"""Private settings shared by the local TV and paired phone."""

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from threading import RLock, Timer

import yaml

from .audio import OUTPUT_ID
from .browser_locale import (
    browser_locale,
    installed_locales,
    locale_profile_text,
    validate_browser,
)
from .build_info import server_info
from .magnifier import validate_magnifier
from .view_config import common_view, service_views, validate_view, view_fingerprint


class SettingsError(ValueError):
    pass


def validate_proxy(value):
    if not isinstance(value, dict) or value.get("mode") not in ("system", "none", "custom"):
        raise SettingsError("invalid proxy mode")
    if value["mode"] != "custom":
        if set(value) != {"mode"}:
            raise SettingsError("invalid proxy fields")
        return dict(value)
    if set(value) != {"mode", "protocol", "host", "port"} or value["protocol"] not in (
        "http",
        "socks5",
    ):
        raise SettingsError("invalid custom proxy")
    host = value["host"]
    if (
        not isinstance(host, str)
        or not re.fullmatch(r"[A-Za-z0-9.:-]{1,253}", host)
        or host.startswith("-")
    ):
        raise SettingsError("invalid proxy host")
    if type(value["port"]) is not int or not 1 <= value["port"] <= 65535:
        raise SettingsError("invalid proxy port")
    return dict(value)


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def proxy_prefs(proxy):
    mode = proxy["mode"]
    bypass = "localhost, 127.0.0.1, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12"
    if mode == "system":
        return {"network.proxy.type": 5, "network.proxy.no_proxies_on": bypass}
    if mode == "none":
        return {"network.proxy.type": 0}
    host = proxy["host"]
    port = proxy["port"]
    prefs = {
        "network.proxy.type": 1,
        "network.proxy.no_proxies_on": bypass,
    }
    if proxy["protocol"] == "http":
        prefs.update(
            {
                "network.proxy.http": host,
                "network.proxy.http_port": port,
                "network.proxy.ssl": host,
                "network.proxy.ssl_port": port,
            }
        )
    else:
        prefs.update(
            {
                "network.proxy.socks": host,
                "network.proxy.socks_port": port,
                "network.proxy.socks_version": 5,
                "network.proxy.socks_remote_dns": True,
            }
        )
    return prefs


def write_proxy_profile(path, proxy):
    path = Path(path)
    existing = path.read_text() if path.exists() else ""
    kept = [
        line
        for line in existing.splitlines()
        if not line.lstrip().startswith('user_pref("network.proxy.')
    ]
    for key, value in proxy_prefs(proxy).items():
        kept.append(f"user_pref({json.dumps(key)}, {json.dumps(value)});")
    atomic_write(path, "\n".join(kept) + "\n")


SDDM_UNITS = (
    "/etc/systemd/system/sddm.service",
    "/usr/lib/systemd/system/sddm.service",
    "/lib/systemd/system/sddm.service",
)


def kde_available():
    """The optional desktop switch exists only where a KDE display manager is installed."""
    return any(Path(unit).exists() for unit in SDDM_UNITS)


