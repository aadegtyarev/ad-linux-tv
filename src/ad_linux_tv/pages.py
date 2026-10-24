"""Static pages and read-only HTTP endpoints."""

import io
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlparse

from .security import private_source, remote_url


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
    if path == "/extension/poll":
        if not handler.valid_bridge():
            return 403, "{}", "application/json"
        return 200, json.dumps(queue.poll()), "application/json"
    if path in ("/health", "/api/status"):
        return 200, json.dumps(queue.status()), "application/json"
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
        "/style.css": ("style.css", "text/css"),
    }
    if path in assets:
        filename, kind = assets[path]
        try:
            return 200, (Path(static) / filename).read_bytes(), kind
        except OSError:
            return 404, "{}", "application/json"
    return 404, "{}", "application/json"
