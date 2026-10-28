"""Scale persistence/runtime XML use temporary paths and no actual compositor/input."""

from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml
from test_config_edges import make_data
from test_settings import manager

from ad_linux_tv.config import load_config
from ad_linux_tv.kiosk_config import render_labwc
from ad_linux_tv.magnifier import validate_magnifier
from ad_linux_tv.settings import SettingsError, SettingsManager


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


def test_runtime_template_keeps_bindings_and_never_exports_auth_or_mutates_config(tmp_path):
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
    assert root.find("keyboard/keybind[@key='F9']/action").attrib["name"] == "ToggleMagnify"
    assert root.find("magnifier/width").text == "440"
    assert data["auth"]["verifier"] not in generated.read_text()
    assert generated.stat().st_mode & 0o777 == 0o600
