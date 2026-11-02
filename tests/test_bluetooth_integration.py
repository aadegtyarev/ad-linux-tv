"""Actual HTTP/ordered socket -> coordinator -> synthetic transport, never system D-Bus."""

import json
import socket
import struct
import threading
from contextlib import closing
from dataclasses import replace
from http.client import HTTPConnection
from types import SimpleNamespace

import pytest
import yaml
from conftest import command_headers, login, make_config, request
from test_bluetooth_manager import Challenge, Clock, Settings, Transport, wait_until
from test_remote_socket import connect, receive_message, send_message

from ad_linux_tv import listener, server
from ad_linux_tv.bluetooth_manager import BluetoothManager
from ad_linux_tv.bluetooth_routes import phone_principal
from ad_linux_tv.settings import SettingsManager


@pytest.fixture
def integrated(monkeypatch, tmp_path):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setenv("AD_LINUX_TV_PIN_FILE", str(tmp_path / "pin"))
    monkeypatch.setattr(
        "ad_linux_tv.remote_rpc.get_media_monitor",
        lambda: SimpleNamespace(status=lambda: {"available": False}),
    )
    transport, clock = Transport(), Clock()
    monkeypatch.setattr(server, "BluezTransport", lambda: transport)
    monkeypatch.setattr(
        server, "BluetoothManager", lambda **kw: BluetoothManager(**kw, clock=clock)
    )
    settings = []

    def settings_factory(*args, **kw):
        value = SettingsManager(*args, **kw, profile=tmp_path / "synthetic-profile")
        settings.append(value)
        return value

    monkeypatch.setattr(server, "SettingsManager", settings_factory)
    config = make_config()
    config["proxy"] = {"mode": "system"}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    handler = server.make_handler(config, path)
    manager = handler.bluetooth_manager
    calls, retired = [], []
    snapshot, operation, retire = manager.snapshot, manager.request, manager.retire

    def snapshot_spy(principal):
        calls.append(("GET", principal))
        return snapshot(principal)

    def operation_spy(principal, body):
        calls.append(("POST", principal))
        return operation(principal, body)

    def retire_spy(principal):
        result = retire(principal)
        retired.append(principal)
        return result

    manager.snapshot, manager.request, manager.retire = snapshot_spy, operation_spy, retire_spy
    httpd = listener.make_server("127.0.0.1", 0, handler)
    manager.start()
    manager.tick()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    conn = HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
    _response, auth, cookie = login(conn, httpd.server_port)
    headers = command_headers(httpd.server_port, cookie, auth["csrf"])
    tv_headers = {"Origin": headers["Origin"], "X-TV-Launcher": "1"}

    def api(body=None, method="POST", headers=None, raw=None):
        # A fresh connection makes denied/unfinished framing tests independent.
        with closing(HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)) as connection:
            response, payload = request(
                connection,
                method,
                "/api/bluetooth",
                raw if raw is not None else json.dumps(body) if method == "POST" else None,
                tv_headers if headers is None else headers,
            )
            return response.status, json.loads(payload)

    obj = SimpleNamespace(
        api=api,
        manager=manager,
        transport=transport,
        clock=clock,
        calls=calls,
        retired=retired,
        config=config,
        path=path,
        settings=settings[0],
        conn=conn,
        httpd=httpd,
        port=httpd.server_port,
        headers=headers,
        tv_headers=tv_headers,
        cookie=cookie,
        csrf=auth["csrf"],
        handler=handler,
    )
    yield obj
    conn.close()
    httpd.shutdown()
    httpd.server_close()
    thread.join(2)
    manager.close()
    assert not manager._thread.is_alive()
    assert transport.closed.is_set()


def acquire(rig, headers=None):
    status, reply = rig.api({"op": "acquire"}, headers=headers)
    assert status == 200
    return reply["lease"]


