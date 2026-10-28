"""HTTP security and command endpoint integration tests."""

import json
from subprocess import CompletedProcess

from conftest import command_headers, login, make_config, request

from ad_linux_tv.settings import SettingsManager


def test_public_services_and_login_ignore_forwarded_headers(endpoint):
    connection, port = endpoint
    response, payload = request(connection, "GET", "/api/services")
    assert response.status == 200
    assert b"verifier" not in payload and b"salt" not in payload
    response, result, cookie = login(connection, port, forwarded="8.8.8.8")
    assert response.status == 200 and result["csrf"] and cookie.startswith("session=")
    cookie_header = response.getheader("Set-Cookie")
    assert "Secure" not in cookie_header
    assert "HttpOnly" in cookie_header and "SameSite=Strict" in cookie_header
    assert "Max-Age=1209600" in cookie_header
    response, _ = request(connection, "GET", "/api/session")
    assert response.status == 401
    response, payload = request(connection, "GET", "/api/session", headers={"Cookie": cookie})
    assert response.status == 200 and json.loads(payload)["csrf"] == result["csrf"]


def test_pin_free_session_requires_private_source_and_keeps_csrf(monkeypatch):
    import threading
    from http.client import HTTPConnection

    import ad_linux_tv.post_routes as post_routes
    import ad_linux_tv.server as server_module
    from ad_linux_tv.listener import make_server

    config = make_config()
    config["auth"]["require_pin"] = False
    server = make_server("127.0.0.1", 0, server_module.make_handler(config))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        response, body = request(connection, "GET", "/api/session")
        assert response.status == 200
        csrf = json.loads(body)["csrf"]
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        assert csrf and cookie.startswith("session=")
        response, _ = request(
            connection, "GET", "/api/session", headers={"Host": "attacker.example"}
        )
        assert response.status == 403
        response, _ = request(
            connection,
            "POST",
            "/api/login",
            '{"pin":"1234"}',
            {"Origin": f"http://127.0.0.1:{server.server_port}"},
        )
        assert response.status == 403
        monkeypatch.setattr(server_module.security, "private_source", lambda _source: False)
        response, _ = request(connection, "GET", "/api/session")
        assert response.status == 403
        monkeypatch.undo()
        monkeypatch.setattr(post_routes, "loopback_source", lambda _source: False)
        headers = command_headers(server.server_port, cookie, csrf)
        response, _ = request(connection, "POST", "/api/command", '{"command":"home"}', headers)
        assert response.status == 202
        headers["X-CSRF-Token"] = "bad"
        response, _ = request(connection, "POST", "/api/command", '{"command":"home"}', headers)
        assert response.status == 403
    finally:
        connection.close()
        server.shutdown()


def test_pairing_pin_is_local_only(endpoint, monkeypatch, tmp_path):
    import ad_linux_tv.pages as pages

    connection, port = endpoint
    pin_file = tmp_path / "remote-pin.txt"
    pin_file.write_text("1234\n")
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setenv("AD_LINUX_TV_PIN_FILE", str(pin_file))
    headers = {"X-TV-Launcher": "1"}
    response, body = request(connection, "GET", "/api/local-pin", headers=headers)
    assert response.status == 200 and json.loads(body) == {"pin": "1234"}
    assert response.getheader("Cache-Control") == "no-store"
    for denied in ({}, {"Host": "attacker.example", **headers}):
        response, body = request(connection, "GET", "/api/local-pin", headers=denied)
        assert response.status == 403 and b"1234" not in body
    monkeypatch.setattr(pages, "loopback_source", lambda _source: False)
    response, body = request(connection, "GET", "/api/local-pin", headers=headers)
    assert response.status == 403 and b"1234" not in body
    monkeypatch.setattr(pages, "loopback_source", lambda _source: True)
    pin_file.unlink()
    response, body = request(connection, "GET", "/api/local-pin", headers=headers)
    assert response.status == 503 and b"1234" not in body


def test_rate_limit_locks_out_bad_pin(endpoint):
    connection, port = endpoint
    headers = {
        "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{port}",
    }
    response, _ = request(connection, "POST", "/api/login", '{"pin":"wrong"}', headers)
    assert response.status == 401
    response, _ = request(connection, "POST", "/api/login", '{"pin":"1234"}', headers)
    assert response.status == 429