class SettingsManager:
    def __init__(
        self, config, config_path, sessions, pin_file=None, profile=None, capabilities=None
    ):
        self.config = config
        self.path = Path(config_path) if config_path else None
        self.sessions = sessions
        self.pin_file = Path(pin_file) if pin_file else None
        self.profile = Path(profile or Path.home() / "snap/firefox/common/ad-linux-tv-profile")
        self.lock = RLock()
        self.magnified = False
        self.proxy_restart_required = False
        self.locale_restart_required = False
        self.capabilities = capabilities or (lambda: [])
        self.view_boot_known = "AD_LINUX_TV_VIEW_HASH" in os.environ
        self.applied_view_hash = os.environ.get("AD_LINUX_TV_VIEW_HASH", view_fingerprint(config))
        # A server-only restart must not mistake a saved pending scale for an
        # applied one. The compositor launcher exports its boot-time scale.
        try:
            self.applied_magnifier_scale = validate_magnifier(
                {"scale": float(os.environ.get("AD_LINUX_TV_MAGNIFIER_SCALE", "2.5"))}
            )["scale"]
        except ValueError:
            self.applied_magnifier_scale = 2.5

    def proxy(self):
        if "proxy" in self.config:
            return self.config["proxy"]
        # Profiles configured before the proxy setting existed may use local Xray.
        try:
            prefs = (self.profile / "user.js").read_text()
            if (
                'user_pref("network.proxy.http", "127.0.0.1")' in prefs
                and 'user_pref("network.proxy.http_port", 1081)' in prefs
            ):
                return {"mode": "custom", "protocol": "http", "host": "127.0.0.1", "port": 1081}
        except OSError:
            pass
        return {"mode": "system"}

    def state(self):
        with self.lock:
            return {
                "server": server_info(),
                "require_pin": self.config["auth"].get("require_pin", True),
                "magnifier": self.magnified,
                "magnifier_scale": self.config.get("magnifier", {}).get("scale", 2.5),
                "magnifier_applied_scale": self.applied_magnifier_scale,
                "restart_required": self.proxy_restart_required
                or self.locale_restart_required
                or self.config.get("magnifier", {}).get("scale", 2.5)
                != self.applied_magnifier_scale
                or view_fingerprint(self.config) != self.applied_view_hash,
                "view": common_view(self.config),
                "service_views": service_views(self.config),
                "view_exceptions_count": sum(
                    "view" in service for service in self.config["services"]
                ),
                "view_profile_ready": self.view_boot_known
                and view_fingerprint(self.config) == self.applied_view_hash,
                "view_restart_required": view_fingerprint(self.config) != self.applied_view_hash,
                "view_bridge_ready": "tab_view_v1" in self.capabilities(),
                "proxy": dict(self.proxy()),
                "proxy_restart_required": self.proxy_restart_required,
                "pointer_acceleration": self.config.get("pointer", {}).get("acceleration", 50),
                "browser_locale": browser_locale(self.config),
                "browser_locales_installed": installed_locales(self.profile),
                "browser_locale_restart_required": self.locale_restart_required,
                "kde_available": kde_available(),
            }

    def audio_levels(self):
        with self.lock:
            audio = self.config.get("audio", {})
            return {"browser": audio.get("browser", 100), "player": audio.get("player", 100)}

    def browser_mute_target(self):
        with self.lock:
            return self.config.get("audio", {}).get("browser_muted", False)

    def set_browser_mute(self, value):
        if type(value) is not bool:
            raise SettingsError("invalid Firefox mute")
        with self.lock:
            current = self.config.get("audio", {})
            if current.get("browser_muted", False) != value or "browser_muted" not in current:
                updated = {**self.audio_levels(), **current, "browser_muted": value}
                self._save_config(dict(self.config, audio=updated))

    def set_audio_output(self, value):
        if not isinstance(value, str) or not OUTPUT_ID.fullmatch(value):
            raise SettingsError("invalid audio output")
        with self.lock:
            current = self.config.get("audio", {})
            if current.get("output") != value:
                updated = {**self.audio_levels(), **current, "output": value}
                self._save_config(dict(self.config, audio=updated))

    def set_audio_level(self, name, value):
        if name not in ("browser", "player") or type(value) is not int or not 0 <= value <= 100:
            raise SettingsError("invalid audio level")
        with self.lock:
            levels = self.audio_levels()
            if levels[name] != value:
                updated = dict(self.config.get("audio", levels), **{name: value})
                self._save_config(dict(self.config, audio=updated))

    def _save_config(self, candidate):
        if self.path is None:
            raise OSError("settings path unavailable")
        atomic_write(self.path, yaml.safe_dump(candidate, allow_unicode=True))
        self.config.clear()
        self.config.update(candidate)

    def update(self, action):
        if not isinstance(action, dict) or set(action) != {"setting", "value"}:
            raise SettingsError("invalid settings action")
        with self.lock:
            setting, value = action["setting"], action["value"]
            if setting == "pin":
                if (
                    not isinstance(value, dict)
                    or set(value) != {"enabled", "pin", "confirm"}
                    or type(value["enabled"]) is not bool
                ):
                    raise SettingsError("invalid PIN action")
                if value["enabled"]:
                    if self.pin_file is None:
                        raise OSError("PIN display unavailable")
                    pin = value["pin"]
                    if (
                        not isinstance(pin, str)
                        or not re.fullmatch(r"[0-9]{4}", pin)
                        or pin != value["confirm"]
                    ):
                        raise SettingsError("PIN must be four matching digits")
                    salt = secrets.token_bytes(16)
                    verifier = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310_000)
                    auth = {
                        "salt": base64.b64encode(salt).decode(),
                        "verifier": base64.b64encode(verifier).decode(),
                        "require_pin": True,
                    }
                else:
                    if value["pin"] is not None or value["confirm"] is not None:
                        raise SettingsError("PIN fields must be empty")
                    if not self.config["auth"].get("require_pin", True):
                        return self.state()
                    auth = dict(self.config["auth"], require_pin=False)
                candidate = dict(self.config, auth=auth)
                old_pin = (
                    self.pin_file.read_text() if self.pin_file and self.pin_file.exists() else None
                )
                if value["enabled"] and self.pin_file:
                    atomic_write(self.pin_file, pin + "\n")
                try:
                    self._save_config(candidate)
                except OSError:
                    if self.pin_file:
                        if old_pin is None:
                            self.pin_file.unlink(missing_ok=True)
                        else:
                            atomic_write(self.pin_file, old_pin)
                    raise
                tag = hashlib.sha256(
                    (
                        auth["verifier"] if auth["require_pin"] else f"{auth['verifier']}:no-pin"
                    ).encode()
                ).hexdigest()
                self.sessions.reset(tag)
            elif setting == "proxy":
                proxy = validate_proxy(value)
                previous = self.proxy()
                if proxy != previous:
                    candidate = dict(self.config, proxy=proxy)
                    profile_path = self.profile / "user.js"
                    old_prefs = profile_path.read_text() if profile_path.exists() else None
                    write_proxy_profile(profile_path, proxy)
                    try:
                        self._save_config(candidate)
                    except OSError:
                        if old_prefs is None:
                            profile_path.unlink(missing_ok=True)
                        else:
                            atomic_write(profile_path, old_prefs)
                        raise
                    self.proxy_restart_required = True
            elif setting == "browser_locale":
                try:
                    browser = validate_browser({"locale": value})
                except ValueError as exc:
                    raise SettingsError(str(exc)) from None
                if browser["locale"] != browser_locale(self.config):
                    candidate = dict(self.config, browser=browser)
                    profile_path = self.profile / "user.js"
                    old_prefs = profile_path.read_text() if profile_path.exists() else None
                    prefs = locale_profile_text(old_prefs or "", browser["locale"])
                    atomic_write(profile_path, prefs)
                    try:
                        self._save_config(candidate)
                    except OSError:
                        if old_prefs is None:
                            profile_path.unlink(missing_ok=True)
                        else:
                            atomic_write(profile_path, old_prefs)
                        raise
                    self.locale_restart_required = True
            elif setting == "view":
                if value is None:
                    candidate = dict(self.config)
                    candidate.pop("view", None)
                else:
                    try:
                        view = validate_view(value)
                    except ValueError as exc:
                        raise SettingsError(str(exc)) from None
                    candidate = dict(self.config, view=view)
                if candidate != self.config:
                    self._save_config(candidate)
            elif setting == "service_view":
                if (
                    not isinstance(value, dict)
                    or set(value) != {"id", "view"}
                    or not isinstance(value["id"], str)
                ):
                    raise SettingsError("invalid service view action")
                service = next(
                    (item for item in self.config["services"] if item.get("id") == value["id"]),
                    None,
                )
                if service is None:
                    raise SettingsError("unknown service")
                if value["view"] is None:
                    override = None
                else:
                    try:
                        override = validate_view(value["view"])
                    except ValueError as exc:
                        raise SettingsError(str(exc)) from None
                services = [dict(item) for item in self.config["services"]]
                target = next(item for item in services if item["id"] == value["id"])
                if override is None:
                    target.pop("view", None)
                else:
                    target["view"] = override
                candidate = dict(self.config, services=services)
                if candidate != self.config:
                    self._save_config(candidate)
            elif setting == "pointer_acceleration":
                if type(value) is not int or not 0 <= value <= 100:
                    raise SettingsError("invalid pointer acceleration")
                if value != self.config.get("pointer", {}).get("acceleration", 50):
                    self._save_config(dict(self.config, pointer={"acceleration": value}))
            elif setting == "magnifier_scale":
                try:
                    magnifier = validate_magnifier({"scale": value})
                except ValueError as exc:
                    raise SettingsError(str(exc)) from None
                if magnifier["scale"] != self.config.get("magnifier", {}).get("scale", 2.5):
                    self._save_config(dict(self.config, magnifier=magnifier))
            elif setting == "magnifier":
                if type(value) is not bool:
                    raise SettingsError("invalid magnifier state")
                if value != self.magnified:
                    result = subprocess.run(
                        ["/usr/bin/wtype", "-k", "F9"], check=False, capture_output=True, timeout=2
                    )
                    if result.returncode:
                        raise OSError("magnifier unavailable")
                    self.magnified = value
            elif setting == "restart":
                if value is not True or not self.state()["restart_required"]:
                    raise SettingsError("restart is not pending")

                def restart_kiosk():
                    try:
                        subprocess.run(
                            [
                                "/usr/bin/sudo",
                                "-n",
                                "/usr/bin/systemctl",
                                "--no-block",
                                "restart",
                                "ad-linux-tv-kiosk.service",
                            ],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass

                timer = Timer(0.7, restart_kiosk)
                timer.daemon = True
                timer.start()
            else:
                raise SettingsError("unknown setting")
            return self.state()
