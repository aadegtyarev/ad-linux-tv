"""Bounded private Bluetooth configuration; never pairing secrets or input history.

Validation checks the persisted shape, not proof of a physical HID identity. The
coordinator and input broker must independently establish that proof before use.
"""

import re
from types import MappingProxyType

ACTIONS = (
    "up",
    "down",
    "left",
    "right",
    "ok",
    "back",
    "home",
    "play_pause",
    "seek_backward",
    "seek_forward",
    "volume_down",
    "volume_up",
    "mute",
)
MAX_BINDINGS = 32

# Linux input-event-codes.h identifiers. No printable keys, modifiers, power or
# reserved kiosk/accessibility keys are candidates, even during learning.
BUTTON_CODES = MappingProxyType(
    {
        "KEY_ESC": 1,
        "KEY_ENTER": 28,
        "KEY_KPENTER": 96,
        "KEY_HOME": 102,
        "KEY_UP": 103,
        "KEY_LEFT": 105,
        "KEY_RIGHT": 106,
        "KEY_DOWN": 108,
        "KEY_MUTE": 113,
        "KEY_VOLUMEDOWN": 114,
        "KEY_VOLUMEUP": 115,
        "KEY_PAUSE": 119,
        "KEY_BACK": 158,
        "KEY_NEXTSONG": 163,
        "KEY_PLAYPAUSE": 164,
        "KEY_PREVIOUSSONG": 165,
        "KEY_REWIND": 168,
        "KEY_HOMEPAGE": 172,
        "KEY_PLAY": 207,
        "KEY_FASTFORWARD": 208,
        "KEY_OK": 352,
        "KEY_SELECT": 353,
    }
)
_ADDRESS = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")


def _address(value):
    if (
        not isinstance(value, str)
        or not _ADDRESS.fullmatch(value)
        or value in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
    ):
        raise ValueError("invalid Bluetooth identity")
    return value


def validate_identity(value):
    """Copy a canonical adapter/device identity, never a device path or name.

    Unresolved private random addresses are not persistent identities. Accept a
    random address only in the static-random format; this alone does not prove
    that a connected device owns it. No supplied values appear in errors.
    """
    if not isinstance(value, dict) or set(value) != {"adapter", "address", "address_type"}:
        raise ValueError("invalid Bluetooth identity")
    adapter = _address(value["adapter"])
    address = _address(value["address"])
    address_type = value["address_type"]
    if not isinstance(address_type, str) or address_type not in ("public", "random"):
        raise ValueError("invalid Bluetooth identity")
    if address_type == "random":
        number = int(address.replace(":", ""), 16)
        random_mask = (1 << 46) - 1
        if number >> 46 != 3 or number & random_mask in (0, random_mask):
            raise ValueError("invalid Bluetooth identity")
    return {"adapter": adapter, "address": address, "address_type": address_type}


def validate_bindings(value):
    """Return a detached bounded map from known physical buttons to fixed actions."""
    if not isinstance(value, dict) or len(value) > MAX_BINDINGS:
        raise ValueError("invalid Bluetooth bindings")
    result = {}
    for key, action in value.items():
        if (
            not isinstance(key, str)
            or key not in BUTTON_CODES
            or not isinstance(action, str)
            or action not in ACTIONS
        ):
            raise ValueError("invalid Bluetooth bindings")
        result[key] = action
    return result


def validate_bluetooth(value):
    """Validate an explicitly present optional ``bluetooth`` config section.

    Omission is handled by the caller and must not trigger a configuration write.
    An explicit section has exactly ``remote``, either null or one identity/map.
    """
    if not isinstance(value, dict) or set(value) != {"remote"}:
        raise ValueError("invalid Bluetooth configuration")
    remote = value["remote"]
    if remote is None:
        return {"remote": None}
    if not isinstance(remote, dict) or set(remote) != {"identity", "bindings"}:
        raise ValueError("invalid Bluetooth configuration")
    return {
        "remote": {
            "identity": validate_identity(remote["identity"]),
            "bindings": validate_bindings(remote["bindings"]),
        }
    }
