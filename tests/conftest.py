"""Reusable local HTTP fixtures for endpoint tests."""

import base64
import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from ad_linux_tv.defaults import DEFAULT_SERVICES
from ad_linux_tv.server import make_handler


def make_config():
    salt = b"0123456789abcdef"
    verifier = hashlib.pbkdf2_hmac("sha256", b"1234", salt, 310_000)
    return {
        "auth": {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(verifier).decode(),
        },
        "services": DEFAULT_SERVICES,
        "page_size": 12,
        "port": 8765,
        "bind": "127.0.0.1",
    }


@pytest.fixture
def endpoint():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(make_config()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    yield connection, server.server_port
    connection.close()
    server.shutdown()


def request(connection, method, path, body=None, headers=None):
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    return response, payload


def login(connection, port, pin="1234", forwarded=None):
    headers = {
        "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{port}",
    }
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    response, payload = request(connection, "POST", "/api/login", json.dumps({"pin": pin}), headers)
    cookie = response.getheader("Set-Cookie", "").split(";", 1)[0]
    return response, json.loads(payload), cookie


def command_headers(port, cookie, csrf, origin=None):
    return {
        "Content-Type": "application/json",
        "Cookie": cookie,
        "Origin": origin or f"http://127.0.0.1:{port}",
        "X-CSRF-Token": csrf,
    }
