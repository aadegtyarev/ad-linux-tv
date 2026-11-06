"""Fixed non-navigation keys and actions for user-chosen TV-session shortcuts.

Numeric values are XKB keysyms. A learner filters locally before returning a
candidate; ordinary typed keys must never become captured results.
"""

ACTIONS = ("ok", "volume_up", "volume_down", "video_panel", "magnifier", "fullscreen")
KEYSYMS = {
    **{f"XF86Launch{digit}": 0x1008FF40 + index for index, digit in enumerate("0123456789ABCDEF")},
    "XF86Tools": 0x1008FF81,
    "XF86Favorites": 0x1008FF30,
    "XF86Search": 0x1008FF1B,
    "XF86AudioMedia": 0x1008FF32,
    "XF86Subtitle": 0x1008FF9A,
    "XF86Video": 0x1008FF87,
    "XF86Info": 0x10081166,
    "XF86Audio": 0x10081188,
    "XF86Red": 0x1008FFA3,
    "XF86Green": 0x1008FFA4,
    "XF86Yellow": 0x1008FFA5,
    "XF86Blue": 0x1008FFA6,
}
BY_VALUE = {value: key for key, value in KEYSYMS.items()}


def validate_shortcuts(value):
    """Allow only six distinct canonical keys; omitted entries mean unassigned."""
    if not isinstance(value, dict) or set(value) - set(ACTIONS):
        raise ValueError("invalid shortcuts")
    result = {}
    for action, key in value.items():
        if not isinstance(key, str) or key not in KEYSYMS:
            raise ValueError("unsupported shortcut")
        result[action] = key
    if len(set(result.values())) != len(result):
        raise ValueError("duplicate shortcut")
    return result
