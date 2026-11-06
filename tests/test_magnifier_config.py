"""Scale persistence/runtime XML use temporary paths and no actual compositor/input."""

from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml
from test_config_edges import make_data
from test_settings import manager

from ad_linux_tv.config import load_config
from ad_linux_tv.kiosk_config import (
    _keysym_parser,
    add_default_ok_bindings,
    add_default_volume_bindings,
    render_labwc,
)
from ad_linux_tv.magnifier import validate_magnifier
from ad_linux_tv.settings import SettingsError, SettingsManager


@pytest.fixture
def fake_keysyms(monkeypatch):
    def parse(raw, _flags):
        name = raw.decode().replace("_", "").casefold()
        if name.startswith("0x"):
            try:
                return int(name, 16)
            except ValueError:
                return 0
        return {
            "xf86ok": 0x10081160,
            "xf86select": 0x1008FFA0,
            "xf86audioraisevolume": 0x1008FF13,
            "xf86audiolowervolume": 0x1008FF11,
        }.get(name, 0)

    monkeypatch.setattr("ad_linux_tv.kiosk_config._keysym_parser", lambda: parse)


def test_real_xkb_parser_when_available():
    parser = _keysym_parser()
    if parser is None:
        pytest.skip("libxkbcommon unavailable")
    assert parser(b"XF86_Select", 1) == 0x1008FFA0
    assert parser(b"0x1008ffa0", 1) == 0x1008FFA0


@pytest.mark.parametrize("value", [True, None, "2.5", 1, 5.25, 2.3, float("inf"), float("nan")])
def test_scale_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_magnifier({"scale": value})


def test_optional_config_default_and_explicit_validated_scale(tmp_path):
    path = tmp_path / "config.yaml"
    data = make_data()
    path.write_text(yaml.safe_dump(data))
    before = path.read_bytes()
    assert "magnifier" not in load_config(path)
    assert path.read_bytes() == before
    data["magnifier"] = {"scale": 3.25}
    path.write_text(yaml.safe_dump(data))
    assert load_config(path)["magnifier"] == {"scale": 3.25}
    data["magnifier"] = {"scale": 3, "script": "not allowed"}
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_config(path)


def test_scale_save_does_not_actuate_and_server_restart_does_not_fake_application(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AD_LINUX_TV_MAGNIFIER_SCALE", "2.5")
    settings, sessions, path, profile = manager(tmp_path)
    token, _ = sessions.create()
    monkeypatch.setattr(
        "ad_linux_tv.settings.subprocess.run", lambda *_a, **_k: pytest.fail("no input/restart")
    )
    assert settings.state()["magnifier_scale"] == 2.5
    settings.update({"setting": "magnifier_scale", "value": 3.5})
    assert load_config(path)["magnifier"] == {"scale": 3.5}
    assert sessions.valid(token)
    assert settings.state()["restart_required"]
    assert settings.state()["magnifier_applied_scale"] == 2.5
    restarted = SettingsManager(load_config(path), path, sessions, profile=profile)
    assert restarted.state()["restart_required"]
    assert restarted.state()["magnifier_applied_scale"] == 2.5
    monkeypatch.setenv("AD_LINUX_TV_MAGNIFIER_SCALE", "3.5")
    booted = SettingsManager(load_config(path), path, sessions, profile=profile)
    assert booted.state()["restart_required"] is False
    assert booted.state()["magnifier_applied_scale"] == 3.5
    for invalid in (True, "3", 0, 20, 2.3):
        with pytest.raises(SettingsError):
            settings.update({"setting": "magnifier_scale", "value": invalid})
    settings.update({"setting": "magnifier_scale", "value": 2.5})
    assert settings.state()["restart_required"] is False


def test_runtime_template_keeps_bindings_and_never_exports_auth_or_mutates_config(
    tmp_path, monkeypatch, fake_keysyms
):
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: True)
    data = make_data()
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    template = Path(__file__).resolve().parents[1] / "ops/kiosk/labwc/rc.xml"
    destination = tmp_path / "runtime"
    before = path.read_bytes()
    assert render_labwc(path, template, destination) == 2.5
    assert path.read_bytes() == before
    data["magnifier"] = {"scale": 4.25}
    path.write_text(yaml.safe_dump(data))
    assert render_labwc(path, template, destination) == 4.25
    generated = destination / "rc.xml"
    root = ElementTree.fromstring(generated.read_text())
    assert root.find("magnifier/initScale").text == "4.25"
    assert root.find("keyboard/default") is not None
    assert root.find("keyboard/keybind[@key='F9']/action").attrib["name"] == "ToggleMagnify"
    for name in ("XF86_AudioRaiseVolume", "XF86_AudioLowerVolume"):
        assert (
            root.find(f"keyboard/keybind[@key='{name}']/action")
            .get("command")
            .startswith("/usr/bin/wpctl ")
        )
    for name in ("XF86OK", "XF86Select"):
        binding = root.find(f"keyboard/keybind[@key='{name}']")
        assert binding.attrib == {"key": name, "onRelease": "yes", "layoutDependent": "yes"}
        assert binding.find("action").attrib == {
            "name": "Execute",
            "command": "/usr/bin/wtype -k Return",
        }
    assert root.find("magnifier/width").text == "440"
    assert data["auth"]["verifier"] not in generated.read_text()
    assert generated.stat().st_mode & 0o777 == 0o600


