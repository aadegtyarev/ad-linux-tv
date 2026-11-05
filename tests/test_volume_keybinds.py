"""The TV compositor's physical volume keys target the software output."""

from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def test_volume_keys_replace_defaults_with_bounded_software_sink_commands():
    root = ElementTree.parse(ROOT / "ops/kiosk/labwc/rc.xml").getroot()
    keyboard = root.find("keyboard")
    assert keyboard is not None
    children = list(keyboard)
    default = next(i for i, element in enumerate(children) if element.tag == "default")
    for key, command in {
        "XF86_AudioRaiseVolume": "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%+",
        "XF86_AudioLowerVolume": "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%-",
    }.items():
        matches = [(i, element) for i, element in enumerate(children) if element.get("key") == key]
        assert len(matches) == 1
        index, binding = matches[0]
        assert index > default  # labwc uses the later duplicate in preference to the default.
        actions = binding.findall("action")
        assert len(actions) == 1
        assert actions[0].attrib == {"name": "Execute", "command": command}


def test_volume_command_is_supplied_by_an_existing_kiosk_dependency():
    setup = (ROOT / "ops/kiosk/setup.sh").read_text()
    assert "wireplumber" in setup
