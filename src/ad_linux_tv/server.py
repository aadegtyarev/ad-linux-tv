"""HTTP application with LAN-authenticated phone control."""

import json
import socket
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from . import security
from .auth_state import RateLimiter, Sessions
from .control import CommandQueue
from .http_errors import BodyTimeout
from .http_io import DeadlineReader
from .pages import get_response
from .post_routes import handle_post


def make_handler(config):
    queue = CommandQueue()
    sessions = Sessions()
    failures = RateLimiter()
    static = Path(__file__).parent / "static"

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.rfile.close()
            self.rfile = DeadlineReader(self.request, getattr(self.server, "read_timeout", 5.0))

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
            return security.private_source(self.client_address[0])

        def valid_bridge(self):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            return (
                security.loopback_source(self.client_address[0])
                and self.headers.get("Host", "") == expected_host
                and self.headers.get(security.BRIDGE_HEADER) == security.BRIDGE_VALUE
            )

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
                and security.remote_url(host, self.server.server_port) is not None
                and (not local_ui or security.loopback_host(host))
            )

        def read_payload(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("transfer encoding is unsupported")
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= 2048:
                raise OverflowError("request body exceeds limit")
            try:
                return json.loads(self.rfile.read(length))
            except socket.timeout as exc:
                self.close_connection = True
                raise BodyTimeout from exc

        def do_GET(self):
            status, body, kind = get_response(self, config, queue, static)
            self.send(status, body, kind)

        def do_POST(self):
            return handle_post(self, config, queue, sessions, failures)

    return Handler
