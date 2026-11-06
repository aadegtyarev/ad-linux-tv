"""Only explicitly selected rare keysyms can become TV-session shortcuts."""

from xml.etree import ElementTree

import pytest
import yaml
from test_config_edges import make_data

from ad_linux_tv.config import load_config
from ad_linux_tv.kiosk_config import add_selected_shortcuts
from ad_linux_tv.tv_shortcut_keys import ACTIONS, BY_VALUE, KEYSYMS, validate_shortcuts


def test_canonical_mapping_is_empty_by_default_and_round_trips():
    assert validate_shortcuts({}) == {}
    value = {
        "ok": "XF86Launch1",
        "volume_up": "XF86Launch2",
        "volume_down": "XF86Launch3",
        "video_panel": "XF86Launch4",
        "magnifier": "XF86Launch5",
        "fullscreen": "XF86Launch6",
    }
    assert validate_shortcuts(value) == value
    assert set(ACTIONS) == set(value)
    previous_three = {key: value[key] for key in ("video_panel", "magnifier", "fullscreen")}
    assert validate_shortcuts(previous_three) == previous_three
    assert len(KEYSYMS) == len(BY_VALUE)
    assert BY_VALUE[KEYSYMS["XF86Launch1"]] == "XF86Launch1"


def test_single_config_preserves_existing_settings_and_rejects_invalid_mapping(tmp_path):
    data = make_data()
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    assert "tv_shortcuts" not in load_config(path)
    data["tv_shortcuts"] = {"video_panel": "XF86Launch1"}
    path.write_text(yaml.safe_dump(data))
    assert load_config(path)["tv_shortcuts"] == data["tv_shortcuts"]
    data["tv_shortcuts"] = {"video_panel": "Return"}
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_config(path)


def test_rendered_shortcuts_use_only_fixed_actions_and_do_not_override_bindings(monkeypatch):
    lookup = {key.casefold(): value for key, value in KEYSYMS.items()}
    lookup["0x1008ff41"] = KEYSYMS["XF86Launch1"]
    monkeypatch.setattr(
        "ad_linux_tv.kiosk_config._keysym_parser",
        lambda: lambda raw, _flags: lookup.get(raw.decode().replace("_", "").casefold(), 0),
    )
    root = ElementTree.fromstring(
        '<labwc_config><keyboard><default/><keybind key="0x1008ff41">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    choices = {"video_panel": "XF86Launch1", "magnifier": "XF86Launch2"}
    assert add_selected_shortcuts(root, choices) == {}  # Unknown built-in defaults.
    assert add_selected_shortcuts(root, choices, defaults_verified=True) == {
        "magnifier": "XF86Launch2"
    }
    assert root.find("keyboard/keybind[@key='0x1008ff41']/action").get("name") == "None"
    binding = root.find("keyboard/keybind[@key='XF86Launch2']")
    assert binding.attrib["onRelease"] == "yes" and binding.attrib["layoutDependent"] == "yes"
    assert binding.find("action").attrib == {
        "name": "Execute",
        "command": "/usr/local/libexec/ad-linux-tv/tv-shortcut.sh magnifier",
    }
    six = {
        "ok": "XF86Launch4",
        "volume_up": "XF86Launch5",
        "volume_down": "XF86Launch6",
    }
    assert add_selected_shortcuts(root, six, defaults_verified=True) == six
    expected = {
        "XF86Launch4": ("yes", "/usr/bin/wtype -k Return"),
        "XF86Launch5": ("no", "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%+"),
        "XF86Launch6": ("no", "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%-"),
    }
    for key, (on_release, command) in expected.items():
        node = root.find(f"keyboard/keybind[@key='{key}']")
        assert node.get("onRelease") == on_release
        assert node.find("action").get("command") == command
    combined = ElementTree.fromstring(
        '<labwc_config><keyboard><keybind key="F8-XF86Launch3">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    assert add_selected_shortcuts(combined, {"fullscreen": "XF86Launch3"}) == {}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"unknown": "XF86Launch1"},
        {"video_panel": "Return"},
        {"video_panel": "XF86OK"},
        {"video_panel": "XF86Select"},
        {"video_panel": "Left"},
        {"video_panel": "XF86AudioRaiseVolume"},
        {"video_panel": "XF86PowerOff"},
        {"ok": "Return"},
        {"volume_up": "XF86AudioRaiseVolume"},
        {"volume_down": "XF86AudioLowerVolume"},
        {"ok": "XF86Launch1", "volume_up": "XF86Launch1"},
        {"video_panel": "A-XF86Launch1"},
        {"video_panel": 'XF86Launch1" onclick="evil'},
        {"video_panel": "XF86Launch1", "fullscreen": "XF86Launch1"},
        {"video_panel": True},
    ],
)
def test_reserved_malformed_duplicate_and_unknown_keys_fail_closed(value):
    with pytest.raises(ValueError):
        validate_shortcuts(value)
