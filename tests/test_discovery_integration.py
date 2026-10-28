"""Temporary configs and localhost fixtures only; no installed TV or real mDNS."""

import json
import threading
from http.client import HTTPConnection

import pytest
from conftest import make_config
from test_config_edges import make_data, write_config

from ad_linux_tv import cli
from ad_linux_tv.config import load_config
from ad_linux_tv.discovery import new_discovery
from ad_linux_tv.listener import make_server
from ad_linux_tv.server import make_handler


def invoke(monkeypatch, path, command, *args):
    monkeypatch.setattr("sys.argv", ["ad-linux-tv", command, "--config", str(path), *args])
    cli.main()


def test_cli_discovery_id_persists_and_legacy_load_does_not_mutate(tmp_path, monkeypatch):
    path = write_config(tmp_path, make_data())
    original = path.read_bytes()
    assert "discovery" not in load_config(path) and path.read_bytes() == original
    invoke(monkeypatch, path, "enable-discovery", "--discovery-name", "Спальня")
    first = load_config(path)
    identity = first["discovery"]["id"]
    assert first["discovery"]["enabled"] and first["discovery"]["name"] == "Спальня"
    assert path.stat().st_mode & 0o777 == 0o600
    invoke(monkeypatch, path, "disable-discovery")
    assert load_config(path)["discovery"] == dict(first["discovery"], enabled=False)
    invoke(monkeypatch, path, "enable-discovery", "--discovery-name", "Гостиная")
    last = load_config(path)
    assert last["discovery"]["id"] == identity
    assert all(last[k] == first[k] for k in first if k != "discovery")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        invoke(monkeypatch, path, "enable-discovery", "--discovery-name", "x\ny")
    assert path.read_bytes() == before


def test_new_init_has_identity_but_disabling_unconfigured_legacy_is_noop(tmp_path, monkeypatch):
    path = tmp_path / "fresh.yaml"
    invoke(monkeypatch, path, "init-config")
    first = load_config(path)
    assert first["discovery"]["enabled"] is True
    with pytest.raises(FileExistsError):
        invoke(monkeypatch, path, "init-config")
    assert load_config(path)["discovery"]["id"] == first["discovery"]["id"]
    legacy = write_config(tmp_path, make_data())
    before = legacy.read_bytes()
    invoke(monkeypatch, legacy, "disable-discovery")
    assert legacy.read_bytes() == before


@pytest.mark.parametrize("value", [None, {}, {"enabled": True}, True])
def test_config_rejects_invalid_discovery(tmp_path, value):
    data = make_data()
    data["discovery"] = value
    with pytest.raises(ValueError, match="discovery"):
        load_config(write_config(tmp_path, data))


def test_device_identity_endpoint_has_no_session_or_secrets_and_rejects_wrong_host():
    data = make_config()
    data["discovery"] = new_discovery("TV")
    server = make_server("127.0.0.1", 0, make_handler(data))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = HTTPConnection("127.0.0.1", server.server_port)
    try:
        conn.request("GET", "/api/device")
        response = conn.getresponse()
        identity = json.loads(response.read())
        assert response.status == 200 and response.getheader("Set-Cookie") is None
        assert identity["id"] == data["discovery"]["id"]
        assert identity["port"] == server.server_port and identity["remote_path"] == "/remote"
        assert not {"csrf", "auth", "verifier", "salt", "pin"} & set(identity)
        conn.request(
            "GET", "/api/device", headers={"Host": f"attacker.example:{server.server_port}"}
        )
        response = conn.getresponse()
        assert response.status == 403
        response.read()
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_legacy_device_endpoint_requests_explicit_configuration(endpoint):
    conn, _ = endpoint
    conn.request("GET", "/api/device")
    response = conn.getresponse()
    assert response.status == 503
    assert json.loads(response.read()) == {"error": "discovery_not_configured"}


def test_listener_closes_owned_discovery_and_sockets_on_exit(monkeypatch):
    from ad_linux_tv import listener

    calls = []

    class Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            calls.append("socket-close")

    class Announcer:
        def __init__(self, _config):
            pass

        def start(self):
            calls.append("advertise-start")

        def close(self):
            calls.append("advertise-close")

    monkeypatch.delenv("AD_LINUX_TV_KIOSK", raising=False)
    monkeypatch.setattr(listener, "make_handler", lambda *_args: object())
    monkeypatch.setattr(listener, "make_server", lambda *_args: Server())
    monkeypatch.setattr(listener, "DiscoveryAnnouncer", Announcer)
    with pytest.raises(KeyboardInterrupt):
        listener.serve(make_config())
    assert calls == ["advertise-start", "advertise-close", "socket-close"]
