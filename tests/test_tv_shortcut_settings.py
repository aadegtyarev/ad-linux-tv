"""Saved shortcut drafts are distinct from what the running compositor applied."""

import json
from subprocess import CompletedProcess
from xml.etree import ElementTree

import pytest
import yaml
from conftest import request
from test_config_edges import make_data
from test_settings import manager

from ad_linux_tv.kiosk_config import render_labwc
from ad_linux_tv.settings import SettingsError, SettingsManager
from ad_linux_tv.tv_shortcut_keys import KEYSYMS


def test_shortcut_ui_asset_is_served(endpoint):
    connection, _port = endpoint
    response, body = request(connection, "GET", "/tv_shortcut_controls.js")
    assert response.status == 200
    assert b"class TvShortcutControls" in body


def test_saved_applied_and_rejected_bindings_are_distinct(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    settings, sessions, path, profile = manager(tmp_path)
    token, _ = sessions.create()
    assert settings.state()["tv_shortcuts"] == {}
    assert settings.state()["tv_shortcuts_applied"] is None
    draft = {"video_panel": "XF86Launch1"}
    template = tmp_path / "template.xml"
    template.write_text(
        "<labwc_config><keyboard><default/></keyboard><magnifier><initScale>2.5</initScale></magnifier></labwc_config>"
    )
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: True)
    mapping = {key.casefold(): value for key, value in KEYSYMS.items()}
    monkeypatch.setattr(
        "ad_linux_tv.kiosk_config._keysym_parser",
        lambda: lambda raw, _flags: mapping.get(raw.decode().casefold(), 0),
    )
    settings.shortcut_template = template
    settings.update({"setting": "tv_shortcuts", "value": {"expected": {}, "assignments": draft}})
    assert sessions.valid(token)
    assert settings.state()["tv_shortcuts_restart_required"]
    assert yaml.safe_load(path.read_text())["tv_shortcuts"] == draft
    config_before = path.read_bytes()
    render_labwc(path, template, runtime / "ad-linux-tv-labwc")
    assert path.read_bytes() == config_before
    root = ElementTree.parse(runtime / "ad-linux-tv-labwc/rc.xml").getroot()
    assert root.find("keyboard/keybind[@key='XF86Launch1']") is not None
    booted = SettingsManager(yaml.safe_load(path.read_text()), path, sessions, profile=profile)
    assert booted.state()["tv_shortcuts_applied"] == draft
    assert not booted.state()["tv_shortcuts_restart_required"]
    assert not booted.state()["tv_shortcuts_unavailable"]
    booted.update({"setting": "tv_shortcuts", "value": {"expected": draft, "assignments": {}}})
    assert booted.state()["tv_shortcuts_restart_required"]
    assert "tv_shortcuts" not in yaml.safe_load(path.read_text())


def test_save_rejects_conflicting_or_unknown_compositor_before_persistence(tmp_path, monkeypatch):
    settings, sessions, path, _profile = manager(tmp_path)
    token, _ = sessions.create()
    template = tmp_path / "rc.xml"
    template.write_text(
        '<labwc_config><keyboard><default/><keybind key="XF86Launch1">'
        '<action name="None"/></keybind></keyboard></labwc_config>'
    )
    settings.shortcut_template = template
    mapping = {key.casefold(): value for key, value in KEYSYMS.items()}
    monkeypatch.setattr(
        "ad_linux_tv.kiosk_config._keysym_parser",
        lambda: lambda raw, _flags: mapping.get(raw.decode().casefold(), 0),
    )
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: True)
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        settings.update(
            {
                "setting": "tv_shortcuts",
                "value": {"expected": {}, "assignments": {"video_panel": "XF86Launch1"}},
            }
        )
    assert path.read_bytes() == before and sessions.valid(token)
    template.write_text("<labwc_config><keyboard><default/></keyboard></labwc_config>")
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: False)
    with pytest.raises(SettingsError):
        settings.update(
            {
                "setting": "tv_shortcuts",
                "value": {"expected": {}, "assignments": {"video_panel": "XF86Launch2"}},
            }
        )
    assert path.read_bytes() == before


