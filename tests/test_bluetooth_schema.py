"""Private configuration accepts only a stable-shaped identity and fixed buttons."""

import copy

import pytest

from ad_linux_tv.bluetooth_schema import (
    ACTIONS,
    BUTTON_CODES,
    validate_bindings,
    validate_bluetooth,
    validate_identity,
)


@pytest.fixture
def identity():
    return {
        "adapter": "AA:BB:CC:DD:EE:FF",
        "address": "11:22:33:44:55:66",
        "address_type": "public",
    }


def test_disabled_and_detached_config(identity):
    assert validate_bluetooth({"remote": None}) == {"remote": None}
    value = {"remote": {"identity": identity, "bindings": {"KEY_ENTER": "ok"}}}
    before = copy.deepcopy(value)
    result = validate_bluetooth(value)
    assert result == before
    result["remote"]["identity"]["address"] = "22:33:44:55:66:77"
    result["remote"]["bindings"]["KEY_ENTER"] = "home"
    assert value == before


@pytest.mark.parametrize("value", [None, True, 1, "", [], {}, {"remote": None, "pin": "1234"}])
def test_invalid_section(value):
    with pytest.raises(ValueError, match="invalid Bluetooth configuration"):
        validate_bluetooth(value)


@pytest.mark.parametrize(
    "remote",
    [None, True, 1, "", [], {}, {"bindings": {}}, {"identity": {}}, {"pin": "1234"}],
)
def test_remote_exact_shape(remote):
    if remote is None:
        assert validate_bluetooth({"remote": remote}) == {"remote": None}
    else:
        with pytest.raises(ValueError, match="invalid Bluetooth configuration"):
            validate_bluetooth({"remote": remote})


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("adapter", None),
        ("adapter", True),
        ("adapter", "00:00:00:00:00:00"),
        ("adapter", "FF:FF:FF:FF:FF:FF"),
        ("adapter", "aa:bb:cc:dd:ee:ff"),
        ("adapter", "AA:BB:CC:DD:EE:FF\n"),
        ("address", "11:22:33:44:55"),
        ("address", "/dev/input/event1"),
        ("address", "<script>secret</script>"),
        ("address_type", None),
        ("address_type", []),
        ("address_type", "private"),
        ("address_type", True),
    ],
)
def test_identity_rejects_invalid_without_echoing_values(identity, field, bad):
    identity[field] = bad
    with pytest.raises(ValueError) as error:
        validate_identity(identity)
    assert str(error.value) == "invalid Bluetooth identity"


@pytest.mark.parametrize("value", [None, [], {}, {"address": "11:22:33:44:55:66"}])
def test_identity_requires_exact_fields(value):
    with pytest.raises(ValueError):
        validate_identity(value)


def test_extra_identity_fields_rejected(identity):
    identity["path"] = "/org/bluez/hci1/dev_11_22_33_44_55_66"
    with pytest.raises(ValueError):
        validate_identity(identity)


def test_static_random_shape_accepted_without_claiming_physical_proof(identity):
    identity.update(address="C1:22:33:44:55:66", address_type="random")
    assert validate_identity(identity) == identity


@pytest.mark.parametrize(
    "address", ["01:22:33:44:55:66", "41:22:33:44:55:66", "81:22:33:44:55:66", "C0:00:00:00:00:00"]
)
def test_unresolved_private_and_invalid_static_random_not_persistable(identity, address):
    identity.update(address=address, address_type="random")
    with pytest.raises(ValueError):
        validate_identity(identity)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        [],
        {True: "ok"},
        {28: "ok"},
        {"KEY_ENTER": True},
        {"KEY_ENTER": None},
        {"KEY_ENTER": []},
        {"KEY_ENTER": "shutdown"},
        {"KEY_ENTER": "sh -c id"},
        {"KEY_A": "ok"},
        {"KEY_SPACE": "ok"},
        {"KEY_F8": "home"},
        {"KEY_F9": "home"},
        {"KEY_F12": "home"},
        {"KEY_LEFTCTRL": "home"},
        {"KEY_POWER": "home"},
        {"KEY_" + str(i): "ok" for i in range(33)},
    ],
)
def test_bindings_fail_closed(value):
    with pytest.raises(ValueError) as error:
        validate_bindings(value)
    assert str(error.value) == "invalid Bluetooth bindings"


def test_catalogues_are_fixed_unique_and_support_all_actions():
    assert len(ACTIONS) == len(set(ACTIONS)) == 13
    assert len(BUTTON_CODES) <= 32
    assert len(set(BUTTON_CODES.values())) == len(BUTTON_CODES)
    for action in ACTIONS:
        assert validate_bindings({"KEY_ENTER": action}) == {"KEY_ENTER": action}
    assert validate_bindings({key: "ok" for key in BUTTON_CODES}) == dict.fromkeys(
        BUTTON_CODES, "ok"
    )
    with pytest.raises(TypeError):
        BUTTON_CODES["KEY_A"] = 30


def test_multiple_buttons_can_share_one_action():
    value = {"KEY_ENTER": "ok", "KEY_OK": "ok"}
    assert validate_bindings(value) == value
