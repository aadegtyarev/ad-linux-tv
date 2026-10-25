"""Authenticated phone WebSocket transport and ordered RPC integration."""

import base64
import json
import socket
import struct
from subprocess import CompletedProcess

from conftest import login


def connect(port, cookie, csrf, origin=None):
    sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    sock.settimeout(2)
    stream = sock.makefile("rb")
    key = base64.b64encode(b"0123456789abcdef").decode()
    headers = (
        "GET /api/remote-ws HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Origin: {origin or f'http://127.0.0.1:{port}'}\r\n"
        f"Cookie: {cookie}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Protocol: csrf.{csrf}\r\n\r\n"
    )
    sock.sendall(headers.encode())
    status = stream.readline().decode().strip()
    response_headers = {}
    while (line := stream.readline()) not in (b"\r\n", b""):
        name, value = line.decode().split(":", 1)
        response_headers[name.lower()] = value.strip()
    if " 101 " in status:
        assert response_headers["sec-websocket-protocol"] == f"csrf.{csrf}"
    return sock, stream, status


def send_message(sock, item):
    payload = json.dumps(item).encode()
    mask = b"test"
    size = (
        bytes([len(payload) | 0x80])
        if len(payload) < 126
        else b"\xfe" + struct.pack("!H", len(payload))
    )
    sock.sendall(
        b"\x81"
        + size
        + mask
        + bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    )


def receive_message(stream):
    first, second = stream.read(2)
    assert first == 0x81
    size = second & 0x7F
    if size == 126:
        size = struct.unpack("!H", stream.read(2))[0]
    return json.loads(stream.read(size))


def test_remote_socket_requires_origin_cookie_and_csrf(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    response, result, cookie = login(connection, port)
    assert response.status == 200
    for wrong_cookie, wrong_csrf, wrong_origin in (
        ("", result["csrf"], None),
        (cookie, "wrong", None),
        (cookie, result["csrf"], "http://attacker.example"),
    ):
        sock, stream, status = connect(port, wrong_cookie, wrong_csrf, wrong_origin)
        assert " 403 " in status
        stream.close()
        sock.close()


def test_remote_socket_keeps_one_connection_and_orders_actions(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as routes

    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(routes, "firefox_active", lambda: True)
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr(routes.subprocess, "run", run)
    connection, port = endpoint
    _response, result, cookie = login(connection, port)
    sock, stream, status = connect(port, cookie, result["csrf"])
    assert " 101 " in status
    try:
        actions = (
            ("GET", "/api/services", None),
            ("POST", "/api/pointer", {"dx": 5, "dy": 1}),
            ("POST", "/api/pointer", {"dx": -2, "dy": 3}),
            ("POST", "/api/pointer", {"click": True}),
            ("POST", "/api/input", {"key": "tab"}),
            ("POST", "/api/command", {"command": "home"}),
            ("GET", "/api/status", None),
            ("GET", "/api/display-timer", None),
        )
        for number, (method, path, body) in enumerate(actions, 1):
            send_message(sock, {"id": number, "method": method, "path": path, "body": body})
        replies = [receive_message(stream) for _ in actions]
        assert [reply["id"] for reply in replies] == list(range(1, len(actions) + 1))
        assert [reply["status"] for reply in replies] == [200, 200, 200, 200, 200, 202, 200, 200]
        assert replies[0]["body"]["services"]
        assert replies[6]["body"]["pending_commands"] == 1
        assert [command[1:3] for command in commands[:3]] == [
            ["pointer", "move"],
            ["pointer", "move"],
            ["pointer", "click"],
        ]
    finally:
        stream.close()
        sock.close()


def test_remote_socket_rejects_unmasked_frame(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    _response, result, cookie = login(connection, port)
    sock, stream, status = connect(port, cookie, result["csrf"])
    assert " 101 " in status
    try:
        sock.sendall(b"\x81\x02{}")
        assert stream.read(2) == b"\x88\x02"
        assert stream.read(2) == struct.pack("!H", 1002)
    finally:
        stream.close()
        sock.close()
