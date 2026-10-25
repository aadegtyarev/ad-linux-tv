"""Static pages and read-only HTTP endpoints."""

import io
import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from . import audio
from .security import loopback_source, private_source, remote_url


def _advertised_url(address, port):
    parsed = ipaddress.ip_address(address)
    if parsed.is_loopback or not private_source(parsed.compressed):
        return ""
    host = f"[{parsed.compressed}]" if parsed.version == 6 else parsed.compressed
    return remote_url(f"{host}:{port}", port) or ""


def _route_address(family):
    if family == socket.AF_INET6:
        destination = ("2001:4860:4860::8888", 53, 0, 0)
    else:
        destination = ("192.0.2.1", 80)
    with socket.socket(family, socket.SOCK_DGRAM) as probe:
        probe.connect(destination)
        return probe.getsockname()[0]


def preferred_remote_address(config):
    bind = ipaddress.ip_address(config["bind"])
    if bind.is_loopback:
        return ""
    if not bind.is_unspecified:
        return _advertised_url(bind.compressed, config["port"])
    try:
        family = socket.AF_INET6 if bind.version == 6 else socket.AF_INET
        return _advertised_url(_route_address(family), config["port"])
    except OSError:
        return ""


def remote_address(handler, config):
    bind = ipaddress.ip_address(config["bind"])
    port = config["port"]
    if bind.is_loopback:
        return ""
    if not bind.is_unspecified:
        return _advertised_url(bind.compressed, port)
    try:
        local = handler.connection.getsockname()[0]
        advertised = _advertised_url(local, port)
        if advertised:
            return advertised
        family = socket.AF_INET6 if bind.version == 6 else socket.AF_INET
        return _advertised_url(_route_address(family), port)
    except OSError:
        return ""


def get_response(handler, config, queue, static):
    path = urlparse(handler.path).path
    if path == "/api/audio":
        local = (
            loopback_source(handler.client_address[0])
            and handler.headers.get("Host") == f"127.0.0.1:{handler.server.server_port}"
        )
        if (
            os.environ.get("AD_LINUX_TV_KIOSK") != "1"
            or not handler.private()
            or not (local or handler.authorized())
            or remote_url(handler.headers.get("Host", ""), handler.server.server_port) is None
        ):
            return 403, "{}", "application/json"
        try:
            return 200, json.dumps(audio.get_state()), "application/json"
        except audio.AudioUnavailable:
            return 503, "{}", "application/json"
    if path == "/api/local-pin":
        expected_host = f"127.0.0.1:{handler.server.server_port}"
        if (
            not loopback_source(handler.client_address[0])
            or handler.headers.get("Host") != expected_host
            or handler.headers.get("X-TV-Launcher") != "1"
            or os.environ.get("AD_LINUX_TV_KIOSK") != "1"
        ):
            return 403, "{}", "application/json"
        if not config["auth"].get("require_pin", True):
            return 200, json.dumps({"pin_required": False}), "application/json"
        pin_file = os.environ.get("AD_LINUX_TV_PIN_FILE")
        if not pin_file:
            return 503, "{}", "application/json"
        try:
            pin = Path(pin_file).read_text().rstrip("\r\n")
        except OSError:
            return 503, "{}", "application/json"
        if not pin or len(pin) > 128 or not pin.isprintable():
            return 503, "{}", "application/json"
        return 200, json.dumps({"pin": pin}), "application/json"
    if path == "/extension/poll":
        if not handler.valid_bridge():
            return 403, "{}", "application/json"
        return 200, json.dumps(queue.poll()), "application/json"
    if path == "/health":
        return 200, json.dumps(queue.status()), "application/json"
    if path == "/api/status":
        status = queue.status()
        status["preferred_remote_address"] = preferred_remote_address(config)
        return 200, json.dumps(status), "application/json"
    if path == "/api/qr":
        import qrcode

        target = remote_address(handler, config)
        if target is None:
            return 400, "{}", "application/json"
        if not target:
            return 503, "{}", "application/json"
        image = qrcode.make(target)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return 200, output.getvalue(), "image/png"
    if path == "/api/services":
        body = {
            "services": config["services"],
            "page_size": config["page_size"],
            "remote_address": remote_address(handler, config),
        }
        return 200, json.dumps(body), "application/json"
    assets = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/remote": ("remote.html", "text/html; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript"),
        "/layout.js": ("layout.js", "text/javascript"),
        "/launcher_ui.js": ("launcher_ui.js", "text/javascript"),
        "/remote.js": ("remote.js", "text/javascript"),
        "/remote_transport.js": ("remote_transport.js", "text/javascript"),
        "/settings_controls.js": ("settings_controls.js", "text/javascript"),
        "/style.css": ("style.css", "text/css"),
    }
    if path in assets:
        filename, kind = assets[path]
        try:
            return 200, (Path(static) / filename).read_bytes(), kind
        except OSError:
            return 404, "{}", "application/json"
    return 404, "{}", "application/json"
