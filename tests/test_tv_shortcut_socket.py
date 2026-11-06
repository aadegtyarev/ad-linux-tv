"""Real authenticated socket boundary and learning-operation ownership."""

import copy
import threading
from http.client import HTTPConnection
from types import SimpleNamespace

import yaml
from conftest import login, make_config
from test_remote_socket import connect, receive_message, send_message
from test_tv_shortcut_learner import FakeProcess, FakeTimer

from ad_linux_tv.listener import make_server
from ad_linux_tv.server import make_handler


def test_phone_learns_then_explicitly_saves_without_changing_other_config(tmp_path, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(
        "ad_linux_tv.settings.SettingsManager._preflight_shortcuts", lambda *_: None
    )
    monkeypatch.setattr(
        "ad_linux_tv.remote_rpc.get_media_monitor",
        lambda: SimpleNamespace(status=lambda: {"available": False}),
    )
    config = make_config()
    original = copy.deepcopy(config)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    handler = make_handler(config, path)
    children = []

    def popen(*_args, **_kwargs):
        child = FakeProcess()
        children.append(child)
        return child

    handler.tv_shortcut_learner._popen = popen
    handler.tv_shortcut_learner._timer_factory = FakeTimer
    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        _response, session, cookie = login(connection, server.server_port)
        sock, stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        try:

            def rpc(number, path, body):
                send_message(sock, {"id": number, "method": "POST", "path": path, "body": body})
                return receive_message(stream)

            started = rpc(1, "/api/tv-shortcut-learn", {"action": "start"})
            identifier = started["body"]["id"]
            assert started["status"] == 202 and yaml.safe_load(path.read_text()) == config
            children[0].returncode = 0
            learned = rpc(2, "/api/tv-shortcut-learn", {"action": "result", "id": identifier})
            assert learned["body"] == {"state": "ready", "key": "XF86Launch1"}
            assert "tv_shortcuts" not in yaml.safe_load(path.read_text())
            saved = rpc(
                3,
                "/api/settings",
                {
                    "setting": "tv_shortcuts",
                    "value": {"expected": {}, "assignments": {"video_panel": "XF86Launch1"}},
                },
            )
            assert saved["status"] == 200
            assert saved["body"]["tv_shortcuts_restart_required"] is True
            stored = yaml.safe_load(path.read_text())
            assert stored.pop("tv_shortcuts") == {"video_panel": "XF86Launch1"}
            assert stored == original
        finally:
            stream.close()
            sock.close()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_pin_change_on_another_phone_cancels_idle_learning_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.delenv("AD_LINUX_TV_PIN_FILE", raising=False)
    monkeypatch.setattr(
        "ad_linux_tv.remote_rpc.get_media_monitor",
        lambda: SimpleNamespace(status=lambda: {"available": False}),
    )
    config = make_config()
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    handler = make_handler(config, path)
    retired = threading.Event()

    class Process(FakeProcess):
        def terminate(self):
            super().terminate()
            retired.set()

    child = Process()
    handler.tv_shortcut_learner._popen = lambda *_args, **_kwargs: child
    handler.tv_shortcut_learner._timer_factory = FakeTimer
    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        _response, session, cookie = login(connection, server.server_port)
        first, first_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        second, second_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        try:
            send_message(
                first,
                {
                    "id": 1,
                    "method": "POST",
                    "path": "/api/tv-shortcut-learn",
                    "body": {"action": "start"},
                },
            )
            assert receive_message(first_stream)["status"] == 202
            send_message(
                second,
                {
                    "id": 2,
                    "method": "POST",
                    "path": "/api/settings",
                    "body": {
                        "setting": "pin",
                        "value": {"enabled": False, "pin": None, "confirm": None},
                    },
                },
            )
            assert receive_message(second_stream)["status"] == 200
            assert retired.wait(1), "PIN change must retire an idle learner on the other socket"
            assert child.terminated
        finally:
            first_stream.close()
            first.close()
            second_stream.close()
            second.close()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_learning_is_scoped_to_one_authenticated_socket_and_retired_on_close(monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(
        "ad_linux_tv.remote_rpc.get_media_monitor",
        lambda: SimpleNamespace(status=lambda: {"available": False}),
    )
    handler = make_handler(make_config())
    children = []
    retired = threading.Event()

    class Process(FakeProcess):
        def terminate(self):
            super().terminate()
            retired.set()

    def popen(*_args, **_kwargs):
        child = Process()
        children.append(child)
        return child

    handler.tv_shortcut_learner._popen = popen
    handler.tv_shortcut_learner._timer_factory = FakeTimer
    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = HTTPConnection("127.0.0.1", server.server_port)
    try:
        _response, session, cookie = login(conn, server.server_port)
        first, first_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        second, second_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        try:

            def rpc(sock, stream, number, body):
                send_message(
                    sock,
                    {
                        "id": number,
                        "method": "POST",
                        "path": "/api/tv-shortcut-learn",
                        "body": body,
                    },
                )
                return receive_message(stream)

            started = rpc(first, first_stream, 1, {"action": "start"})
            assert started["status"] == 202
            identifier = started["body"]["id"]
            assert (
                rpc(second, second_stream, 2, {"action": "result", "id": identifier})["status"]
                == 503
            )
            assert (
                rpc(second, second_stream, 3, {"action": "cancel", "id": identifier})["status"]
                == 409
            )
            assert rpc(first, first_stream, 4, {"action": "result", "id": identifier})["body"] == {
                "state": "waiting"
            }
            assert rpc(second, second_stream, 5, {"action": "start"})["status"] == 409
        finally:
            first_stream.close()
            first.close()
            second_stream.close()
            second.close()
        assert retired.wait(3), "closing the owner's socket must terminate its learner"
        assert children[0].terminated
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(2)
