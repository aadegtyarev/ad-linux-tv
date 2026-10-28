"""Never actuate real host power: explicit injected or mocked shutdown only."""

import stat
import subprocess
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from conftest import command_headers, login
from conftest import request as http_request

from ad_linux_tv.host_power import (
    HostPowerControl,
    PowerError,
    dispatch_shutdown,
    shutdown_available,
)


def test_session_bound_one_use_challenge_and_latch():
    calls = []
    power = HostPowerControl(
        available=lambda: True, actuator=lambda: calls.append("off") or "requested"
    )
    challenge = power.prepare("one")["challenge"]
    with pytest.raises(PowerError) as error:
        power.confirm("other", challenge)
    assert error.value.status == 409
    assert calls == []
    assert power.confirm("one", challenge) == (202, {"available": True, "phase": "requested"})
    with pytest.raises(PowerError):
        power.confirm("one", challenge)
    with pytest.raises(PowerError):
        power.prepare("one")
    assert calls == ["off"]


def test_expired_and_replaced_confirmation_does_not_dispatch():
    clock = [100]
    calls = []
    power = HostPowerControl(
        available=lambda: True, actuator=lambda: calls.append(1), clock=lambda: clock[0]
    )
    first = power.prepare("session")["challenge"]
    power.prepare("session")
    with pytest.raises(PowerError):
        power.confirm("session", first)
    last = power.prepare("session")["challenge"]
    clock[0] += 20
    with pytest.raises(PowerError):
        power.confirm("session", last)
    assert not calls


def test_challenge_capacity_and_strict_token():
    power = HostPowerControl(available=lambda: True, actuator=lambda: "requested")
    for value in range(64):
        power.prepare(str(value))
    with pytest.raises(PowerError) as error:
        power.prepare("overflow")
    assert error.value.status == 503
    for invalid in (None, True, 1, "x", "!" * 43):
        with pytest.raises(PowerError) as error:
            power.confirm("session", invalid)
        assert error.value.status == 400


def test_uncertain_shutdown_cannot_be_replayed_even_with_fresh_nonce():
    calls = []
    power = HostPowerControl(
        available=lambda: True, actuator=lambda: calls.append(1) or "uncertain"
    )
    challenge = power.prepare("session")["challenge"]
    assert power.confirm("session", challenge)[0] == 503
    assert power.status()["phase"] == "uncertain"
    with pytest.raises(PowerError):
        power.prepare("session")
    with pytest.raises(PowerError):
        power.confirm("session", challenge)
    assert calls == [1]


def test_definite_unavailable_consumes_challenge():
    power = HostPowerControl(available=lambda: True, actuator=lambda: "unavailable")
    challenge = power.prepare("session")["challenge"]
    assert power.confirm("session", challenge) == (503, {"available": True, "phase": "idle"})
    with pytest.raises(PowerError):
        power.confirm("session", challenge)


def test_no_lock_held_across_actuation_and_no_second_dispatch():
    entered, release = Event(), Event()
    calls = []

    def actuator():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return "requested"

    power = HostPowerControl(available=lambda: True, actuator=actuator)
    challenge = power.prepare("session")["challenge"]
    thread = Thread(target=lambda: power.confirm("session", challenge))
    thread.start()
    assert entered.wait(2)
    assert power.status()["phase"] == "dispatching"
    with pytest.raises(PowerError):
        power.prepare("another")
    release.set()
    thread.join(2)
    assert not thread.is_alive() and calls == [1]


def test_fixed_shutdown_actuator_and_timeout_are_not_retry(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("ad_linux_tv.host_power.subprocess.run", run)
    assert dispatch_shutdown() == "requested"
    assert calls[0][0] == [
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "--no-block",
        "start",
        "ad-linux-tv-poweroff.service",
    ]
    assert calls[0][1]["timeout"] == 5

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("fixed", 5)

    monkeypatch.setattr("ad_linux_tv.host_power.subprocess.run", timeout)
    assert dispatch_shutdown() == "uncertain"


def test_availability_requires_kiosk_root_owned_regular_unit(monkeypatch):
    info = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0)
    monkeypatch.setattr("ad_linux_tv.host_power.UNIT_PATH", SimpleNamespace(lstat=lambda: info))
    monkeypatch.delenv("AD_LINUX_TV_KIOSK", raising=False)
    assert not shutdown_available()
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    assert shutdown_available()
    info.st_mode = stat.S_IFLNK | 0o777
    assert not shutdown_available()
    info.st_mode, info.st_uid = stat.S_IFREG | 0o666, 0
    assert not shutdown_available()
    info.st_mode, info.st_uid = stat.S_IFREG | 0o644, 1002
    assert not shutdown_available()


@pytest.fixture
def power_endpoint(monkeypatch, request):
    import json

    calls = []
    power = HostPowerControl(
        available=lambda: True, actuator=lambda: calls.append("off") or "requested"
    )
    monkeypatch.setattr("ad_linux_tv.server.HostPowerControl", lambda: power)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = request.getfixturevalue("endpoint")
    _response, data, cookie = login(connection, port)
    headers = command_headers(port, cookie, data["csrf"])
    return connection, port, headers, calls, json


def test_http_shutdown_requires_session_csrf_even_loopback_and_consumes_once(power_endpoint):
    connection, port, headers, calls, json = power_endpoint
    for denied in (
        {"Origin": f"http://127.0.0.1:{port}"},
        {**headers, "X-CSRF-Token": "wrong"},
        {**headers, "Origin": "http://elsewhere"},
    ):
        response, _ = http_request(connection, "POST", "/api/power", '{"action":"prepare"}', denied)
        assert response.status == 403
    response, _ = http_request(connection, "GET", "/api/power")
    assert response.status == 403
    response, payload = http_request(
        connection, "POST", "/api/power", '{"action":"prepare"}', headers
    )
    assert response.status == 200 and not calls
    challenge = json.loads(payload)["challenge"]
    action = json.dumps({"action": "shutdown", "challenge": challenge})
    response, _ = http_request(connection, "POST", "/api/power", action, headers)
    assert response.status == 202 and calls == ["off"]
    response, _ = http_request(connection, "POST", "/api/power", action, headers)
    assert response.status == 409 and calls == ["off"]


def test_http_power_rejects_unknown_fields_and_non_kiosk(power_endpoint, monkeypatch):
    connection, _port, headers, calls, _json = power_endpoint
    for body in (
        "{}",
        '{"action":"off"}',
        '{"action":"prepare","unit":"evil"}',
        '{"action":"shutdown","challenge":true}',
    ):
        response, _ = http_request(connection, "POST", "/api/power", body, headers)
        assert response.status == 400
    monkeypatch.delenv("AD_LINUX_TV_KIOSK")
    response, _ = http_request(connection, "POST", "/api/power", '{"action":"prepare"}', headers)
    assert response.status == 403 and not calls
