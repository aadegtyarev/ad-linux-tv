"""Nonsecret device identity and owned, optional LAN DNS-SD advertisement."""

import ipaddress
import logging
import socket
import threading
import uuid
from urllib.parse import urlsplit

SERVICE_TYPE = "_ad-linux-tv._tcp.local."
PROTOCOL = 1
LOG = logging.getLogger(__name__)


def validate_discovery(value):
    if value is None:
        return None  # Legacy configurations never gain an implicit broadcast or ID.
    if (
        not isinstance(value, dict)
        or set(value) != {"enabled", "id", "name"}
        or type(value["enabled"]) is not bool
        or not isinstance(value["id"], str)
        or str(uuid.UUID(value["id"])) != value["id"]
        or not isinstance(value["name"], str)
        or not 1 <= len(value["name"]) <= 80
        or len(value["name"].encode("utf-8")) > 160
        or value["name"] != value["name"].strip()
        or not value["name"].isprintable()
    ):
        raise ValueError("discovery requires enabled, canonical UUID id and printable name")
    return dict(value)


def new_discovery(name="Linux TV"):
    return validate_discovery({"enabled": True, "id": str(uuid.uuid4()), "name": name})


def device_identity(config, port=None):
    value = validate_discovery(config.get("discovery"))
    if value is None:
        return None
    return {
        "app": "ad-linux-tv",
        "protocol": PROTOCOL,
        "id": value["id"],
        "name": value["name"],
        "port": config["port"] if port is None else port,
        "remote_path": "/remote",
    }


def advertisement_address(config):
    # Same route/bind policy as the existing phone QR; route probing sends no UDP data.
    from .pages import preferred_remote_address
    from .security import private_source

    url = preferred_remote_address(config)
    address = urlsplit(url).hostname if url else None
    if not address:
        return None
    parsed = ipaddress.ip_address(address)
    return parsed.compressed if private_source(address) and not parsed.is_loopback else None


class _Publisher:
    def __init__(self, address, identity):
        from zeroconf import IPVersion, ServiceInfo, Zeroconf

        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        self.info = ServiceInfo(
            SERVICE_TYPE,
            f"ad-linux-tv-{identity['id']}.{SERVICE_TYPE}",
            addresses=[socket.inet_pton(family, address)],
            port=identity["port"],
            properties={
                "id": identity["id"],
                "name": identity["name"],
                "protocol": str(PROTOCOL),
                "path": "/remote",
            },
            server=f"ad-linux-tv-{identity['id']}.local.",
        )
        self.zeroconf = Zeroconf(
            interfaces=[address],
            ip_version=IPVersion.V6Only if family == socket.AF_INET6 else IPVersion.V4Only,
        )
        try:
            self.zeroconf.register_service(self.info, allow_name_change=False)
        except BaseException:
            self.zeroconf.close()
            raise

    def close(self):
        try:
            self.zeroconf.unregister_service(self.info)
        finally:
            self.zeroconf.close()


class DiscoveryAnnouncer:
    """One publisher, periodically re-bound after address changes; constructor is passive."""

    def __init__(self, config, *, resolver=advertisement_address, publisher=_Publisher):
        self.config, self.resolver, self.publisher = config, resolver, publisher
        self.identity = device_identity(config)
        self.enabled = bool(self.identity and config["discovery"]["enabled"])
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.active = None
        self.address = None
        self.state = "disabled" if not self.enabled else "starting"

    def _retire(self):
        if self.active is not None:
            try:
                self.active.close()
            except Exception:
                self.enabled = False  # Unknown retirement must never spawn another publisher.
                self.state = "cleanup_failed"
                raise
        self.active = None
        self.address = None

    def refresh(self):
        """One bounded reconciliation step; tests inject pure fake resolver/publisher."""
        with self.lock:
            if not self.enabled or self.stop_event.is_set():
                return
            try:
                address = self.resolver(self.config)
                if address == self.address and self.active is not None:
                    return
                self._retire()
                if address is None:
                    self.state = "no_lan_address"
                    return
                self.active = self.publisher(address, self.identity)
                self.address, self.state = address, "announcing"
            except Exception:
                # Do not expose local paths, exception text or authentication configuration.
                if self.state != "cleanup_failed":
                    self.state = "unavailable"
                LOG.warning("LAN discovery unavailable; browser remote remains usable")

    def _run(self):
        while not self.stop_event.is_set():
            self.refresh()
            self.stop_event.wait(10)

    def start(self):
        if self.enabled and self.thread is None and not self.stop_event.is_set():
            self.thread = threading.Thread(target=self._run, name="tv-discovery", daemon=True)
            self.thread.start()

    def status(self):
        # Never wait on native multicast registration in an HTTP request.
        return self.state

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.state = "cleanup_failed"
                raise RuntimeError("discovery shutdown not confirmed")
        with self.lock:
            self._retire()
            self.state = "closed"
