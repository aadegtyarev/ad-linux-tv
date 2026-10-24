"""HTTP security and command endpoint integration tests."""

from subprocess import CompletedProcess

from conftest import command_headers, login, request


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
