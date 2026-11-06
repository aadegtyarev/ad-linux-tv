"""A phone retired by a PIN change cannot finish an in-flight key operation."""

import copy
import inspect
import json
import threading
from contextlib import contextmanager
from http.client import HTTPConnection
from types import SimpleNamespace

import yaml
from conftest import login, make_config, request
from test_remote_socket import connect, receive_message, send_message
from test_tv_shortcut_learner import FakeProcess, FakeTimer

from ad_linux_tv.listener import make_server
from ad_linux_tv.server import make_handler


@contextmanager
def server_with_two_sockets(tmp_path, monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.delenv("AD_LINUX_TV_PIN_FILE", raising=False)
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
    child = FakeProcess()
    handler.tv_shortcut_learner._popen = lambda *_args, **_kwargs: child
    handler.tv_shortcut_learner._timer_factory = FakeTimer
    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = HTTPConnection("127.0.0.1", server.server_port)
    first = second = first_stream = second_stream = None
    try:
        _response, session, cookie = login(conn, server.server_port)
        first, first_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        second, second_stream, status = connect(server.server_port, cookie, session["csrf"])
        assert " 101 " in status
        yield handler, child, path, original, first, first_stream, second, second_stream
    finally:
        for stream in (first_stream, second_stream):
            if stream is not None:
                stream.close()
        for sock in (first, second):
            if sock is not None:
                sock.close()
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def message(sock, number, path, body):
    send_message(sock, {"id": number, "method": "POST", "path": path, "body": body})


def pin_off(sock):
    message(
        sock,
        99,
        "/api/settings",
        {"setting": "pin", "value": {"enabled": False, "pin": None, "confirm": None}},
    )


def test_learning_result_rechecks_session_after_pin_reset_before_retirement(tmp_path, monkeypatch):
    from ad_linux_tv.remote_rpc import RemoteDispatcher

    entered, proceed = threading.Event(), threading.Event()
    retire_entered, retire_proceed = threading.Event(), threading.Event()
    original_dispatch = RemoteDispatcher.dispatch

    def paused_dispatch(self, method, path, body):
        if path == "/api/tv-shortcut-learn" and body.get("action") == "result":
            entered.set()
            assert proceed.wait(3)
        return original_dispatch(self, method, path, body)

    monkeypatch.setattr(RemoteDispatcher, "dispatch", paused_dispatch)
    with server_with_two_sockets(tmp_path, monkeypatch) as (
        handler,
        child,
        _path,
        _original,
        a,
        ar,
        b,
        br,
    ):
        real_retire = handler.tv_shortcut_learner.retire

        def paused_retire(owner, identifier=None):
            if identifier is not None:
                retire_entered.set()
                assert retire_proceed.wait(3)
            return real_retire(owner, identifier)

        handler.tv_shortcut_learner.retire = paused_retire
        try:
            message(a, 1, "/api/tv-shortcut-learn", {"action": "start"})
            started = receive_message(ar)
            child.returncode = 0
            message(
                a, 2, "/api/tv-shortcut-learn", {"action": "result", "id": started["body"]["id"]}
            )
            assert entered.wait(2)
            pin_off(b)
            assert retire_entered.wait(2)
            proceed.set()
            result = receive_message(ar)
            assert result["status"] == 403 and "key" not in result["body"]
            retire_proceed.set()
            assert receive_message(br)["status"] == 200
        finally:
            proceed.set()
            retire_proceed.set()


def test_idle_learning_is_retired_when_session_is_evicted(tmp_path, monkeypatch):
    with server_with_two_sockets(tmp_path, monkeypatch) as (
        handler,
        child,
        _path,
        _original,
        a,
        ar,
        _b,
        _br,
    ):
        sessions = inspect.getclosurevars(handler.authorized).nonlocals["sessions"]
        sessions.max_sessions = 1
        handler.tv_shortcut_learner._timer_factory = threading.Timer
        retired = threading.Event()
        original_terminate = child.terminate

        def terminate():
            original_terminate()
            retired.set()

        child.terminate = terminate
        message(a, 1, "/api/tv-shortcut-learn", {"action": "start"})
        assert receive_message(ar)["status"] == 202
        port = a.getpeername()[1]
        new_conn = HTTPConnection("127.0.0.1", port)
        try:
            login(new_conn, port)  # max_sessions evicts the first phone without its traffic
            assert retired.wait(2)
            assert child.terminated
            assert handler.tv_shortcut_learner.snapshot() is None
        finally:
            new_conn.close()


def test_delayed_pin_cleanup_does_not_cancel_new_session_learning(tmp_path, monkeypatch):
    retire_entered, retire_proceed = threading.Event(), threading.Event()
    with server_with_two_sockets(tmp_path, monkeypatch) as (
        handler,
        old_child,
        _path,
        _original,
        a,
        ar,
        b,
        br,
    ):
        real_retire = handler.tv_shortcut_learner.retire
        children = [old_child]

        def popen(*_args, **_kwargs):
            child = FakeProcess()
            children.append(child)
            return child

        def paused_retire(owner, identifier=None):
            if identifier is not None:
                retire_entered.set()
                assert retire_proceed.wait(3)
            return real_retire(owner, identifier)

        handler.tv_shortcut_learner._popen = popen
        handler.tv_shortcut_learner.retire = paused_retire
        third = third_stream = new_conn = None
        try:
            message(a, 1, "/api/tv-shortcut-learn", {"action": "start"})
            assert receive_message(ar)["status"] == 202
            old_timer = handler.tv_shortcut_learner._active["timer"]
            pin_off(b)
            assert retire_entered.wait(2)
            old_timer.fire()
            assert children[1].terminated
            port = a.getpeername()[1]
            new_conn = HTTPConnection("127.0.0.1", port)
            response, payload = request(
                new_conn, "GET", "/api/session", headers={"Host": f"127.0.0.1:{port}"}
            )
            assert response.status == 200
            cookie = response.getheader("Set-Cookie").split(";", 1)[0]
            csrf = json.loads(payload)["csrf"]
            third, third_stream, status = connect(port, cookie, csrf)
            assert " 101 " in status
            message(third, 3, "/api/tv-shortcut-learn", {"action": "start"})
            assert receive_message(third_stream)["status"] == 202
            assert not children[2].terminated
            retire_proceed.set()
            assert receive_message(br)["status"] == 200
            assert not children[2].terminated
        finally:
            retire_proceed.set()
            if third_stream is not None:
                third_stream.close()
            if third is not None:
                third.close()
            if new_conn is not None:
                new_conn.close()


def test_shortcut_save_rechecks_session_after_pin_reset_before_settings_lock(tmp_path, monkeypatch):
    from ad_linux_tv.remote_rpc import RemoteRequest

    entered, proceed = threading.Event(), threading.Event()
    original_read = RemoteRequest.read_payload

    def paused_read(self):
        if isinstance(self.body, dict) and self.body.get("setting") == "tv_shortcuts":
            entered.set()
            assert proceed.wait(3)
        return original_read(self)

    monkeypatch.setattr(RemoteRequest, "read_payload", paused_read)
    with server_with_two_sockets(tmp_path, monkeypatch) as (
        _handler,
        _child,
        path,
        original,
        a,
        ar,
        b,
        br,
    ):
        try:
            message(
                a,
                1,
                "/api/settings",
                {
                    "setting": "tv_shortcuts",
                    "value": {"expected": {}, "assignments": {"ok": "XF86Launch1"}},
                },
            )
            assert entered.wait(2)
            pin_off(b)
            assert receive_message(br)["status"] == 200
            proceed.set()
            assert receive_message(ar)["status"] == 403
            stored = yaml.safe_load(path.read_text())
            assert "tv_shortcuts" not in stored
            assert stored["services"] == original["services"]
        finally:
            proceed.set()
