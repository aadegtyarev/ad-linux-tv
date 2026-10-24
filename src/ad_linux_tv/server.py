"""HTTP application with LAN-authenticated phone control."""

import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from .auth_state import RateLimiter, Sessions
from .control import CommandQueue
from .pages import get_response
from .post_routes import handle_post
from .security import loopback_host, private_source, remote_url


def make_handler(config):
    queue = CommandQueue()
    sessions = Sessions()
    failures = RateLimiter()
    static = Path(__file__).parent / "static"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, body, kind="application/json", headers=()):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'",
            )
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def private(self):
            return private_source(self.client_address[0])

        def authorized(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie.get("session")
            return token.value if token and sessions.valid(token.value) else None

        def valid_origin(self, local_ui=False):
            origin = urlparse(self.headers.get("Origin", ""))
            host = self.headers.get("Host", "")
            return (
                origin.scheme == "http"
                and origin.netloc.lower() == host.lower()
                and remote_url(host, self.server.server_port) is not None
                and (not local_ui or loopback_host(host))
            )

        def read_payload(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("transfer encoding is unsupported")
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= 2048:
                raise OverflowError("request body exceeds limit")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            status, body, kind = get_response(self, config, queue, static)
            self.send(status, body, kind)

        def do_POST(self):
            return handle_post(self, config, queue, sessions, failures)

    return Handler
