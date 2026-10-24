"""Static pages and read-only HTTP endpoints."""
import io
import json
from urllib.parse import urlparse


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
        host = handler.headers.get("Host", "").split(":", 1)[0]
        if not host: return 400, "{}", "application/json"
        image = qrcode.make(f"http://{host}:{config['port']}/remote")
        output = io.BytesIO(); image.save(output, format="PNG")
        return 200, output.getvalue(), "image/png"
    if path == "/api/services":
        body = {"services": config["services"], "page_size": config["page_size"]}
        return 200, json.dumps(body), "application/json"
    filename = {"/": "index.html", "/remote": "remote.html", "/app.js": "app.js", "/remote.js": "remote.js", "/style.css": "style.css"}.get(path)
    if filename:
        kind = "text/html; charset=utf-8" if filename.endswith("html") else "text/javascript" if filename.endswith("js") else "text/css"
        try: return 200, (static / filename).read_bytes(), kind
        except FileNotFoundError: return 404, "{}", "application/json"
    return 404, "{}", "application/json"