def test_prior_three_action_receipt_and_config_remain_valid(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime/ad-linux-tv-labwc"
    runtime.mkdir(parents=True)
    original = {
        "video_panel": "XF86Launch1",
        "magnifier": "XF86Launch2",
        "fullscreen": "XF86Launch3",
    }
    (runtime / "shortcuts-applied.json").write_text(
        json.dumps({"requested": original, "applied": original})
    )
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime.parent))
    settings, sessions, path, profile = manager(tmp_path)
    config = dict(make_data(), tv_shortcuts=original)
    path.write_text(yaml.safe_dump(config))
    settings = SettingsManager(config, path, sessions, profile=profile)
    assert settings.state()["tv_shortcuts_applied"] == original
    assert not settings.state()["tv_shortcuts_restart_required"]
    monkeypatch.setattr(settings, "_preflight_shortcuts", lambda _value: None)
    expanded = dict(original, ok="XF86Launch4", volume_up="XF86Launch5", volume_down="XF86Launch6")
    state = settings.update(
        {"setting": "tv_shortcuts", "value": {"expected": original, "assignments": expanded}}
    )
    assert state["tv_shortcuts"] == expanded and state["tv_shortcuts_applied"] == original
    assert state["tv_shortcuts_restart_required"]


def test_stale_phone_cannot_overwrite_newer_shortcut_mapping(tmp_path, monkeypatch):
    settings, sessions, path, _profile = manager(tmp_path)
    monkeypatch.setattr(settings, "_preflight_shortcuts", lambda _value: None)
    first = {"video_panel": "XF86Launch1"}
    settings.update({"setting": "tv_shortcuts", "value": {"expected": {}, "assignments": first}})
    before = path.read_bytes()
    token, _ = sessions.create()
    with pytest.raises(SettingsError):
        settings.update(
            {
                "setting": "tv_shortcuts",
                "value": {"expected": {}, "assignments": {"fullscreen": "XF86Launch2"}},
            }
        )
    assert path.read_bytes() == before and sessions.valid(token)
    assert settings.state()["tv_shortcuts"] == first


def test_unavailable_binding_can_be_removed_without_revalidating_others(tmp_path, monkeypatch):
    settings, sessions, path, profile = manager(tmp_path)
    saved = {"video_panel": "XF86Launch1", "fullscreen": "XF86Launch2"}
    config = dict(make_data(), tv_shortcuts=saved)
    path.write_text(yaml.safe_dump(config))
    settings = SettingsManager(config, path, sessions, profile=profile)
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: False)
    assert settings.update(
        {
            "setting": "tv_shortcuts",
            "value": {"expected": saved, "assignments": {"fullscreen": "XF86Launch2"}},
        }
    )["tv_shortcuts"] == {"fullscreen": "XF86Launch2"}
    assert yaml.safe_load(path.read_text())["tv_shortcuts"] == {"fullscreen": "XF86Launch2"}


def test_magnifier_shortcut_uses_existing_toggle_and_keeps_phone_state(tmp_path, monkeypatch):
    settings, _sessions, _path, _profile = manager(tmp_path)
    calls = []
    monkeypatch.setattr(
        "ad_linux_tv.settings.subprocess.run",
        lambda argv, **_kwargs: (calls.append(argv), CompletedProcess(argv, 0))[1],
    )
    assert settings.update({"setting": "magnifier_toggle", "value": True})["magnifier"] is True
    assert settings.update({"setting": "magnifier_toggle", "value": True})["magnifier"] is False
    assert calls == [["/usr/bin/wtype", "-k", "F9"], ["/usr/bin/wtype", "-k", "F9"]]
    with pytest.raises(SettingsError):
        settings.update({"setting": "magnifier_toggle", "value": False})


