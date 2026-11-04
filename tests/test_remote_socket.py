"""Authenticated phone WebSocket transport and ordered RPC integration."""

import base64
import json
import socket
import struct
import time
from subprocess import CompletedProcess

from conftest import login, request

from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE


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


def test_video_geometry_through_socket_and_bridge_requires_capability(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    _, session, cookie = login(connection, port)
    bridge = {
        "Host": f"127.0.0.1:{port}",
        BRIDGE_HEADER: BRIDGE_VALUE,
        "Content-Type": "application/json",
    }
    now = int(time.time() * 1000)
    media_id = "a" * 32
    report = {
        "protocol": 1,
        "sequence": now,
        "sent_at": now,
        "capabilities": ["html_media_v1"],
        "media": {
            "media_id": media_id,
            "playing": True,
            "position": 12,
            "duration": 900,
            "can_seek": True,
        },
    }
    assert (
        request(connection, "POST", "/extension/media", json.dumps(report), bridge)[0].status == 200
    )
    sock, stream, status = connect(port, cookie, session["csrf"])
    assert " 101 " in status

    def rpc(number, method, body):
        send_message(
            sock, {"id": number, "method": method, "path": "/api/video-geometry", "body": body}
        )
        reply = receive_message(stream)
        assert reply["id"] == number
        return reply

    try:
        command = {"action": "apply", "media_id": media_id, "mode": "4:3", "mirror": True}
        assert rpc(1, "GET", None)["body"] == {"available": False, "media_id": None}
        assert rpc(2, "POST", command)["status"] == 409
        assert json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1]) == []
        report["sequence"] += 1
        report["sent_at"] = int(time.time() * 1000)
        report["capabilities"].append("video_geometry_v1")
        assert (
            request(connection, "POST", "/extension/media", json.dumps(report), bridge)[0].status
            == 200
        )
        assert rpc(3, "GET", None)["body"] == {"available": True, "media_id": media_id}
        reply = rpc(4, "POST", command)
        assert reply["status"] == 202
        command_id = reply["body"]["id"]
        assert rpc(5, "POST", {"action": "result", "id": command_id})["status"] == 202
        item = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])[0]
        assert item["id"] == command_id and item["command"] == "video_geometry"
        assert item["mode"] == "4:3" and item["mirror"] is True
        ack = json.dumps({"id": command_id, "outcome": "failed", "reason": "unsupported"})
        assert request(connection, "POST", "/extension/ack", ack)[0].status == 403
        assert request(connection, "POST", "/extension/ack", ack, bridge)[0].status == 200
        assert request(connection, "POST", "/extension/ack", ack, bridge)[0].status == 409
        result = rpc(6, "POST", {"action": "result", "id": command_id})
        assert result["status"] == 200 and result["body"]["outcome"] == "failed"
        second = rpc(7, "POST", command)["body"]["id"]
        item = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])[0]
        assert item["id"] == second
        ack = json.dumps({"id": second, "outcome": "completed", "reason": None})
        assert request(connection, "POST", "/extension/ack", ack, bridge)[0].status == 200
        assert rpc(8, "POST", {"action": "result", "id": second})["status"] == 202
        report["sequence"] += 1
        report["sent_at"] = int(time.time() * 1000)
        assert (
            request(connection, "POST", "/extension/media", json.dumps(report), bridge)[0].status
            == 200
        )
        result = rpc(9, "POST", {"action": "result", "id": second})
        assert result["status"] == 200 and result["body"]["outcome"] == "completed"
        response, body = request(
            connection, "GET", "/api/display-timer", headers={"Host": f"127.0.0.1:{port}"}
        )
        assert response.status == 200 and json.loads(body)["video_notice"] is True
    finally:
        stream.close()
        sock.close()


def test_remote_socket_media_uses_same_authenticated_channel(endpoint, monkeypatch):
    import ad_linux_tv.remote_rpc as rpc

    class FakeMedia:
        def status(self):
            return {"available": True, "title": "Test", "can_seek": False}

        def command(self, action, position=None):
            if action != "pause" or position is not None:
                raise ValueError("unsupported")
            return {"available": True, "title": "Test", "playing": False}

    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(rpc, "get_media_monitor", FakeMedia)
    connection, port = endpoint
    _response, result, cookie = login(connection, port)
    sock, stream, status = connect(port, cookie, result["csrf"])
    assert " 101 " in status
    try:
        for number, method, body in (
            (1, "GET", None),
            (2, "POST", {"action": "pause"}),
            (3, "POST", {"action": "seek", "position": 999}),
            (4, "POST", {"action": "pause", "unexpected": True}),
        ):
            send_message(sock, {"id": number, "method": method, "path": "/api/media", "body": body})
        replies = [receive_message(stream) for _ in range(4)]
        assert [reply["status"] for reply in replies] == [200, 200, 409, 400]
        assert replies[0]["body"]["title"] == "Test"
        assert replies[1]["body"]["playing"] is False
    finally:
        stream.close()
        sock.close()
