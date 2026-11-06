"""Local overlay authority and authenticated phone-open boundary."""

import json

from conftest import login, request
from test_remote_socket import connect, receive_message, send_message

PANEL = "/api/local-video-panel"


def overlay_headers(port):
    return {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "X-AD-Linux-TV-Video-Panel": "video-panel-v1",
        "Content-Type": "application/json",
    }


def test_local_panel_rejects_missing_or_forged_authority(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    good = overlay_headers(port)
    for headers in (
        {},
        {**good, "Origin": "http://attacker.example"},
        {**good, "Host": "attacker.example"},
        {**good, "X-AD-Linux-TV-Video-Panel": "wrong"},
    ):
        response, _ = request(connection, "GET", PANEL, headers=headers)
        assert response.status == 403
    response, payload = request(connection, "GET", PANEL, headers=good)
    assert response.status == 200
    state = json.loads(payload)
    assert state["visible"] is False
    assert "media_id" not in state
    monkeypatch.delenv("AD_LINUX_TV_KIOSK")
    response, _ = request(connection, "GET", PANEL, headers=good)
    assert response.status == 403


def test_local_panel_only_accepts_fixed_actions(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    headers = overlay_headers(port)
    response, payload = request(connection, "GET", PANEL, headers=headers)
    assert response.status == 200
    instance = json.loads(payload)["instance"]
    for action, expected in (
        ({"action": "open", "extra": True}, 400),
        ({"action": "close", "extra": True}, 400),
        ({"action": "apply", "instance": instance, "revision": 0}, 409),
        (
            {
                "action": "choose",
                "instance": instance,
                "mode": "4:3",
                "mirror": False,
                "revision": 0,
            },
            409,
        ),
        ({"action": "close"}, 400),
        ({"action": "close", "instance": instance, "opening": None}, 400),
        ({"action": "close", "instance": "f" * 32, "opening": "a" * 32}, 409),
        ({"action": "close", "instance": instance, "opening": "a" * 32}, 409),
    ):
        response, _ = request(connection, "POST", PANEL, json.dumps(action), headers)
        assert response.status == expected


def test_local_fixed_shortcut_open_needs_live_overlay_and_exact_authority(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    headers = overlay_headers(port)
    body = json.dumps({"action": "open"})
    assert request(connection, "POST", PANEL, body, headers)[0].status == 503
    assert (
        request(connection, "POST", PANEL, body, {**headers, "Origin": "http://bad.example"})[
            0
        ].status
        == 403
    )
    assert request(connection, "GET", PANEL, headers=headers)[0].status == 200
    duplicate = '{"action":"close","action":"open"}'
    assert request(connection, "POST", PANEL, duplicate, headers)[0].status == 400
    response, payload = request(connection, "POST", PANEL, body, headers)
    assert response.status == 200 and json.loads(payload)["visible"] is True


def test_phone_open_requires_authenticated_socket_and_live_overlay(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    response, result, cookie = login(connection, port)
    assert response.status == 200
    bad_socket, bad_stream, status = connect(port, "", result["csrf"])
    assert " 403 " in status
    bad_stream.close()
    bad_socket.close()
    sock, stream, status = connect(port, cookie, result["csrf"])
    assert " 101 " in status
    try:
        item = {
            "id": 1,
            "method": "POST",
            "path": "/api/tv-video-panel",
            "body": {"action": "open"},
        }
        send_message(sock, item)
        assert receive_message(stream)["status"] == 503
        response, _ = request(connection, "GET", PANEL, headers=overlay_headers(port))
        assert response.status == 200
        item["id"] = 2
        send_message(sock, item)
        reply = receive_message(stream)
        assert reply["status"] == 202 and reply["body"] == {"accepted": True}
        response, payload = request(connection, "GET", PANEL, headers=overlay_headers(port))
        state = json.loads(payload)
        assert response.status == 200 and state["visible"] is True
        item["id"] = 3
        send_message(sock, item)
        assert receive_message(stream)["status"] == 202
        stale_close = {
            "action": "close",
            "instance": state["instance"],
            "opening": state["opening"],
        }
        response, _ = request(
            connection, "POST", PANEL, json.dumps(stale_close), overlay_headers(port)
        )
        assert response.status == 409
        response, payload = request(connection, "GET", PANEL, headers=overlay_headers(port))
        state = json.loads(payload)
        current_close = {
            "action": "close",
            "instance": state["instance"],
            "opening": state["opening"],
        }
        response, payload = request(
            connection, "POST", PANEL, json.dumps(current_close), overlay_headers(port)
        )
        assert response.status == 200 and json.loads(payload)["visible"] is False
        item["id"] = 4
        item["body"] = {"action": "open", "extra": True}
        send_message(sock, item)
        assert receive_message(stream)["status"] == 400
    finally:
        stream.close()
        sock.close()
