"""Discovery tests never open multicast sockets or inspect real LAN interfaces."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ad_linux_tv.discovery import (
    DiscoveryAnnouncer,
    advertisement_address,
    device_identity,
    new_discovery,
    validate_discovery,
)


def config():
    return {"bind": "0.0.0.0", "port": 8765, "discovery": new_discovery("Гостиная")}


def test_identity_is_stable_nonsecret_and_passive():
    data = config()
    data["auth"] = {"verifier": "must-not-escape", "salt": "private", "pin": "1234"}
    first = device_identity(data)
    assert first == device_identity(data)
    assert set(first) == {"app", "protocol", "id", "name", "port", "remote_path"}
    assert first["app"] == "ad-linux-tv" and first["remote_path"] == "/remote"
    assert "must-not-escape" not in json.dumps(first)
    assert new_discovery()["id"] != first["id"]
    assert device_identity({"port": 8765}) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("enabled", "yes"),
        ("enabled", 1),
        ("id", "not-a-uuid"),
        ("id", ""),
        ("name", ""),
        ("name", " x"),
        ("name", "x\ny"),
        ("name", "x" * 81),
        ("name", "🙂" * 41),
        ("name", None),
    ],
)
def test_discovery_schema_is_strict(field, value):
    data = new_discovery()
    data[field] = value
    with pytest.raises((ValueError, TypeError, AttributeError)):
        validate_discovery(data)


def test_legacy_disabled_and_constructor_do_not_touch_network():
    resolver, publisher = Mock(), Mock()
    old = DiscoveryAnnouncer({"port": 8765}, resolver=resolver, publisher=publisher)
    old.start()
    old.refresh()
    assert old.status() == "disabled" and old.thread is None
    resolver.assert_not_called()
    publisher.assert_not_called()
    old.close()


def test_address_change_unregisters_previous_before_registering_new():
    events = []
    address = ["192.168.1.20"]

    def publisher(ip, identity):
        events.append(("register", ip, identity["id"]))
        return SimpleNamespace(close=lambda: events.append(("close", ip)))

    manager = DiscoveryAnnouncer(config(), resolver=lambda _c: address[0], publisher=publisher)
    assert events == []
    manager.refresh()
    manager.refresh()
    assert len(events) == 1 and manager.status() == "announcing"
    address[0] = "192.168.1.21"
    manager.refresh()
    assert events[1] == ("close", "192.168.1.20")
    assert events[2][0:2] == ("register", "192.168.1.21")
    assert events[0][2] == events[2][2]
    address[0] = None
    manager.refresh()
    assert manager.status() == "no_lan_address"
    manager.close()
    manager.close()
    assert manager.status() == "closed"


def test_missing_lan_and_publisher_failure_leave_http_independent(caplog):
    manager = DiscoveryAnnouncer(config(), resolver=lambda _c: None, publisher=Mock())
    manager.refresh()
    assert manager.status() == "no_lan_address"
    manager = DiscoveryAnnouncer(
        config(),
        resolver=lambda _c: "192.168.1.2",
        publisher=Mock(side_effect=RuntimeError("PRIVATE diagnostic must not be logged")),
    )
    manager.refresh()
    assert manager.status() == "unavailable"
    assert "PRIVATE" not in caplog.text
    manager.close()


def test_unknown_retirement_latches_and_never_creates_another_publisher():
    active = SimpleNamespace(close=Mock(side_effect=RuntimeError("unknown cleanup")))
    factory = Mock(return_value=active)
    address = ["192.168.1.2"]
    manager = DiscoveryAnnouncer(config(), resolver=lambda _c: address[0], publisher=factory)
    manager.refresh()
    address[0] = "192.168.1.3"
    manager.refresh()
    assert manager.status() == "cleanup_failed"
    manager.refresh()
    assert factory.call_count == 1
    with pytest.raises(RuntimeError):
        manager.close()
    assert manager.status() == "cleanup_failed"


def test_close_failure_preserves_unconfirmed_cleanup_state():
    active = SimpleNamespace(close=Mock(side_effect=RuntimeError("unknown cleanup")))
    factory = Mock(return_value=active)
    manager = DiscoveryAnnouncer(config(), resolver=lambda _c: "192.168.1.2", publisher=factory)
    manager.refresh()
    assert manager.status() == "announcing"
    for _ in range(2):
        with pytest.raises(RuntimeError):
            manager.close()
        assert manager.status() == "cleanup_failed"
        manager.refresh()
    assert factory.call_count == 1


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://192.168.1.2:8765/remote", "192.168.1.2"),
        ("http://[fd00::2]:8765/remote", "fd00::2"),
        ("http://127.0.0.1:8765/remote", None),
        ("http://203.0.113.2:8765/remote", None),
        ("http://[fe80::1]:8765/remote", None),
        ("", None),
    ],
)
def test_advertisement_matches_existing_private_bind_route_policy(monkeypatch, url, expected):
    monkeypatch.setattr("ad_linux_tv.pages.preferred_remote_address", lambda _c: url)
    assert advertisement_address(config()) == expected


def test_publisher_constructs_valid_records_without_real_multicast(monkeypatch):
    import zeroconf

    from ad_linux_tv.discovery import SERVICE_TYPE, _Publisher

    calls = []

    class FakeZeroconf:
        def __init__(self, **kwargs):
            calls.append(("open", kwargs["interfaces"]))

        def register_service(self, info, **kwargs):
            calls.append(("register", info, kwargs))

        def unregister_service(self, info):
            calls.append(("unregister", info))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(zeroconf, "Zeroconf", FakeZeroconf)
    identity = device_identity(config())
    publisher = _Publisher("192.168.1.2", identity)
    assert publisher.info.type == SERVICE_TYPE
    assert publisher.info.properties[b"id"].decode() == identity["id"]
    assert set(publisher.info.properties) == {b"id", b"name", b"protocol", b"path"}
    publisher.close()
    assert [row[0] for row in calls] == ["open", "register", "unregister", "close"]


def test_status_never_waits_for_registration_lock():
    manager = DiscoveryAnnouncer(config(), resolver=Mock(), publisher=Mock())
    with manager.lock:
        assert manager.status() == "starting"
