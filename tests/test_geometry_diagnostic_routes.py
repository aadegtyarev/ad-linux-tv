"""Local geometry diagnostics must not appear in public status."""

import json
import threading
from http.client import HTTPConnection

from conftest import make_config, request
from test_video_panel_routes import overlay_headers

from ad_linux_tv.control import FAILURE_TTL_SECONDS
from ad_linux_tv.listener import make_server
from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE
from ad_linux_tv.server import make_handler

PATH = "/api/local-video-geometry-diagnostic"


def test_geometry_diagnostic_is_local_bounded_and_public_status_is_redacted(monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    handler = make_handler(make_config())
    queue = handler.tv_video_menu._queue
    monkeypatch.setattr(queue.browser_media, "status", lambda: {"media_id": "a" * 32})
    monkeypatch.setattr(queue.browser_media, "capabilities", lambda: ["video_geometry_v1"])

    def admit():
        return queue.push_geometry("a" * 32, "16:9", False)

    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    headers = overlay_headers(server.server_port)
    try:

        def diagnostic():
            response, payload = request(connection, "GET", PATH, headers=headers)
            assert response.status == 200
            assert response.getheader("Cache-Control") == "no-store"
            return json.loads(payload)

        assert diagnostic() == {"reason": None}
        command_id = admit()
        assert queue.acknowledge(command_id, "failed", "geometry_presentation_ratio")
        assert queue.geometry_result(command_id)["reason"] == "geometry_presentation_ratio"
        assert diagnostic() == {"reason": "geometry_presentation_ratio"}
        for path in ("/health", "/api/status"):
            response, payload = request(connection, "GET", path)
            assert response.status == 200
            assert json.loads(payload)["last_command_failure"] == {
                "outcome": "failed",
                "reason": "unsupported",
            }
            assert b"geometry_presentation_ratio" not in payload
            assert command_id.encode() not in payload
        bridge = {"Host": f"127.0.0.1:{server.server_port}", BRIDGE_HEADER: BRIDGE_VALUE}
        for reason in (
            "geometry_video_transform",
            "geometry_post_write_current",
            "geometry_post_write_exception",
            "geometry_post_write_closed",
            "geometry_close_mutation",
            "geometry_close_playback",
            "geometry_close_check",
            "geometry_post_write_ownership",
        ):
            command_id = admit()
            body = json.dumps({"id": command_id, "outcome": "failed", "reason": reason})
            assert request(connection, "POST", "/extension/ack", body, bridge)[0].status == 200
            assert queue.geometry_result(command_id)["reason"] == reason
            assert diagnostic() == {"reason": reason}
            assert queue.status()["last_command_failure"]["reason"] == "unsupported"
        command_id = admit()
        assert diagnostic() == {"reason": None}
        assert queue.acknowledge(command_id)
        assert diagnostic() == {"reason": None}
        assert queue.status()["last_command_failure"]["reason"] == "unsupported"
        command_id = admit()
        assert queue.acknowledge(command_id, "failed", "geometry_post_write_exception")
        assert diagnostic() == {"reason": "geometry_post_write_exception"}
        for bad in (
            {},
            {**headers, "Host": "attacker.example"},
            {**headers, "Origin": "http://attacker.example"},
            {**headers, "X-AD-Linux-TV-Video-Panel": "wrong"},
        ):
            assert request(connection, "GET", PATH, headers=bad)[0].status == 403
        with monkeypatch.context() as scoped:
            scoped.setattr(
                "ad_linux_tv.video_panel_routes.security.loopback_source", lambda _: False
            )
            assert request(connection, "GET", PATH, headers=headers)[0].status == 403
        with monkeypatch.context() as scoped:
            scoped.delenv("AD_LINUX_TV_KIOSK")
            assert request(connection, "GET", PATH, headers=headers)[0].status == 403
        assert request(connection, "GET", PATH + "?x=1", headers=headers)[0].status == 404
        queue.geometry_diagnostic["recorded_at"] -= FAILURE_TTL_SECONDS + 1
        assert diagnostic() == {"reason": None}
        command_id = admit()
        assert queue.acknowledge(command_id, "failed", "transition_busy")
        assert diagnostic() == {"reason": None}
        assert queue.status()["last_command_failure"]["reason"] == "transition_busy"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(2)
