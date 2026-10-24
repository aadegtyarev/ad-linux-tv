"""Loopback-only bridge lease and acknowledgement endpoints."""

import json

from conftest import command_headers, login, request

from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE


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
    response, _ = request(
        connection, "POST", "/extension/ack", json.dumps({"id": first["id"]}), ack_headers
    )
    assert response.status == 200
    assert json.loads(request(connection, "GET", "/api/status")[1])["pending_commands"] == 1

    response, payload = request(connection, "GET", "/extension/poll", headers=bridge)
    second = json.loads(payload)[0]
    assert second["command"] == "open"
    response, _ = request(
        connection, "POST", "/extension/ack", json.dumps({"id": second["id"]}), ack_headers
    )
    assert response.status == 200
    assert request(connection, "GET", "/extension/poll", headers=bridge)[1] == b"[]"
    final_status = json.loads(request(connection, "GET", "/api/status")[1])
    assert final_status["extension_online"] and final_status["pending_commands"] == 0