def action(rig, lease, op, **fields):
    return rig.api({"op": op, "lease": lease, **fields})


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("failure", ["public", "host", "foreign_origin", "missing_auth"])
def test_bluetooth_authority_precedes_inventory(integrated, monkeypatch, method, failure):
    rig = integrated
    headers = dict(rig.headers)
    # localhost passes direct Host, but is deliberately not literal TV authority.
    headers["Host"] = f"localhost:{rig.port}"
    headers["Origin"] = f"http://localhost:{rig.port}"
    if failure == "public":
        monkeypatch.setattr(rig.handler, "private", lambda self: False)
    elif failure == "host":
        headers["Host"] = f"attacker.example:{rig.port}"
        headers["Origin"] = f"http://attacker.example:{rig.port}"
    elif failure == "foreign_origin":
        headers["Origin"] = "http://attacker.example"
    else:
        headers.pop("Cookie")
    before = len(rig.calls)
    assert rig.api({"op": "acquire"}, method=method, headers=headers) == (403, {})
    assert len(rig.calls) == before


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("missing", ["Cookie", "X-CSRF-Token", "Origin"])
def test_direct_phone_http_requires_all_session_origin_csrf(integrated, method, missing):
    rig = integrated
    headers = dict(rig.headers, Host=f"localhost:{rig.port}", Origin=f"http://localhost:{rig.port}")
    headers.pop(missing)
    before = len(rig.calls)
    assert rig.api({"op": "acquire"}, method=method, headers=headers)[0] == 403
    assert len(rig.calls) == before


def test_tv_exact_authority_and_phone_session_identity_are_separate(integrated):
    rig = integrated
    assert rig.api(method="GET", headers={})[0] == 200
    assert rig.calls[-1][1].kind == "tv"
    assert rig.api({"op": "acquire"}, headers={"Origin": rig.tv_headers["Origin"]})[0] == 403
    assert rig.api({"op": "acquire"}, headers={"X-TV-Launcher": "1"})[0] == 403
    lease = acquire(rig)
    tv = rig.calls[-1][1]
    assert tv.kind == "tv" and tv.connection is None
    action(rig, lease, "release")
    phone_headers = dict(
        rig.headers, Host=f"localhost:{rig.port}", Origin=f"http://localhost:{rig.port}"
    )
    acquire(rig, phone_headers)
    principal = rig.calls[-1][1]
    assert principal.kind == "phone" and principal.connection is None
    assert principal == phone_principal(rig.cookie.split("=", 1)[1])
    assert rig.cookie.split("=", 1)[1] not in repr(principal)


@pytest.mark.parametrize(
    "raw,expected",
    [("x", 400), ("[]", 400), ("{", 400), ("[" * 1000 + "]" * 1000, 400), (" " * 2049, 413)],
)
def test_http_bluetooth_body_framing(integrated, raw, expected):
    assert integrated.api(raw=raw)[0] == expected


def test_http_transfer_encoding_is_rejected(integrated):
    headers = dict(integrated.tv_headers, **{"Transfer-Encoding": "chunked"})
    assert integrated.api({"op": "acquire"}, headers=headers)[0] == 400