def test_fullscreen_command_requires_bridge_capability(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes
    from ad_linux_tv.browser_media import BrowserMedia

    monkeypatch.setattr(post_routes, "loopback_source", lambda _address: False)
    connection, port = endpoint
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    body = '{"command":"fullscreen"}'
    monkeypatch.setattr(BrowserMedia, "capabilities", lambda _self: ["html_media_v1"])
    response, _ = request(connection, "POST", "/api/command", body, headers)
    assert response.status == 409
    monkeypatch.setattr(BrowserMedia, "capabilities", lambda _self: ["video_fullscreen_v1"])
    response, reply = request(connection, "POST", "/api/command", body, headers)
    assert response.status == 202 and json.loads(reply)["id"]


def test_rejects_dns_rebinding_local_origin(endpoint):
    connection, _ = endpoint
    headers = {"Host": "attacker.example", "Origin": "http://attacker.example"}
    response, _ = request(connection, "POST", "/api/login", '{"pin":"1234"}', headers)
    assert response.status == 403


def test_command_requires_origin_csrf_and_allowed_service(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes

    monkeypatch.setattr(post_routes, "loopback_source", lambda _address: False)
    connection, port = endpoint
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    body = '{"command":"open","service_id":"unknown"}'
    response, _ = request(connection, "POST", "/api/command", body, headers)
    assert response.status == 400
    headers["Origin"] = "http://attacker.example"
    response, _ = request(connection, "POST", "/api/command", '{"command":"home"}', headers)
    assert response.status == 403
    headers = command_headers(port, cookie, "wrong")
    response, _ = request(connection, "POST", "/api/command", '{"command":"home"}', headers)
    assert response.status == 403


def test_login_rejects_malformed_and_oversized_payload(endpoint):
    connection, port = endpoint
    headers = {
        "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{port}",
    }
    response, _ = request(connection, "POST", "/api/login", "{", headers)
    assert response.status == 400
    response, _ = request(connection, "POST", "/api/login", b"x" * 2049, headers)
    assert response.status == 413
    _, auth, cookie = login(connection, port)
    command = command_headers(port, cookie, auth["csrf"])
    response, _ = request(connection, "POST", "/api/command", "{", command)
    assert response.status == 400
    response, _ = request(connection, "POST", "/api/command", b"x" * 2049, command)
    assert response.status == 413


def test_kde_switch_requires_kiosk_loopback_and_exact_host(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes

    connection, port = endpoint
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr(post_routes.subprocess, "run", run)
    monkeypatch.setattr(post_routes, "kde_available", lambda: True)
    headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 403
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 202
    assert calls == [
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/systemctl",
            "--no-block",
            "start",
            "ad-linux-tv-switch-kde.service",
        ]
    ]
    headers["Host"] = "localhost"
    headers["Origin"] = "http://localhost"
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 403
    assert len(calls) == 1
    headers["Host"] = f"127.0.0.1:{port}"
    headers["Origin"] = "http://attacker.example"
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 403
    monkeypatch.setattr(post_routes, "loopback_source", lambda _address: False)
    headers["Origin"] = f"http://127.0.0.1:{port}"
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 403
    assert len(calls) == 1


def test_kde_switch_is_refused_without_a_kde_display_manager(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes

    connection, port = endpoint
    calls = []
    monkeypatch.setattr(post_routes.subprocess, "run", lambda command, **_: calls.append(command))
    monkeypatch.setattr(post_routes, "kde_available", lambda: False)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    response, _ = request(connection, "POST", "/api/system/kde", "{}", headers)
    assert response.status == 409
    assert calls == []


def test_phone_text_input_requires_auth_and_never_returns_text(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes

    connection, port = endpoint
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcess(command, 0)

    monkeypatch.setattr(post_routes.subprocess, "run", run)
    origin = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    response, _ = request(connection, "POST", "/api/input", json.dumps({"text": "секрет"}), origin)
    assert response.status == 403

    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    response, payload = request(
        connection, "POST", "/api/input", json.dumps({"text": "Поиск 42"}), headers
    )
    assert response.status == 200 and b"\xd0\x9f" not in payload
    assert calls[-1][0] == ["/usr/bin/wtype", "-"]
    assert calls[-1][1]["input"] == "Поиск 42".encode()
    response, _ = request(connection, "POST", "/api/input", '{"key":"address"}', headers)
    assert response.status == 200
    assert calls[-1][0] == ["/usr/bin/wtype", "-M", "ctrl", "-k", "l"]
    response, _ = request(connection, "POST", "/api/input", '{"key":"browser-back"}', headers)
    assert response.status == 200
    assert calls[-1][0] == ["/usr/bin/wtype", "-M", "alt", "-k", "Left", "-m", "alt"]
    response, _ = request(connection, "POST", "/api/input", '{"key":"browser-forward"}', headers)
    assert response.status == 200
    assert calls[-1][0] == ["/usr/bin/wtype", "-M", "alt", "-k", "Right", "-m", "alt"]
    for key, expected in (
        ("up", "Up"),
        ("down", "Down"),
        ("left", "Left"),
        ("right", "Right"),
        ("ok", "Return"),
        ("system", "F8"),
        ("video-fullscreen", "f"),
    ):
        response, _ = request(connection, "POST", "/api/input", json.dumps({"key": key}), headers)
        assert response.status == 200
        assert calls[-1][0] == ["/usr/bin/wtype", "-k", expected]
    response, _ = request(connection, "POST", "/api/input", '{"text":"bad\\ntext"}', headers)
    assert response.status == 400
    assert len(calls) == 20
    assert calls[-2][0] == [
        "/usr/bin/wlrctl",
        "toplevel",
        "find",
        "app_id:firefox_firefox",
        "app_id:firefox",
        "state:active",
    ]

    def no_firefox(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcess(command, 1)

    monkeypatch.setattr(post_routes.subprocess, "run", no_firefox)
    response, _ = request(connection, "POST", "/api/input", '{"key":"browser-back"}', headers)
    assert response.status == 503
    headers["X-CSRF-Token"] = "wrong"
    response, _ = request(connection, "POST", "/api/input", '{"key":"enter"}', headers)
    assert response.status == 403


def test_phone_touchpad_is_authenticated_bounded_and_targets_firefox(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes

    connection, port = endpoint
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr(post_routes.subprocess, "run", run)
    origin = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    response, _ = request(connection, "POST", "/api/pointer", '{"click":true}', origin)
    assert response.status == 403
    _, auth, cookie = login(connection, port)
    headers = command_headers(port, cookie, auth["csrf"])
    for payload, expected in (
        ({"dx": 60, "dy": -15}, ["/usr/bin/wlrctl", "pointer", "move", "60", "-15"]),
        ({"click": True}, ["/usr/bin/wlrctl", "pointer", "click"]),
        ({"scroll": 64}, ["/usr/bin/wlrctl", "pointer", "scroll", "64", "0"]),
        ({"scroll": 0, "scroll_x": 12}, ["/usr/bin/wlrctl", "pointer", "scroll", "0", "12"]),
        ({"scroll": 64, "scroll_x": -64}, ["/usr/bin/wlrctl", "pointer", "scroll", "64", "-64"]),
    ):
        response, _ = request(connection, "POST", "/api/pointer", json.dumps(payload), headers)
        assert response.status == 200
        assert calls[-1] == expected
    for payload in (
        {"dx": 601, "dy": 0},
        {"click": "yes"},
        {"scroll": 0},
        {"scroll": 65},
        {"scroll": 0, "scroll_x": 0},
        {"scroll": 1, "scroll_x": 65},
        {"scroll": 1, "scroll_x": True},
        {"scroll_x": 1},
        {"scroll": 1, "scroll_x": 1, "extra": 0},
        {"dx": True, "dy": 1},
    ):
        response, _ = request(connection, "POST", "/api/pointer", json.dumps(payload), headers)
        assert response.status == 400
    assert len(calls) == 10

    def no_firefox(command, **_kwargs):
        calls.append(command)
        return CompletedProcess(command, 1)

    monkeypatch.setattr(post_routes.subprocess, "run", no_firefox)
    response, _ = request(connection, "POST", "/api/pointer", '{"click":true}', headers)
    assert response.status == 503


def test_audio_control_requires_pairing_and_csrf(endpoint, monkeypatch):
    import ad_linux_tv.audio as audio
    import ad_linux_tv.pages as pages
    import ad_linux_tv.post_routes as post_routes

    connection, port = endpoint
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(pages, "loopback_source", lambda _address: False)
    monkeypatch.setattr(post_routes, "loopback_source", lambda _address: False)
    state = {
        "outputs": [{"id": "hdmi", "name": "HDMI"}],
        "selected": "hdmi",
        "volume": 100,
        "muted": False,
    }
    calls = []
    monkeypatch.setattr(audio, "get_state", lambda: state)
    monkeypatch.setattr(audio, "apply", lambda command: calls.append(command) or state)
    saved = []
    monkeypatch.setattr(
        SettingsManager, "set_audio_output", lambda _self, value: saved.append(value)
    )
    response, _ = request(connection, "GET", "/api/audio")
    assert response.status == 403
    _, auth, cookie = login(connection, port)
    response, body = request(connection, "GET", "/api/audio", headers={"Cookie": cookie})
    assert response.status == 200 and json.loads(body)["volume"] == 100
    headers = command_headers(port, cookie, "wrong")
    response, _ = request(connection, "POST", "/api/audio", '{"volume":45}', headers)
    assert response.status == 403 and not calls
    headers = command_headers(port, cookie, auth["csrf"])
    response, body = request(connection, "POST", "/api/audio", '{"volume":45}', headers)
    assert response.status == 200 and json.loads(body)["selected"] == "hdmi"
    assert calls == [{"volume": 45}]
    assert saved == ["hdmi"]
    headers["Origin"] = "http://attacker.example"
    response, _ = request(connection, "POST", "/api/audio", '{"volume":10}', headers)
    assert response.status == 403 and calls == [{"volume": 45}]


def test_advanced_audio_route_saves_targets_and_keeps_output_level(tmp_path, monkeypatch):
    import threading
    from http.client import HTTPConnection

    import yaml

    from ad_linux_tv import audio
    from ad_linux_tv.config import load_config
    from ad_linux_tv.listener import make_server
    from ad_linux_tv.server import make_handler

    data = make_config()
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    calls = []
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(
        audio,
        "get_state",
        lambda *_args: {
            "outputs": [{"id": "hdmi", "name": "HDMI"}],
            "selected": "hdmi",
            "volume": 80,
            "muted": False,
            "browser_volume": None,
        },
    )
    monkeypatch.setattr(audio, "normalize_browser_volume", lambda target: calls.append(target))
    monkeypatch.setattr(
        audio, "normalize_browser_mute", lambda target: calls.append(("mute", target))
    )
    monkeypatch.setattr(audio, "browser_audio_active", lambda: False)
    server = make_server("127.0.0.1", 0, make_handler(data, path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    headers = {"Origin": f"http://127.0.0.1:{server.server_port}"}
    try:
        response, body = request(connection, "GET", "/api/audio")
        assert response.status == 200 and json.loads(body)["browser_target"] == 100
        response, body = request(connection, "POST", "/api/audio", '{"browser_volume":35}', headers)
        assert response.status == 200 and json.loads(body)["volume"] == 80
        assert calls == [35] and load_config(path)["audio"]["browser"] == 35
        response, body = request(connection, "POST", "/api/audio", '{"player_volume":60}', headers)
        assert response.status == 200 and json.loads(body)["player_target"] == 60
        assert load_config(path)["audio"] == {"browser": 35, "player": 60}
        response, body = request(
            connection, "POST", "/api/audio", '{"browser_muted":true}', headers
        )
        assert response.status == 200 and json.loads(body)["browser_mute_target"] is True
        assert calls[-1] == ("mute", True)
        assert load_config(path)["audio"] == {"browser": 35, "player": 60, "browser_muted": True}
    finally:
        connection.close()
        server.shutdown()
