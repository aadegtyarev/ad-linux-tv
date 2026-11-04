"""Bluetooth device names through fake BlueZ only; no host Bluetooth access."""

from dataclasses import replace

import pytest
from test_bluetooth_bluez import _DEVICE, _OM, _PROPS, AP, DP, FakeBus, Lane
from test_bluetooth_manager import Rig


@pytest.fixture
def rig():
    instance = Rig()
    instance.start()
    instance.acquire()
    yield instance
    instance.manager.close()


def test_bootstrap_alias_then_late_name_during_discovery_and_invalidation():
    bus = FakeBus()
    bus.inventory[DP][_DEVICE].pop("Name")
    bus.inventory[DP][_DEVICE]["Alias"] = "22:33:44:55:66:77"
    lane = Lane(bus=bus)
    try:
        before = lane.transport.snapshot().devices[0]
        assert before.name == before.alias == "22:33:44:55:66:77"
        assert before.bluez_name == ""
        lane.begin("discover")
        lane.accepted()
        lane.properties(Name="Actual Remote")
        updated = lane.transport.snapshot().devices[0]
        assert updated.id == before.id and updated.device_epoch == before.device_epoch
        assert updated.name == updated.bluez_name == "Actual Remote"
        assert updated.alias == "22:33:44:55:66:77"
        lane.properties(Alias="Living room")
        updated = lane.transport.snapshot().devices[0]
        assert (updated.name, updated.bluez_name, updated.alias) == (
            "Actual Remote",
            "Actual Remote",
            "Living room",
        )
        lane.signal(_PROPS, "PropertiesChanged", [_DEVICE, {}, ["Name"]], DP)
        updated = lane.transport.snapshot().devices[0]
        assert (updated.name, updated.bluez_name, updated.alias) == (
            "Living room",
            "",
            "Living room",
        )
        lane.signal(_PROPS, "PropertiesChanged", [_DEVICE, {}, ["Alias"]], DP)
        updated = lane.transport.snapshot().devices[0]
        assert (updated.name, updated.bluez_name, updated.alias) == ("", "", "")
        assert updated.id == before.id and updated.device_epoch == before.device_epoch
    finally:
        lane.close()


@pytest.mark.parametrize(
    "bluez_name,alias,expected",
    [
        ("Real", "", "Real"),
        ("", "Alias", "Alias"),
        ("Same", "Same", "Same"),
        ("", "", ""),
        ("Real", None, "Real"),
        (None, "Alias", "Alias"),
    ],
)
def test_name_first_and_missing_or_invalid_fields(bluez_name, alias, expected):
    bus = FakeBus()
    bus.inventory[DP][_DEVICE].update(Name=bluez_name, Alias=alias)
    lane = Lane(bus=bus)
    try:
        device = lane.transport.snapshot().devices[0]
        assert device.name == expected
        assert device.bluez_name == (bluez_name or "")
        assert device.alias == (alias or "")
    finally:
        lane.close()


def test_interfaces_added_preserves_both_fields_and_separate_sanitization():
    lane = Lane()
    try:
        path = AP + "/dev_synthetic"
        lane.signal(
            _OM,
            "InterfacesAdded",
            [
                path,
                {
                    _DEVICE: {
                        "Address": "55:44:33:22:11:00",
                        "Adapter": AP,
                        "Name": "<name>\n" + "🙂" * 100,
                        "Alias": "<alias>\u202e" + "я" * 100,
                    }
                },
            ],
        )
        device = next(
            d for d in lane.transport.snapshot().devices if d.address == "55:44:33:22:11:00"
        )
        assert device.name == device.bluez_name and device.name.startswith("<name>")
        assert device.alias.startswith("<alias>")
        for value in (device.name, device.bluez_name, device.alias):
            assert "\n" not in value and "\u202e" not in value
            assert len(value) <= 80 and len(value.encode()) <= 160
    finally:
        lane.close()


def test_manager_exposes_independently_bounded_fields_without_identity_change(rig):
    fake = replace(
        rig.transport.state.devices[0],
        name="actual",
        bluez_name="actual\n" + "🙂" * 100,
        alias="22:33:44:55:66:77\u202e" + "я" * 100,
    )
    rig.transport.state = replace(rig.transport.state, devices=(fake,))
    item = rig.state()["devices"][0]
    assert item["name"] == "actual"
    assert item["bluez_name"].startswith("actual") and "\n" not in item["bluez_name"]
    assert item["alias"].startswith("22:33:44:55:66:77") and "\u202e" not in item["alias"]
    assert all(
        len(item[key]) <= 80 and len(item[key].encode()) <= 160
        for key in ("name", "bluez_name", "alias")
    )
    assert "address" not in item
    assert not rig.settings.saves