def test_real_management_pipeline_requested_observed_and_confirmed_forget(integrated):
    rig = integrated
    saved = Settings()
    saved.saved_remote()
    rig.settings.set_bluetooth(saved.section)
    original_auth = dict(rig.config["auth"])
    lease = acquire(rig)
    status, reply = action(rig, lease, "discover")
    assert status == 202 and reply["state"]["operation"]["phase"] == "queued"
    operation_id = reply["state"]["operation"]["id"]
    assert rig.transport.calls[-1][0] == "discover"
    assert action(rig, lease, "cancel", operation_id=operation_id)[0] == 200
    status, reply = action(rig, lease, "pair", device_id="device")
    operation_id = reply["state"]["operation"]["id"]
    assert status == 202 and not reply["state"]["devices"][0]["paired"]
    rig.transport.emit("challenge", operation_id, challenge=Challenge(kind="pin"))
    status, private = action(rig, lease, "poll")
    assert private["challenge"]["kind"] == "pin"
    assert set(rig.api(method="GET")[1]) == {"state"}
    assert "challenge" not in rig.api(method="GET")[1]
    assert (
        action(
            rig,
            lease,
            "answer",
            operation_id=operation_id,
            challenge_id="challenge",
            answer={"pin": "1234"},
        )[0]
        == 202
    )
    assert rig.transport.calls[-1][0] == "answer"
    rig.transport.emit("accepted", operation_id)
    assert not action(rig, lease, "poll")[1]["state"]["devices"][0]["paired"]
    rig.transport.device(paired=True)
    rig.transport.emit("paired", operation_id)
    rig.transport.emit("finished", operation_id, code="observed")
    assert action(rig, lease, "poll")[1]["state"]["devices"][0]["paired"]
    status, reply = action(rig, lease, "connect", device_id="device")
    operation_id = reply["state"]["operation"]["id"]
    assert status == 202 and not reply["state"]["devices"][0]["connected"]
    rig.transport.device(connected=True)
    rig.transport.emit("connected", operation_id)
    rig.transport.emit("finished", operation_id, code="observed")
    assert action(rig, lease, "poll")[1]["state"]["devices"][0]["connected"]
    status, reply = action(rig, lease, "forget_prepare", device_id="device")
    operation_id = reply["state"]["operation"]["id"]
    assert status == 200 and not any(call[0] == "forget" for call in rig.transport.calls)
    status, reply = action(
        rig,
        lease,
        "forget_confirm",
        operation_id=operation_id,
        confirmation_id=reply["confirmation_id"],
    )
    assert status == 202 and reply["state"]["devices"][0]["paired"]
    rig.transport.state = replace(rig.transport.state, devices=())
    rig.transport.emit("forgotten", operation_id)
    rig.manager.tick()
    assert not action(rig, lease, "poll")[1]["state"]["devices"]
    assert rig.settings.bluetooth_config() == {"remote": None}
    stored = yaml.safe_load(rig.path.read_text())
    assert stored["auth"] == original_auth and stored["proxy"] == {"mode": "system"}


@pytest.mark.parametrize(
    "kind,answer",
    [
        ("pin", {"pin": "1234"}),
        ("passkey", {"passkey": "123456"}),
        ("confirmation", {"confirm": True}),
        ("display_pin", None),
        ("display_passkey", None),
    ],
)
def test_pairing_challenge_envelopes_remain_owner_only(integrated, kind, answer):
    rig = integrated
    lease = acquire(rig)
    reply = action(rig, lease, "pair", device_id="device")[1]
    op = reply["state"]["operation"]["id"]
    value = (
        "123456"
        if kind in ("confirmation", "display_passkey")
        else "1234"
        if kind == "display_pin"
        else ""
    )
    rig.transport.emit("challenge", op, challenge=Challenge(kind=kind, value=value))
    private = action(rig, lease, "poll")[1]
    assert private["challenge"]["kind"] == kind
    assert "challenge" not in rig.api(method="GET")[1]
    if answer is not None:
        assert (
            action(rig, lease, "answer", operation_id=op, challenge_id="challenge", answer=answer)[
                0
            ]
            == 202
        )
    else:
        assert (
            action(
                rig,
                lease,
                "answer",
                operation_id=op,
                challenge_id="challenge",
                answer={"confirm": True},
            )[0]
            == 400
        )
    assert action(rig, lease, "cancel", operation_id=op)[0] == 200
    assert "challenge" not in action(rig, lease, "poll")[1]