def test_renderer_reports_existing_binding_conflict_without_overwriting_it(tmp_path, monkeypatch):
    config = dict(make_data(), tv_shortcuts={"video_panel": "XF86Launch1"})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    template = tmp_path / "template.xml"
    template.write_text(
        '<labwc_config><keyboard><default/><keybind key="0x1008ff41">'
        '<action name="None"/></keybind></keyboard>'
        "<magnifier><initScale>2.5</initScale></magnifier></labwc_config>"
    )
    mapping = {key.casefold(): value for key, value in KEYSYMS.items()}
    mapping["0x1008ff41"] = KEYSYMS["XF86Launch1"]
    monkeypatch.setattr("ad_linux_tv.kiosk_config._known_labwc_defaults", lambda: True)
    monkeypatch.setattr(
        "ad_linux_tv.kiosk_config._keysym_parser",
        lambda: lambda raw, _flags: mapping.get(raw.decode().casefold(), 0),
    )
    out = tmp_path / "runtime"
    render_labwc(path, template, out)
    state = json.loads((out / "shortcuts-applied.json").read_text())
    assert state == {"requested": {"video_panel": "XF86Launch1"}, "applied": {}}
    root = ElementTree.parse(out / "rc.xml").getroot()
    assert root.find("keyboard/keybind[@key='0x1008ff41']/action").get("name") == "None"
    assert root.find("keyboard/keybind[@key='XF86Launch1']") is None


@pytest.mark.parametrize("invalid", [False, True])
def test_unknown_boot_receipt_still_requires_restart_after_last_clear(
    tmp_path, monkeypatch, invalid
):
    runtime = tmp_path / "runtime/ad-linux-tv-labwc"
    runtime.mkdir(parents=True)
    if invalid:
        (runtime / "shortcuts-applied.json").write_text('{"requested":')
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime.parent))
    settings, sessions, path, profile = manager(tmp_path)
    saved = {"video_panel": "XF86Launch1"}
    config = dict(make_data(), tv_shortcuts=saved)
    path.write_text(yaml.safe_dump(config))
    settings = SettingsManager(config, path, sessions, profile=profile)
    assert settings.state()["tv_shortcuts_applied"] is None
    settings.update({"setting": "tv_shortcuts", "value": {"expected": saved, "assignments": {}}})
    assert settings.state()["tv_shortcuts_restart_required"]
    assert settings.state()["restart_required"]
    # A server-only restart does not falsely claim the compositor cleared it.
    restarted = SettingsManager(yaml.safe_load(path.read_text()), path, sessions, profile=profile)
    assert restarted.state()["tv_shortcuts_restart_required"]


def test_kiosk_without_runtime_environment_does_not_claim_bindings_are_cleared(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    settings, _sessions, _path, _profile = manager(tmp_path)
    assert settings.state()["tv_shortcuts_applied"] is None
    assert settings.state()["tv_shortcuts_restart_required"]


def test_unavailable_at_boot_is_not_an_endless_restart_prompt(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime/ad-linux-tv-labwc"
    runtime.mkdir(parents=True)
    draft = {"video_panel": "XF86Launch1"}
    (runtime / "shortcuts-applied.json").write_text(json.dumps({"requested": draft, "applied": {}}))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime.parent))
    settings, _sessions, path, profile = manager(tmp_path)
    config = dict(make_data(), tv_shortcuts=draft)
    path.write_text(yaml.safe_dump(config))
    booted = SettingsManager(config, path, settings.sessions, profile=profile)
    assert not booted.state()["tv_shortcuts_restart_required"]
    assert booted.state()["tv_shortcuts_unavailable"]
    with pytest.raises(SettingsError):
        booted.update(
            {
                "setting": "tv_shortcuts",
                "value": {"expected": draft, "assignments": {"video_panel": "Return"}},
            }
        )
    assert yaml.safe_load(path.read_text())["tv_shortcuts"] == draft
