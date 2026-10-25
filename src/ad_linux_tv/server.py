"""HTTP application with LAN-authenticated phone control."""

import hashlib
import json
import os
import socket
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import security
from .auth_state import RateLimiter, Sessions
from .control import CommandQueue
from .http_errors import BodyTimeout
from .http_io import DeadlineReader
from .pages import get_response
from .post_routes import handle_post
from .remote_socket import serve_remote_socket
from .settings import SettingsManager
from .sleep_timer import DisplaySleepTimer


def make_handler(config, config_path=None):
    queue = CommandQueue()
    display_timer = DisplaySleepTimer(queue)
    pin_file = (
        os.environ.get("AD_LINUX_TV_PIN_FILE")
        if os.environ.get("AD_LINUX_TV_KIOSK") == "1"
        else None
    )
    session_file = Path(pin_file).with_name("remote-sessions.json") if pin_file else None
    verifier = config["auth"]["verifier"]
    auth_material = verifier if config["auth"].get("require_pin", True) else f"{verifier}:no-pin"
    auth_tag = hashlib.sha256(auth_material.encode()).hexdigest()
    sessions = Sessions(storage_path=session_file, auth_tag=auth_tag)
    settings = SettingsManager(config, config_path, sessions, pin_file=pin_file)
    failures = RateLimiter()
    static = Path(__file__).parent / "static"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.rfile.close()
            self.rfile = DeadlineReader(self.request, getattr(self.server, "read_timeout", 5.0))

        def handle_one_request(self):
            self.rfile.reset_deadline()
            self.payload_consumed = False
            super().handle_one_request()

        def log_message(self, *_args):
            pass

        def send(self, status, body, kind="application/json", headers=()):
            data = body if isinstance(body, bytes) else body.encode()
            if self.command == "POST" and not self.payload_consumed:
                self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            if self.close_connection:
                self.send_header("Connection", "close")
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

        def issue_session(self):
            token, csrf = sessions.create()
            cookie = f"session={token}; HttpOnly; SameSite=Strict; Path=/"
            cookie += f"; Max-Age={sessions.lifetime}"
            return self.send(200, json.dumps({"csrf": csrf}), headers=(("Set-Cookie", cookie),))

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
                data = self.rfile.read(length)
                self.payload_consumed = True
                return json.loads(data)
            except socket.timeout as exc:
                self.close_connection = True
                raise BodyTimeout from exc

        def do_GET(self):
            if urlparse(self.path).path == "/api/remote-ws":
                return serve_remote_socket(
                    self, config, queue, sessions, failures, display_timer, static, settings
                )
            if urlparse(self.path).path == "/api/settings":
                local = (
                    security.loopback_source(self.client_address[0])
                    and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                )
                if (
                    os.environ.get("AD_LINUX_TV_KIOSK") != "1"
                    or not self.private()
                    or not (local or self.authorized())
                ):
                    return self.send(403, "{}")
                return self.send(200, json.dumps(settings.state()))
            if urlparse(self.path).path == "/api/display-timer":
                host = self.headers.get("Host", "")
                local = security.loopback_source(self.client_address[0]) and host == (
                    f"127.0.0.1:{self.server.server_port}"
                )
                if (
                    os.environ.get("AD_LINUX_TV_KIOSK") != "1"
                    or not self.private()
                    or security.remote_url(host, self.server.server_port) is None
                    or not (local or self.authorized())
                ):
                    return self.send(403, "{}")
                return self.send(200, json.dumps(display_timer.status()))
            if urlparse(self.path).path == "/api/command-result":
                host = self.headers.get("Host", "")
                local = security.loopback_source(self.client_address[0]) and host == (
                    f"127.0.0.1:{self.server.server_port}"
                )
                if (
                    os.environ.get("AD_LINUX_TV_KIOSK") != "1"
                    or not self.private()
                    or security.remote_url(host, self.server.server_port) is None
                    or not (local or self.authorized())
                ):
                    return self.send(403, "{}")
                try:
                    query = parse_qs(urlparse(self.path).query, strict_parsing=True)
                    if set(query) != {"id"} or len(query["id"]) != 1:
                        raise ValueError("invalid result id")
                    command_id = query["id"][0]
                    if not 16 <= len(command_id) <= 64 or not all(
                        char.isalnum() or char in "-_" for char in command_id
                    ):
                        raise ValueError("invalid result id")
                except ValueError:
                    return self.send(400, "{}")
                result = queue.result(command_id)
                return self.send(200, json.dumps(result)) if result else self.send(202, "{}")
            if urlparse(self.path).path == "/api/session":
                if (
                    not self.private()
                    or security.remote_url(self.headers.get("Host", ""), self.server.server_port)
                    is None
                ):
                    return self.send(403, "{}")
                token = self.authorized()
                if not token and not config["auth"].get("require_pin", True):
                    if not security.direct_host(
                        self.headers.get("Host", ""),
                        self.connection.getsockname()[0],
                        self.server.server_port,
                    ):
                        return self.send(403, "{}")
                    return self.issue_session()
                csrf = sessions.csrf_for(token) if token else None
                return self.send(200, json.dumps({"csrf": csrf})) if csrf else self.send(401, "{}")
            status, body, kind = get_response(self, config, queue, static)
            self.send(status, body, kind)

        def do_POST(self):
            return handle_post(self, config, queue, sessions, failures, display_timer, settings)

    return Handler
