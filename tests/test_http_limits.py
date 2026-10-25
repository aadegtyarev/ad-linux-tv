"""HTTP worker, body-timeout, and login-admission limits."""

import socket
import threading
import time
from http.client import HTTPConnection
from threading import Semaphore

from conftest import make_config

from ad_linux_tv.listener import make_server
from ad_linux_tv.server import make_handler


def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_remote_requests_reuse_connection():
    server = make_server("127.0.0.1", 0, make_handler(make_config()))
    running(server)
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        connection.request("GET", "/api/session")
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        first_socket = connection.sock
        assert first_socket is not None
        connection.request("GET", "/api/services")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        assert connection.sock is first_socket
    finally:
        connection.close()
        server.shutdown()


def test_worker_limit_rejects_excess_request_without_blocking_first():
    started = threading.Event()
    release = threading.Event()

    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            started.set()
            release.wait(2)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = make_server("127.0.0.1", 0, Handler, Semaphore(1))
    running(server)
    first = HTTPConnection("127.0.0.1", server.server_port)
    first.request("GET", "/")
    assert started.wait(1)
    second = HTTPConnection("127.0.0.1", server.server_port)
    second.request("GET", "/")
    assert second.getresponse().status == 503
    release.set()
    assert first.getresponse().status == 200
    first.close()
    second.close()
    server.shutdown()


def test_slow_headers_cannot_extend_absolute_read_deadline():
    server = make_server("127.0.0.1", 0, make_handler(make_config()))
    server.read_timeout = 0.15
    running(server)
    client = socket.create_connection(("127.0.0.1", server.server_port), timeout=1)
    client.sendall(b"GET /api/services HTTP/1.1\r\nHost: 127.0.0.1\r\n")
    time.sleep(0.08)
    try:
        client.sendall(b"X-Slow: one\r\n")
    except OSError:
        pass
    time.sleep(0.1)
    client.settimeout(1)
    assert client.recv(100) == b""
    client.close()
    server.shutdown()


def test_slow_body_times_out_and_releases_auth_admission():
    server = make_server("127.0.0.1", 0, make_handler(make_config()))
    server.read_timeout = 0.1
    running(server)
    port = server.server_port
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    connection.putrequest("POST", "/api/login")
    connection.putheader("Host", f"127.0.0.1:{port}")
    connection.putheader("Origin", f"http://127.0.0.1:{port}")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "40")
    connection.endheaders()
    connection.send(b'{"pin":')
    assert connection.getresponse().status == 408
    connection.close()
    server.shutdown()
