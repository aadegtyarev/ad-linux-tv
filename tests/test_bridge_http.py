"""Loopback-only bridge lease and acknowledgement endpoints."""

import json

from conftest import command_headers, login, request

from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE


def test_player_target_is_visible_only_to_local_bridge(endpoint):
    connection, port = endpoint
    route = "/extension/audio-target"
    assert request(connection, "GET", route)[0].status == 403
    bridge = {"Host": f"127.0.0.1:{port}", BRIDGE_HEADER: BRIDGE_VALUE}
    response, body = request(connection, "GET", route, headers=bridge)
    assert response.status == 200 and json.loads(body) == {"volume": 100}


def test_bridge_requires_custom_header_exact_host_and_orders_acknowledgements(endpoint):
    connection, port = endpoint
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    for command in ('{"command":"home"}', '{"command":"open","service_id":"youtube"}'):
        assert request(connection, "POST", "/api/command", command, headers)[0].status == 202

    status = json.loads(request(connection, "GET", "/api/status")[1])
    assert not status["extension_online"] and status["pending_commands"] == 2
    missing = {"Host": f"127.0.0.1:{port}"}
    assert request(connection, "GET", "/extension/poll", headers=missing)[0].status == 403
    foreign = {"Host": f"attacker.example:{port}", BRIDGE_HEADER: BRIDGE_VALUE}
    assert request(connection, "GET", "/extension/poll", headers=foreign)[0].status == 403

    bridge = {"Host": f"127.0.0.1:{port}", BRIDGE_HEADER: BRIDGE_VALUE}
    response, payload = request(connection, "GET", "/extension/poll", headers=bridge)
    first = json.loads(payload)[0]
    assert response.status == 200 and first["command"] == "home"
    assert response.getheader("Access-Control-Allow-Origin") is None
    assert request(connection, "GET", "/extension/poll", headers=bridge)[1] == b"[]"
    ack_headers = {**bridge, "Content-Type": "application/json"}

    def acknowledge(command_id, outcome="completed", reason=None):
        body = json.dumps({"id": command_id, "outcome": outcome, "reason": reason})
        return request(connection, "POST", "/extension/ack", body, ack_headers)[0]

    response = acknowledge(first["id"])
    assert response.status == 200
    assert json.loads(request(connection, "GET", "/api/status")[1])["pending_commands"] == 1

    response, payload = request(connection, "GET", "/extension/poll", headers=bridge)
    second = json.loads(payload)[0]
    assert second["command"] == "open"
    response = acknowledge(second["id"])
    assert response.status == 200
    assert request(connection, "GET", "/extension/poll", headers=bridge)[1] == b"[]"
    final_status = json.loads(request(connection, "GET", "/api/status")[1])
    assert final_status["extension_online"] and final_status["pending_commands"] == 0
    for command in ('{"command":"home"}', '{"command":"back"}'):
        assert request(connection, "POST", "/api/command", command, headers)[0].status == 202
    failed = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])[0]
    assert acknowledge(failed["id"], "failed", "operation").status == 200
    status = json.loads(request(connection, "GET", "/api/status")[1])
    assert status["last_command_failure"] == {"outcome": "failed", "reason": "operation"}
    assert "service_id" not in status["last_command_failure"]
    following = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])[0]
    assert following["command"] == "back"
    assert acknowledge(following["id"]).status == 200
    retained = json.loads(request(connection, "GET", "/api/status")[1])
    assert retained["last_command_failure"] == {"outcome": "failed", "reason": "operation"}


def test_player_result_requires_auth_and_matches_ack(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = endpoint
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    response, body = request(
        connection, "POST", "/api/command", '{"command":"player_get"}', headers
    )
    assert response.status == 202
    command_id = json.loads(body)["id"]
    route = f"/api/command-result?id={command_id}"
    remote_host = {"Host": f"192.168.1.50:{port}"}
    assert request(connection, "GET", route, headers=remote_host)[0].status == 403
    assert request(connection, "GET", route)[0].status == 202
    assert (
        request(connection, "GET", route, headers={**remote_host, "Cookie": cookie})[0].status
        == 202
    )
    bridge = {"Host": f"127.0.0.1:{port}", BRIDGE_HEADER: BRIDGE_VALUE}
    item = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])[0]
    assert item["id"] == command_id and item["command"] == "player_get"
    ack = json.dumps({"id": command_id, "outcome": "completed", "reason": None, "volume": 55})
    assert (
        request(
            connection,
            "POST",
            "/extension/ack",
            ack,
            {**bridge, "Content-Type": "application/json"},
        )[0].status
        == 200
    )
    response, body = request(connection, "GET", route, headers={**remote_host, "Cookie": cookie})
    assert response.status == 200
    assert json.loads(body) == {
        "id": command_id,
        "outcome": "completed",
        "reason": None,
        "volume": 55,
    }
