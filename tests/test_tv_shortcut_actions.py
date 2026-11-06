"""The three fixed shortcut payloads reach their existing server actions."""

import json
import time
from subprocess import CompletedProcess

from conftest import request
from test_video_panel_routes import overlay_headers

from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE


def test_local_fixed_actions_reuse_panel_magnifier_and_fullscreen(endpoint, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    called = []
    monkeypatch.setattr(
        "ad_linux_tv.settings.subprocess.run",
        lambda args, **_kwargs: (called.append(args), CompletedProcess(args, 0))[1],
    )
    connection, port = endpoint
    host = f"127.0.0.1:{port}"
    local = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json"}
    panel = overlay_headers(port)
    assert request(connection, "GET", "/api/local-video-panel", headers=panel)[0].status == 200
    response, body = request(
        connection, "POST", "/api/local-video-panel", '{"action":"open"}', panel
    )
    assert response.status == 200 and json.loads(body)["visible"] is True
    response, body = request(
        connection, "POST", "/api/settings", '{"setting":"magnifier_toggle","value":true}', local
    )
    assert response.status == 200 and json.loads(body)["magnifier"] is True
    assert called == [["/usr/bin/wtype", "-k", "F9"]]
    assert (
        request(connection, "POST", "/api/command", '{"command":"fullscreen"}', local)[0].status
        == 409
    )
    bridge = {"Host": host, BRIDGE_HEADER: BRIDGE_VALUE, "Content-Type": "application/json"}
    now = int(time.time() * 1000)
    report = {
        "protocol": 1,
        "sequence": now,
        "sent_at": now,
        "capabilities": ["video_fullscreen_v1"],
        "media": None,
    }
    assert (
        request(connection, "POST", "/extension/media", json.dumps(report), bridge)[0].status == 200
    )
    response, _body = request(connection, "POST", "/api/command", '{"command":"fullscreen"}', local)
    assert response.status == 202
    commands = json.loads(request(connection, "GET", "/extension/poll", headers=bridge)[1])
    assert len(commands) == 1 and commands[0]["command"] == "fullscreen"
