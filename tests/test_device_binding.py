"""Identity correlation prevents PIN-free bootstrap on a reassigned old address."""

import json
import threading
from http.client import HTTPConnection

from conftest import make_config

from ad_linux_tv.discovery import new_discovery
from ad_linux_tv.listener import make_server
from ad_linux_tv.security import matches_device
from ad_linux_tv.server import make_handler

ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_optional_binding_is_strict_but_legacy_is_compatible():
    config = {"discovery": {"id": ID, "enabled": False}}
    assert matches_device("/api/session", {}, {})
    assert matches_device(f"/api/session?device={ID}", {}, config)
    assert matches_device("/api/session", {"X-AD-Linux-TV-Device": ID}, config)
    for query in ("", OTHER, f"{ID}&device={ID}"):
        assert not matches_device(f"/api/session?device={query}", {}, config)
    assert not matches_device(f"/api/session?device={ID}", {}, {})
    assert not matches_device(f"/api/session?device={ID}", {"X-AD-Linux-TV-Device": OTHER}, config)


def test_wrong_device_cannot_create_session_or_submit_login(monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    config = make_config()
    config["discovery"] = new_discovery("Test TV")
    config["auth"]["require_pin"] = False
    server = make_server("127.0.0.1", 0, make_handler(config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = HTTPConnection("127.0.0.1", server.server_port)
    try:
        for method, path, body in (
            ("GET", f"/api/session?device={OTHER}", None),
            ("POST", f"/api/login?device={OTHER}", json.dumps({"pin": "0000"})),
        ):
            conn.request(method, path, body, {"Origin": f"http://127.0.0.1:{server.server_port}"})
            response = conn.getresponse()
            assert response.status == 403
            assert response.getheader("Set-Cookie") is None
            response.read()
        conn.request("GET", f"/api/session?device={config['discovery']['id']}")
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Set-Cookie")
        assert json.loads(response.read())["csrf"]
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