def test_helper_absence_and_pending_proof_cancellation_remain_honest(integrated):
    rig = integrated
    saved = Settings()
    saved.saved_remote()
    rig.settings.set_bluetooth(saved.section)
    rig.transport.device(paired=True, connected=True)
    lease = acquire(rig)
    for op, fields, expected in [
        ("select_remote", {"device_id": "device"}, 503),
        ("learn", {"action": "ok"}, 503),
        ("bind", {"operation_id": "old", "observation_id": "old"}, 409),
        ("test", {"operation_id": "old", "observation_id": "old"}, 409),
    ]:
        status, reply = action(rig, lease, op, **fields)
        assert status == expected and "observation" not in reply
    assert rig.settings.bluetooth_config() == saved.section
    reply = action(rig, lease, "disconnect", device_id="device")[1]
    op = reply["state"]["operation"]["id"]
    with rig.manager._lock:
        rig.transport.emit("disconnected", op)
        rig.transport.emit("finished", op, code="uncertain")
    reply = action(rig, lease, "poll")[1]
    assert reply["state"]["operation"]["phase"] == "finished"
    assert reply["state"]["operation"]["remaining_ms"] > 0
    assert action(rig, lease, "discover")[0] == 409
    assert (
        action(rig, lease, "cancel", operation_id=op)[1]["state"]["operation"]["remaining_ms"] == 0
    )
    rig.transport.device(connected=False)
    rig.transport.emit("disconnected", op)
    assert action(rig, lease, "discover")[0] == 202


def ws_request(sock, stream, body=None, method="POST", path="/api/bluetooth", number=1):
    send_message(sock, {"id": number, "method": method, "path": path, "body": body})
    return receive_message(stream)


def test_ordered_socket_principal_is_unique_stable_and_retired_exactly(integrated):
    rig = integrated
    first, stream, status = connect(rig.port, rig.cookie, rig.csrf)
    second, other, status2 = connect(rig.port, rig.cookie, rig.csrf)
    assert " 101 " in status and " 101 " in status2
    try:
        reply = ws_request(first, stream, {"op": "acquire"})
        lease = reply["body"]["lease"]
        principal = rig.calls[-1][1]
        assert principal.kind == "phone" and principal.connection
        reply = ws_request(second, other, {"op": "acquire"})
        different = rig.calls[-1][1]
        assert reply["status"] == 409
        assert different.owner == principal.owner and different.connection != principal.connection
        other.close()
        second.close()
        wait_until(lambda: different in rig.retired)
        reply = ws_request(first, stream, {"op": "discover", "lease": lease})
        assert reply["status"] == 202 and rig.calls[-1][1] is principal
        assert acquire_busy(rig) == 409
    finally:
        stream.close()
        first.close()
        other.close()
        second.close()
    wait_until(lambda: principal in rig.retired)
    assert rig.retired.count(principal) == 1
    assert acquire(rig)


def acquire_busy(rig):
    return rig.api({"op": "acquire"})[0]


@pytest.mark.parametrize(
    "method,path,body,expected",
    [
        ("DELETE", "/api/bluetooth", None, 400),
        ("GET", "/api/bluetooth", {}, 400),
        ("POST", "/api/bluetooth/other", {"op": "acquire"}, 400),
        ("POST", "/api/bluetooth", {"op": "acquire", "owner": "tv"}, 400),
        ("POST", "/api/bluetooth", {"op": "acquire", "padding": "x" * 2050}, 413),
        ("POST", "/api/bluetooth", {"op": "acquire", "padding": "я" * 1100}, 413),
    ],
)
def test_socket_bluetooth_allowlist_and_decoded_body_limit(
    integrated, method, path, body, expected
):
    rig = integrated
    sock, stream, _ = connect(rig.port, rig.cookie, rig.csrf)
    try:
        # Use literal UTF-8 so the multi-byte body fits the existing 4KiB frame.
        payload = json.dumps(
            {"id": 1, "method": method, "path": path, "body": body}, ensure_ascii=False
        ).encode()
        mask = b"test"
        frame = (
            bytes([len(payload) | 0x80])
            if len(payload) < 126
            else b"\xfe" + struct.pack("!H", len(payload))
        )
        sock.sendall(b"\x81" + frame + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))
        assert receive_message(stream)["status"] == expected
    finally:
        stream.close()
        sock.close()


