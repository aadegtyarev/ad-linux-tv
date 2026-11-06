"""Render private runtime labwc configuration from the single persistent YAML config."""

import ctypes
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

from .config import load_config
from .settings import atomic_write
from .tv_shortcut_keys import KEYSYMS, validate_shortcuts

# These two multimedia keysyms are deliberately handled only in this session.
# Normal Enter and navigation remain untouched; an existing explicit binding wins.
_OK_KEYSYMS = {"XF86OK": 0x10081160, "XF86Select": 0x1008FFA0}


@lru_cache(maxsize=1)
def _keysym_parser():
    try:
        library = ctypes.CDLL("libxkbcommon.so.0")
        parser = library.xkb_keysym_from_name
        parser.argtypes = [ctypes.c_char_p, ctypes.c_int]
        parser.restype = ctypes.c_uint32
        return parser
    except (OSError, AttributeError):
        return None


_MODIFIERS = frozenset({"S", "C", "A", "Mod1", "H", "Mod3", "W", "Mod4", "M", "Mod5"})


def _bare_binding_symbols(keyboard, parser):
    """Match labwc's hyphen-separated symbols without treating modifiers as keys."""
    symbols, names = set(), set()
    for binding in keyboard.findall("keybind"):
        parts = binding.get("key", "").split("-")
        if any(part in _MODIFIERS for part in parts):
            continue
        for part in parts:
            if part:
                symbols.add(parser(part.encode("utf-8"), 1))
                names.add(part.replace("_", "").casefold())
    return symbols, names


def add_default_ok_bindings(root, *, defaults_verified=False):
    keyboard = root.find("keyboard")
    if keyboard is None:
        keyboard = ElementTree.SubElement(root, "keyboard")
    if keyboard.find("default") is None and not keyboard.findall("keybind"):
        # Labwc implicitly loads defaults only while there are no explicit binds.
        keyboard.insert(0, ElementTree.Element("default"))
    parser = _keysym_parser()
    if parser is None:
        # Without the compositor's parser, aliases cannot be checked safely.
        print("TV OK defaults unavailable: XKB library not found", file=sys.stderr)
        return
    if keyboard.find("default") is not None and not defaults_verified:
        print("TV OK defaults unavailable: unknown labwc defaults", file=sys.stderr)
        return
    existing, normalized = _bare_binding_symbols(keyboard, parser)
    for key, keysym in _OK_KEYSYMS.items():
        if keysym in existing or key.replace("_", "").casefold() in normalized:
            continue
        if parser(key.encode("utf-8"), 1) != keysym:
            print(f"TV OK default unavailable: {key} unsupported", file=sys.stderr)
            continue
        binding = ElementTree.SubElement(
            keyboard, "keybind", {"key": key, "onRelease": "yes", "layoutDependent": "yes"}
        )
        ElementTree.SubElement(
            binding, "action", {"name": "Execute", "command": "/usr/bin/wtype -k Return"}
        )


_VOLUME_COMMANDS = {
    "volume_up": "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%+",
    "volume_down": "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%-",
}


def add_default_volume_bindings(root, *, defaults_verified=False):
    """Upgrade known labwc default volume actions without overriding custom binds."""
    keyboard = root.find("keyboard")
    parser = _keysym_parser()
    if keyboard is None or keyboard.find("default") is None or parser is None:
        return
    existing, _ = _bare_binding_symbols(keyboard, parser)
    for key, action in (
        ("XF86_AudioRaiseVolume", "volume_up"),
        ("XF86_AudioLowerVolume", "volume_down"),
    ):
        sym = parser(key.encode("utf-8"), 1)
        if not sym or sym in existing:
            continue
        if not defaults_verified:
            print("TV volume defaults unavailable: unknown labwc defaults", file=sys.stderr)
            continue
        binding = ElementTree.SubElement(keyboard, "keybind", {"key": key})
        ElementTree.SubElement(
            binding, "action", {"name": "Execute", "command": _VOLUME_COMMANDS[action]}
        )


_SHORTCUT_COMMANDS = {
    "ok": "/usr/bin/wtype -k Return",
    **_VOLUME_COMMANDS,
    "video_panel": "/usr/local/libexec/ad-linux-tv/tv-shortcut.sh video_panel",
    "magnifier": "/usr/local/libexec/ad-linux-tv/tv-shortcut.sh magnifier",
    "fullscreen": "/usr/local/libexec/ad-linux-tv/tv-shortcut.sh fullscreen",
}
_REPEATABLE = frozenset({"volume_up", "volume_down"})


def add_selected_shortcuts(root, shortcuts, *, defaults_verified=False):
    """Append only nonconflicting, supported bindings; return what was rendered."""
    choices = validate_shortcuts(shortcuts)
    if not choices:
        return {}
    keyboard = root.find("keyboard")
    parser = _keysym_parser()
    if keyboard is None or parser is None:
        return {}
    # <default/> expands to labwc-internal bindings, not visible in XML.
    if keyboard.find("default") is not None and not defaults_verified:
        return {}
    existing, _ = _bare_binding_symbols(keyboard, parser)
    applied = {}
    for action, key in choices.items():
        keysym = KEYSYMS[key]
        if keysym in existing or parser(key.encode("utf-8"), 1) != keysym:
            continue
        binding = ElementTree.SubElement(
            keyboard,
            "keybind",
            {
                "key": key,
                "onRelease": "no" if action in _REPEATABLE else "yes",
                "layoutDependent": "yes",
            },
        )
        ElementTree.SubElement(
            binding, "action", {"name": "Execute", "command": _SHORTCUT_COMMANDS[action]}
        )
        existing.add(keysym)
        applied[action] = key
    return applied


def _known_labwc_defaults():
    """Only versions whose built-in bindings were reviewed may be extended."""
    try:
        result = subprocess.run(
            ["/usr/bin/labwc", "--version"], capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.split()[:2] == ["labwc", "0.9.3"]


def render_labwc(config_path, template, destination):
    config = load_config(config_path)
    tree = ElementTree.parse(template)
    root = tree.getroot()
    if root.tag != "labwc_config":
        raise ValueError("unsupported compositor template")
    node = root.find("magnifier/initScale")
    if node is None:
        raise ValueError("magnifier template missing")
    node.text = format(config.get("magnifier", {"scale": 2.5})["scale"], "g")
    defaults_verified = _known_labwc_defaults()
    add_default_ok_bindings(root, defaults_verified=defaults_verified)
    add_default_volume_bindings(root, defaults_verified=defaults_verified)
    selected = config.get("tv_shortcuts", {})
    applied = add_selected_shortcuts(root, selected, defaults_verified=defaults_verified)
    directory = Path(destination)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(directory / "rc.xml", ElementTree.tostring(root, encoding="unicode"))
    atomic_write(
        directory / "shortcuts-applied.json",
        json.dumps({"requested": selected, "applied": applied}, sort_keys=True),
    )
    return config.get("magnifier", {"scale": 2.5})["scale"]


def main():
    try:
        if len(sys.argv) != 4:
            raise ValueError("expected config, template and destination")
        print(format(render_labwc(*sys.argv[1:]), "g"))
    except (OSError, ValueError, ElementTree.ParseError):
        print("Cannot prepare TV compositor configuration", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
