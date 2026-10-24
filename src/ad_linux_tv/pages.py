"""Static pages and read-only HTTP endpoints."""

import io
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlparse

from .security import loopback_host, private_source, remote_url


def remote_address(handler, config):
    host = handler.headers.get("Host", "")
    port = config["port"]
    current = remote_url(host, port)
    if current is None:
        return None
    if not loopback_host(host):
        return current
    bind = ipaddress.ip_address(config["bind"])
    if not bind.is_unspecified and not bind.is_loopback:
        if not private_source(bind.compressed):
            return ""
        host = f"[{bind.compressed}]" if bind.version == 6 else bind.compressed
        return remote_url(host, port)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            address = probe.getsockname()[0]
        if private_source(address):
            return remote_url(address, port)
    except OSError:
        pass
    return ""


def get_response(handler, config, queue, static):
    path = urlparse(handler.path).path
    if path in ("/extension/poll", "/extension/heartbeat"):
        if handler.client_address[0] not in ("127.0.0.1", "::1"):
            return 403, "{}", "application/json"
        result = queue.poll() if path.endswith("poll") else queue.status()
        return 200, json.dumps(result), "application/json"
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