@pytest.mark.parametrize(
    "exit_kind", ["eof", "close", "malformed", "unauthorized", "timeout", "budget", "exception"]
)
def test_socket_finally_retires_on_every_exit(integrated, monkeypatch, exit_kind):
    rig = integrated
    sock, stream, _ = connect(rig.port, rig.cookie, rig.csrf)
    reply = ws_request(sock, stream, {"op": "acquire"})
    principal = rig.calls[-1][1]
    lease = reply["body"]["lease"]
    assert ws_request(sock, stream, {"op": "discover", "lease": lease})["status"] == 202
    if exit_kind == "eof":
        sock.shutdown(socket.SHUT_WR)
    elif exit_kind == "close":
        sock.sendall(b"\x88\x80test")
    elif exit_kind == "malformed":
        sock.sendall(b"\x81\x00")  # unmasked, forbidden frame
    elif exit_kind == "unauthorized":
        rig.settings.sessions.reset("new-auth")
        send_message(sock, {"id": 2, "method": "GET", "path": "/api/status", "body": None})
    elif exit_kind == "timeout":
        from ad_linux_tv.remote_socket import RemoteSocket

        monkeypatch.setattr(
            RemoteSocket, "_frame", lambda self: (_ for _ in ()).throw(socket.timeout())
        )
        sock.sendall(b"\x89\x80test")  # let a current blocking read finish
    elif exit_kind == "budget":
        monkeypatch.setattr("ad_linux_tv.remote_socket.FrameBudget.allow", lambda self: False)
        sock.sendall(b"\x89\x80test")
    else:

        def fail(*args):
            raise RuntimeError("synthetic dispatch failure")

        monkeypatch.setattr("ad_linux_tv.remote_rpc.RemoteDispatcher.dispatch", fail)
        send_message(sock, {"id": 2, "method": "GET", "path": "/api/status", "body": None})
    try:
        wait_until(lambda: principal in rig.retired)
        assert rig.retired.count(principal) == 1
        assert rig.manager._owner is None
        assert rig.transport.calls[-1][0] == "cancel"
    finally:
        stream.close()
        sock.close()


@pytest.mark.parametrize("owner", ["phone", "tv"])
@pytest.mark.parametrize("setting", ["pin", "noop", "unrelated", "invalid"])
def test_settings_pin_invalidation_retires_only_phones_outside_settings_lock(
    integrated, owner, setting
):
    rig = integrated
    if setting == "noop":
        rig.config["auth"]["require_pin"] = False
    sock = stream = None
    if owner == "phone":
        sock, stream, _ = connect(rig.port, rig.cookie, rig.csrf)
        lease = ws_request(sock, stream, {"op": "acquire"})["body"]["lease"]
        principal = rig.calls[-1][1]
        assert ws_request(sock, stream, {"op": "discover", "lease": lease})["status"] == 202
    else:
        lease = acquire(rig)
        action(rig, lease, "discover")
        principal = rig.calls[-1][1]
    retired = []
    real = rig.manager.retire_phones

    def retire_phones():
        assert not rig.settings.lock._is_owned()
        retired.append(True)
        real()

    rig.manager.retire_phones = retire_phones
    if setting == "noop":
        data = {"setting": "pin", "value": {"enabled": False, "pin": None, "confirm": None}}
    elif setting == "pin":
        data = {"setting": "pin", "value": {"enabled": False, "pin": None, "confirm": None}}
    elif setting == "unrelated":
        data = {"setting": "pointer_acceleration", "value": 60}
    else:
        data = {"setting": "pin", "value": {"enabled": True, "pin": "1234", "confirm": "0000"}}
    try:
        response, _ = request(rig.conn, "POST", "/api/settings", json.dumps(data), rig.tv_headers)
        assert response.status == (400 if setting == "invalid" else 200)
        assert bool(retired) == (setting == "pin")
        assert (rig.manager._owner is None) == (setting == "pin" and owner == "phone")
        if rig.manager._owner:
            assert rig.manager._owner == principal
    finally:
        if stream:
            stream.close()
            sock.close()


