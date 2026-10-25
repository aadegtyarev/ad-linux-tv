"""Private settings validation, persistence and session boundaries."""

from subprocess import CompletedProcess

import pytest
import yaml
from test_config_edges import make_data

from ad_linux_tv.auth_state import Sessions
from ad_linux_tv.config import load_config, verify_pin
from ad_linux_tv.settings import SettingsError, SettingsManager, validate_proxy


def manager(tmp_path):
    path = tmp_path / "config.yaml"
    data = make_data()
    data["auth"]["require_pin"] = False
    path.write_text(yaml.safe_dump(data))
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "user.js").write_text(
        'user_pref("network.proxy.type", 1);\n'
        'user_pref("network.proxy.http", "127.0.0.1");\n'
        'user_pref("network.proxy.http_port", 1081);\n'
        'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n'
    )
    sessions = Sessions(storage_path=tmp_path / "sessions.json", auth_tag="old")
    settings = SettingsManager(load_config(path), path, sessions, tmp_path / "pin.txt", profile)
    return settings, sessions, path, profile


def test_pin_change_is_private_and_invalidates_phone_sessions(tmp_path):
    settings, sessions, path, _profile = manager(tmp_path)
    token, _csrf = sessions.create()
    assert settings.state()["require_pin"] is False
    assert "verifier" not in settings.state()
    with pytest.raises(SettingsError):
        settings.update(
            {"setting": "pin", "value": {"enabled": True, "pin": "1234", "confirm": "4321"}}
        )
    assert sessions.valid(token)
    settings.update(
        {"setting": "pin", "value": {"enabled": True, "pin": "1234", "confirm": "1234"}}
    )
    assert not sessions.valid(token)
    assert verify_pin("1234", load_config(path)["auth"])
    assert (tmp_path / "pin.txt").read_text() == "1234\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "pin.txt").stat().st_mode & 0o777 == 0o600
    token, _ = sessions.create()
    settings.update({"setting": "pin", "value": {"enabled": False, "pin": None, "confirm": None}})
    assert not sessions.valid(token)
    assert load_config(path)["auth"]["require_pin"] is False


def test_proxy_modes_preserve_other_firefox_prefs_and_reject_bad_input(tmp_path):
    settings, _sessions, path, profile = manager(tmp_path)
    assert settings.state()["proxy"] == {
        "mode": "custom",
        "protocol": "http",
        "host": "127.0.0.1",
        "port": 1081,
    }
    with pytest.raises(SettingsError):
        settings.update(
            {
                "setting": "proxy",
                "value": {"mode": "custom", "protocol": "http", "host": "bad/user", "port": 80},
            }
        )
    assert "proxy" not in load_config(path)
    settings.update({"setting": "proxy", "value": {"mode": "none"}})
    prefs = (profile / "user.js").read_text()
    assert 'user_pref("network.proxy.type", 0);' in prefs
    assert "network.proxy.http" not in prefs
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" in prefs
    assert settings.state()["proxy_restart_required"] is True
    settings.update(
        {
            "setting": "proxy",
            "value": {
                "mode": "custom",
                "protocol": "socks5",
                "host": "proxy.example",
                "port": 1080,
            },
        }
    )
    prefs = (profile / "user.js").read_text()
    assert 'user_pref("network.proxy.socks", "proxy.example");' in prefs
    assert 'user_pref("network.proxy.socks_remote_dns", true);' in prefs
    assert load_config(path)["proxy"]["mode"] == "custom"
    settings.update({"setting": "proxy", "value": {"mode": "system"}})
    prefs = (profile / "user.js").read_text()
    assert 'user_pref("network.proxy.type", 5);' in prefs
    assert 'user_pref("network.proxy.no_proxies_on",' in prefs
    for value in (
        {"mode": "custom", "protocol": "http", "host": "host", "port": 0},
        {"mode": "none", "host": "extra"},
    ):
        with pytest.raises(SettingsError):
            validate_proxy(value)


def test_magnifier_toggles_only_on_state_change(tmp_path, monkeypatch):
    settings, _sessions, _path, _profile = manager(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr("ad_linux_tv.settings.subprocess.run", run)
    settings.update({"setting": "magnifier", "value": True})
    settings.update({"setting": "magnifier", "value": True})
    assert calls == [["/usr/bin/wtype", "-k", "F9"]]
    assert settings.state()["magnifier"] is True
    settings.update({"setting": "magnifier", "value": False})
    assert len(calls) == 2


def test_settings_route_requires_kiosk_and_exact_local_origin(tmp_path, monkeypatch):
    import json
    import threading
    from http.client import HTTPConnection

    from ad_linux_tv.listener import make_server
    from ad_linux_tv.server import make_handler

    settings, _sessions, path, _profile = manager(tmp_path)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setenv("AD_LINUX_TV_PIN_FILE", str(tmp_path / "pin.txt"))
    server = make_server("127.0.0.1", 0, make_handler(settings.config, path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        connection.request("GET", "/api/settings")
        response = connection.getresponse()
        state = json.loads(response.read())
        assert response.status == 200 and state["require_pin"] is False
        assert "verifier" not in state
        action = json.dumps({"setting": "magnifier", "value": False})
        connection.request("POST", "/api/settings", action, {"Origin": "http://evil.example"})
        response = connection.getresponse()
        response.read()
        assert response.status == 403
        connection.request("POST", "/api/settings", action, {"Origin": origin})
        response = connection.getresponse()
        response.read()
        assert response.status == 200
    finally:
        connection.close()
        server.shutdown()
