"""Shared manager construction and partial listener lifecycle without a system bus."""

from types import SimpleNamespace

import pytest
from conftest import make_config
from test_bluetooth_manager import Transport

from ad_linux_tv import listener, server
from ad_linux_tv.bluetooth_manager import Principal


def test_handler_constructs_one_inert_manager_for_all_connections(monkeypatch):
    transports = []

    def factory():
        transports.append(Transport())
        return transports[-1]

    monkeypatch.setattr(server, "BluezTransport", factory)
    monkeypatch.delenv("AD_LINUX_TV_PIN_FILE", raising=False)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    handler = server.make_handler(make_config())
    assert len(transports) == 1
    assert transports[0].start_count == transports[0].close_count == 0
    assert handler.bluetooth_manager._thread is None
    handler.bluetooth_manager.close()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("failure", ["", "start", "snapshot"])
def test_absent_transport_keeps_center_routes_constructible(monkeypatch, enabled, failure):
    transport = Transport()
    if failure:
        transport.fail.add(failure)
    monkeypatch.setattr(server, "BluezTransport", lambda: transport)
    monkeypatch.delenv("AD_LINUX_TV_PIN_FILE", raising=False)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1" if enabled else "0")
    handler = server.make_handler(make_config())
    manager = handler.bluetooth_manager
    try:
        manager.start()
        manager.tick()
        principal = Principal("phone", "synthetic-session")
        status, reply = manager.request(principal, {"op": "acquire"})
        if enabled and not failure:
            assert status == 200
        else:
            assert status == 503 and reply["error"] == "unavailable"
        assert transport.start_count == int(enabled)
    finally:
        manager.close()
    if enabled:
        assert not manager._thread.is_alive()
        assert transport.close_count == 1
    else:
        assert manager._thread is None and transport.close_count == 0


@pytest.mark.parametrize(
    "failure",
    [
        "discovery_construct",
        "listen1",
        "listen2",
        "manager_start",
        "background_start",
        "discovery_start",
        "foreground",
        "manager_close",
        "discovery_close",
    ],
)
def test_listener_closes_manager_and_all_partial_resources(monkeypatch, failure):
    calls, sockets = [], []

    def record(name):
        calls.append(name)
        if name == failure:
            raise RuntimeError("synthetic failure")

    class Manager:
        def start(self):
            record("manager_start")

        def close(self):
            record("manager_close")

    class Discovery:
        def __init__(self, config):
            record("discovery_construct")

        def start(self):
            record("discovery_start")

        def close(self):
            record("discovery_close")

    class Socket:
        def serve_forever(self):
            record("foreground")
            raise KeyboardInterrupt

        def shutdown(self):
            calls.append("background_shutdown")

        def server_close(self):
            calls.append("socket_close")

    def make_socket(*args):
        record(f"listen{len(sockets) + 1}")
        result = Socket()
        sockets.append(result)
        return result

    class Thread:
        def __init__(self, **kw):
            self.kw = kw

        def start(self):
            record("background_start")

    manager = Manager()
    monkeypatch.delenv("AD_LINUX_TV_KIOSK", raising=False)
    monkeypatch.setattr(
        listener, "make_handler", lambda *args: SimpleNamespace(bluetooth_manager=manager)
    )
    monkeypatch.setattr(listener, "make_server", make_socket)
    monkeypatch.setattr(listener, "DiscoveryAnnouncer", Discovery)
    monkeypatch.setattr(listener, "Thread", Thread)
    config = dict(make_config(), bind="192.168.1.2")
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        listener.serve(config)
    assert calls.count("manager_close") == 1
    assert calls.count("socket_close") == len(sockets)
    if failure != "discovery_construct":
        assert calls.count("discovery_close") == 1
    if "discovery_start" in calls:
        assert calls.count("background_shutdown") == 1
    if "manager_start" in calls:
        assert calls.index("manager_start") > calls.index("listen2")


def test_generic_authenticated_bluetooth_is_bounded_unavailable(monkeypatch, endpoint):
    import json

    from conftest import command_headers, login, request

    monkeypatch.delenv("AD_LINUX_TV_KIOSK", raising=False)
    connection, port = endpoint
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    headers.update(Host=f"localhost:{port}", Origin=f"http://localhost:{port}")
    response, payload = request(connection, "POST", "/api/bluetooth", '{"op":"acquire"}', headers)
    assert response.status == 503
    assert json.loads(payload)["state"]["devices"] == []
    response, payload = request(connection, "GET", "/api/bluetooth", headers=headers)
    assert response.status == 200 and not json.loads(payload)["state"]["available"]
    response, _ = request(connection, "GET", "/api/bluetooth")
    assert response.status == 403  # local exemption is kiosk-only
    response, _ = request(connection, "GET", "/api/services")
    assert response.status == 200