def test_bluetooth_never_leaks_into_public_status_or_settings(integrated):
    rig = integrated
    lease = acquire(rig)
    action(rig, lease, "pair", device_id="device")
    op = rig.api(method="GET")[1]["state"]["operation"]["id"]
    rig.transport.emit("challenge", op, challenge=Challenge(kind="display_pin", value="ABCD"))
    for path in ("/health", "/api/status", "/api/services", "/api/settings"):
        response, payload = request(rig.conn, "GET", path)
        assert response.status == 200
        assert not any(
            secret in payload.decode() for secret in (lease, "ABCD", "bluetooth", "device_epoch")
        )


def test_bluetooth_static_assets_and_html_order(integrated):
    for page, entry, kind in (("/", "app.js", "tv"), ("/remote", "remote.js", "phone")):
        response, payload = request(integrated.conn, "GET", page)
        assert response.status == 200
        html = payload.decode()
        assert html.index("/bluetooth_controls.js") < html.index("/" + entry)
        assert html.count(f'id="{kind}-bluetooth-controls"') == 1
        assert f'<details id="{kind}-bluetooth-details"' in html
        assert "/bluetooth_controls.css" in html
    for asset in ("bluetooth_controls.js", "bluetooth_controls.css"):
        response, payload = request(integrated.conn, "GET", "/" + asset)
        assert response.status == 200 and len(payload) > 100


@pytest.mark.parametrize("bad_host", ["attacker.example", "127.0.0.2", "127.0.0.1:1"])
def test_socket_direct_host_is_checked_before_any_inventory(integrated, bad_host):
    import base64

    rig = integrated
    host = f"{bad_host}:{rig.port}" if ":" not in bad_host else bad_host
    sock = socket.create_connection(("127.0.0.1", rig.port), timeout=2)
    stream = sock.makefile("rb")
    before = len(rig.calls)
    try:
        key = base64.b64encode(b"0123456789abcdef").decode()
        sock.sendall(
            (
                f"GET /api/remote-ws HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\n"
                f"Cookie: {rig.cookie}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Protocol: csrf.{rig.csrf}\r\n\r\n"
            ).encode()
        )
        assert b" 403 " in stream.readline()
        assert len(rig.calls) == before
    finally:
        stream.close()
        sock.close()


@pytest.mark.parametrize("stage", ["headers", "dispatcher"])
def test_socket_finally_also_covers_partial_upgrade_and_dispatcher_setup(
    integrated, monkeypatch, stage
):
    rig = integrated
    if stage == "headers":
        original = rig.handler.end_headers

        def end_headers(handler):
            original(handler)
            if handler.path.startswith("/api/remote-ws"):
                raise ConnectionError("synthetic upgrade write failure")

        monkeypatch.setattr(rig.handler, "end_headers", end_headers)
    else:

        def unavailable():
            raise ConnectionError("synthetic dispatcher setup failure")

        monkeypatch.setattr("ad_linux_tv.remote_rpc.get_media_monitor", unavailable)
    sock, stream, status = connect(rig.port, rig.cookie, rig.csrf)
    try:
        assert " 101 " in status
        wait_until(lambda: len(rig.retired) == 1)
        assert rig.retired[0].kind == "phone" and rig.retired[0].connection
    finally:
        stream.close()
        sock.close()


def test_pin_changed_through_ordered_socket_retires_all_phone_owners_immediately(integrated):
    rig = integrated
    sock, stream, _ = connect(rig.port, rig.cookie, rig.csrf)
    try:
        lease = ws_request(sock, stream, {"op": "acquire"})["body"]["lease"]
        assert ws_request(sock, stream, {"op": "discover", "lease": lease})["status"] == 202
        reply = ws_request(
            sock,
            stream,
            {"setting": "pin", "value": {"enabled": True, "pin": "4321", "confirm": "4321"}},
            path="/api/settings",
        )
        assert reply["status"] == 200
        assert rig.manager._owner is None
        assert rig.transport.calls[-1][0] == "cancel"
        send_message(sock, {"id": 4, "method": "GET", "path": "/api/bluetooth", "body": None})
        wait_until(lambda: len(rig.retired) == 1)
    finally:
        stream.close()
        sock.close()