def test_ok_defaults_respect_explicit_bindings_and_avoid_disabling_compositor_defaults(
    fake_keysyms,
):
    root = ElementTree.fromstring(
        '<labwc_config><keyboard><default/><keybind key="XF86_Select">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    add_default_ok_bindings(root, defaults_verified=True)
    assert len(root.findall("keyboard/keybind")) == 2
    assert root.find("keyboard/keybind[@key='XF86_Select']/action").get("name") == "None"
    assert root.find("keyboard/keybind[@key='XF86OK']") is not None
    add_default_ok_bindings(root, defaults_verified=True)
    assert len(root.findall("keyboard/keybind")) == 2
    for markup in (
        "<labwc_config/>",
        "<labwc_config><keyboard/></labwc_config>",
        "<labwc_config><keyboard><repeatRate>25</repeatRate></keyboard></labwc_config>",
    ):
        root = ElementTree.fromstring(markup)
        add_default_ok_bindings(root, defaults_verified=True)
        assert root.find("keyboard/default") is not None
        assert len(root.findall("keyboard/keybind")) == 2

    numeric = ElementTree.fromstring(
        '<labwc_config><keyboard><keybind key="0x1008ffa0"><action name="None"/>'
        "</keybind></keyboard></labwc_config>"
    )
    add_default_ok_bindings(numeric)
    assert len(numeric.findall("keyboard/keybind")) == 2
    assert numeric.find("keyboard/keybind[@key='XF86Select']") is None
    assert numeric.find("keyboard/keybind[@key='0x1008ffa0']/action").get("name") == "None"

    combined = ElementTree.fromstring(
        '<labwc_config><keyboard><keybind key="F8-XF86_Select"><action name="None"/>'
        "</keybind></keyboard></labwc_config>"
    )
    add_default_ok_bindings(combined)
    assert combined.find("keyboard/keybind[@key='XF86Select']") is None
    assert combined.find("keyboard/keybind[@key='XF86OK']") is not None

    custom = ElementTree.fromstring(
        '<labwc_config><keyboard><keybind key="F8"><action name="None"/>'
        "</keybind></keyboard></labwc_config>"
    )
    add_default_ok_bindings(custom)
    assert custom.find("keyboard/default") is None  # No implicit defaults before the change.
    assert custom.find("keyboard/keybind[@key='F8']/action").get("name") == "None"


def test_volume_defaults_upgrade_only_missing_binds_and_preserve_custom(fake_keysyms):
    root = ElementTree.fromstring(
        '<labwc_config><keyboard><default/><keybind key="XF86AudioRaiseVolume">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    add_default_volume_bindings(root, defaults_verified=False)
    assert len(root.findall("keyboard/keybind")) == 1
    add_default_volume_bindings(root, defaults_verified=True)
    assert root.find("keyboard/keybind[@key='XF86AudioRaiseVolume']/action").get("name") == "None"
    down = root.find("keyboard/keybind[@key='XF86_AudioLowerVolume']/action")
    assert down.get("command") == "/usr/bin/wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 5%-"
    add_default_volume_bindings(root, defaults_verified=True)
    assert len(root.findall("keyboard/keybind")) == 2
    no_defaults = ElementTree.fromstring(
        '<labwc_config><keyboard><keybind key="F8"/></keyboard></labwc_config>'
    )
    add_default_volume_bindings(no_defaults, defaults_verified=True)
    assert len(no_defaults.findall("keyboard/keybind")) == 1
    numeric = ElementTree.fromstring(
        '<labwc_config><keyboard><default/><keybind key="F8-0x1008ff13">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    add_default_volume_bindings(numeric, defaults_verified=True)
    assert numeric.find("keyboard/keybind[@key='XF86_AudioRaiseVolume']") is None
    assert numeric.find("keyboard/keybind[@key='XF86_AudioLowerVolume']") is not None


def test_existing_install_gets_volume_defaults_in_runtime_without_changing_template(
    tmp_path, monkeypatch, fake_keysyms
):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(make_data()))
    template = tmp_path / "rc.xml"
    template.write_text(
        "<labwc_config><keyboard><default/></keyboard><magnifier><initScale>2.5</initScale></magnifier></labwc_config>"
    )
    before = template.read_bytes()
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: True)
    render_labwc(path, template, tmp_path / "runtime")
    root = ElementTree.parse(tmp_path / "runtime/rc.xml").getroot()
    assert (
        root.find("keyboard/keybind[@key='XF86_AudioRaiseVolume']/action")
        .get("command")
        .endswith("5%+")
    )
    assert (
        root.find("keyboard/keybind[@key='XF86_AudioLowerVolume']/action")
        .get("command")
        .endswith("5%-")
    )
    assert template.read_bytes() == before


def test_ok_defaults_fail_closed_for_unknown_implicit_or_explicit_defaults(fake_keysyms):
    for markup in (
        "<labwc_config><keyboard><default/></keyboard></labwc_config>",
        "<labwc_config><keyboard/></labwc_config>",
    ):
        root = ElementTree.fromstring(markup)
        add_default_ok_bindings(root, defaults_verified=False)
        assert root.find("keyboard/default") is not None
        assert not root.findall("keyboard/keybind")


def test_runtime_does_not_insert_ok_defaults_on_unknown_labwc(tmp_path, monkeypatch, fake_keysyms):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(make_data()))
    template = Path(__file__).resolve().parents[1] / "ops/kiosk/labwc/rc.xml"
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: False)
    render_labwc(path, template, tmp_path / "runtime")
    root = ElementTree.parse(tmp_path / "runtime/rc.xml").getroot()
    assert root.find("keyboard/default") is not None
    assert root.find("keyboard/keybind[@key='XF86OK']") is None
    assert root.find("keyboard/keybind[@key='XF86Select']") is None
    assert root.find("keyboard/keybind[@key='XF86_AudioRaiseVolume']") is not None


def test_ok_defaults_skip_unsupported_keysyms(monkeypatch, capsys):
    def parser(raw, _flags):
        return 0x1008FFA0 if raw.decode().replace("_", "").casefold() == "xf86select" else 0

    monkeypatch.setattr("ad_linux_tv.kiosk_config._keysym_parser", lambda: parser)
    root = ElementTree.fromstring("<labwc_config><keyboard><default/></keyboard></labwc_config>")
    add_default_ok_bindings(root, defaults_verified=True)
    assert root.find("keyboard/keybind[@key='XF86Select']") is not None
    assert root.find("keyboard/keybind[@key='XF86OK']") is None
    assert "XF86OK unsupported" in capsys.readouterr().err


def test_ok_defaults_fail_closed_without_keysym_parser(monkeypatch):
    monkeypatch.setattr("ad_linux_tv.kiosk_config._keysym_parser", lambda: None)
    root = ElementTree.fromstring("<labwc_config><keyboard/></labwc_config>")
    add_default_ok_bindings(root)
    assert root.find("keyboard/default") is not None
    assert not root.findall("keyboard/keybind")
