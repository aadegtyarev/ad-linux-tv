"""HTTP application with LAN-authenticated phone control."""
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse

from .config import verify_pin
from .control import CommandQueue
from .pages import get_response


def make_handler(config):
    queue = CommandQueue()
    sessions = {}
    failures = {}
    static = Path(__file__).parent / "static"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, body, kind="application/json", headers=()):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            for key, value in headers: self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)
        def private(self):
            import ipaddress
            try:
                addr = ipaddress.ip_address(self.client_address[0])
                return addr.is_private or addr.is_loopback
            except ValueError:
                return False

        def authorized(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie.get("session")
            issued = sessions.get(token.value) if token else None
            return issued is not None and time.time() - issued < 43_200
        def do_GET(self):
            status, body, kind = get_response(self, config, queue, static)
            self.send(status, body, kind)

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/login":
                if not self.private():
                    return self.send(403, "{}")
                now = time.time()
                ip = self.client_address[0]
                if failures.get(ip, (0, 0))[1] > now:
                    return self.send(429, "{}")
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 <= length <= 2048: return self.send(413, "{}")
                    raw = self.rfile.read(length)
                    pin = json.loads(raw).get("pin")
                except Exception:
                    return self.send(400, "{}")
                if not verify_pin(pin, config["auth"]):
                    count = failures.get(ip, (0, 0))[0] + 1
                    failures[ip] = (count, now + min(900, 2 ** min(count, 9)))
                    return self.send(401, "{}")
                token = secrets.token_urlsafe(32)
                sessions[token] = now
                return self.send(200, "{}", headers=(("Set-Cookie", f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"),))
            if not self.private() or not self.authorized(): return self.send(403, "{}")
            origin = self.headers.get("Origin", "")
            host = self.headers.get("Host", "")
            if not host or urlparse(origin).netloc != host: return self.send(403, "{}")
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= 2048: return self.send(413, "{}")
                raw = self.rfile.read(length)
                data = json.loads(raw)
                command = data["command"]
                service = data.get("service_id")
                if command == "open" and service not in {x["id"] for x in config["services"]}:
                    raise ValueError
                queue.push(command, service)
            except Exception:
                return self.send(400, "{}")
            return self.send(202, "{}")

    return Handler


def serve(config):
    ThreadingHTTPServer((config["bind"], config["port"]), make_handler(config)).serve_forever()