def test_bluetooth_assets_and_route_helper_participate_in_existing_fingerprint(tmp_path):
    from pathlib import Path

    from ad_linux_tv.build_info import package_fingerprint

    root = Path(server.__file__).parent
    (tmp_path / "static").mkdir()
    for name in (
        "bluetooth_routes.py",
        "static/bluetooth_controls.js",
        "static/bluetooth_controls.css",
    ):
        target = tmp_path / name
        target.write_bytes((root / name).read_bytes())
    original = package_fingerprint(tmp_path)
    assert len(original) == 16
    for name in (
        "bluetooth_routes.py",
        "static/bluetooth_controls.js",
        "static/bluetooth_controls.css",
    ):
        target = tmp_path / name
        saved = target.read_bytes()
        target.write_bytes(saved + b"\n")
        assert package_fingerprint(tmp_path) != original
        target.write_bytes(saved)


def test_old_socket_cannot_recompute_a_different_session_principal(integrated, monkeypatch):
    rig = integrated
    sock, stream, _ = connect(rig.port, rig.cookie, rig.csrf)
    try:
        assert ws_request(sock, stream, {"op": "acquire"})["status"] == 200
        principal = rig.calls[-1][1]
        before = len(rig.calls)
        token, _ = rig.settings.sessions.create()
        monkeypatch.setattr(rig.handler, "authorized", lambda self: token)
        send_message(sock, {"id": 2, "method": "GET", "path": "/api/bluetooth", "body": None})
        wait_until(lambda: principal in rig.retired)
        assert len(rig.calls) == before
        assert rig.manager._owner is None
    finally:
        stream.close()
        sock.close()


@pytest.mark.parametrize("setting", ["noop", "unrelated"])
def test_settings_does_not_misattribute_auth_change_while_reading_body(
    integrated, monkeypatch, setting
):
    rig = integrated
    if setting == "noop":
        rig.config["auth"]["require_pin"] = False
    calls = []
    original_read = rig.handler.read_payload

    def read_payload(handler):
        payload = original_read(handler)
        if handler.path == "/api/settings":
            # Simulate another update completing while this request reads its body.
            rig.settings.sessions.reset("concurrent-auth-change")
        return payload

    monkeypatch.setattr(rig.handler, "read_payload", read_payload)
    monkeypatch.setattr(rig.manager, "retire_phones", lambda: calls.append(True))
    data = (
        {"setting": "pin", "value": {"enabled": False, "pin": None, "confirm": None}}
        if setting == "noop"
        else {"setting": "pointer_acceleration", "value": 60}
    )
    response, _ = request(rig.conn, "POST", "/api/settings", json.dumps(data), rig.tv_headers)
    assert response.status == 200 and calls == []


@pytest.mark.parametrize(
    "body,headers,expected",
    [
        ("{}", {}, 400),
        ("x" * 2049, {}, 413),
        (None, {"Content-Length": "-1"}, 400),
        (None, {"Content-Length": "invalid"}, 400),
        (None, {"Transfer-Encoding": "chunked"}, 400),
    ],
)
def test_bluetooth_http_get_is_bodyless_before_inventory(integrated, body, headers, expected):
    rig = integrated
    before = len(rig.calls)
    assert rig.api(method="GET", raw=body, headers=headers)[0] == expected
    assert len(rig.calls) == before


def test_socket_private_source_precedes_session_lookup(integrated, monkeypatch):
    rig = integrated
    monkeypatch.setattr(rig.handler, "private", lambda self: False)
    auth_calls = []
    monkeypatch.setattr(rig.handler, "authorized", lambda self: auth_calls.append(True))
    sock, stream, status = connect(rig.port, rig.cookie, rig.csrf)
    try:
        assert " 403 " in status and not auth_calls and not rig.calls
    finally:
        stream.close()
        sock.close()
