"""Bluetooth persistence uses the existing private, serialized settings writer."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import yaml
from test_settings import manager

from ad_linux_tv.config import load_config
from ad_linux_tv.settings import SettingsError


def remote():
    return {
        "remote": {
            "identity": {
                "adapter": "AA:BB:CC:DD:EE:FF",
                "address": "11:22:33:44:55:66",
                "address_type": "public",
            },
            "bindings": {"KEY_ENTER": "ok"},
        }
    }


def test_legacy_absence_and_disabled_noop_do_not_rewrite(tmp_path):
    settings, _sessions, path, _profile = manager(tmp_path)
    before = path.read_bytes()
    assert "bluetooth" not in load_config(path)
    assert settings.bluetooth_config() == {"remote": None}
    settings.set_bluetooth({"remote": None})
    assert path.read_bytes() == before
    assert "bluetooth" not in settings.config


def test_targeted_private_save_detaches_data_and_preserves_other_state(tmp_path):
    settings, sessions, path, profile = manager(tmp_path)
    token, _ = sessions.create()
    before = copy.deepcopy(settings.config)
    shared = settings.config
    prefs = (profile / "user.js").read_bytes()
    value = remote()
    settings.set_bluetooth(value)
    assert settings.config is shared
    assert load_config(path) == dict(before, bluetooth=value)
    assert path.stat().st_mode & 0o777 == 0o600
    assert sessions.valid(token)
    assert (profile / "user.js").read_bytes() == prefs
    assert "bluetooth" not in settings.state()
    assert "identity" not in settings.state()
    value["remote"]["bindings"]["KEY_ENTER"] = "home"
    result = settings.bluetooth_config()
    result["remote"]["identity"]["address"] = "22:33:44:55:66:77"
    assert settings.bluetooth_config() == remote()
    assert load_config(path)["bluetooth"] == remote()
    settings.set_bluetooth({"remote": None})
    assert load_config(path) == dict(before, bluetooth={"remote": None})
    assert sessions.valid(token)


@pytest.mark.parametrize("value", [None, {}, {"remote": True}, {"remote": None, "pin": "secret"}])
def test_invalid_section_rejected_on_load_and_save(tmp_path, value):
    settings, _sessions, path, _profile = manager(tmp_path)
    before = path.read_bytes()
    shared = copy.deepcopy(settings.config)
    with pytest.raises(SettingsError, match="invalid Bluetooth configuration"):
        settings.set_bluetooth(value)
    assert path.read_bytes() == before
    assert settings.config == shared
    path.write_text(yaml.safe_dump(dict(shared, bluetooth=value)))
    with pytest.raises(ValueError) as error:
        load_config(path)
    assert str(error.value) == "Invalid configuration: invalid Bluetooth configuration"


def test_noop_save_does_not_write_and_generic_setting_cannot_bypass_owner(tmp_path, monkeypatch):
    settings, _sessions, _path, _profile = manager(tmp_path)
    settings.set_bluetooth(remote())

    def forbidden_write(*_args):
        pytest.fail("unchanged Bluetooth value must not write")

    monkeypatch.setattr(settings, "_save_config", forbidden_write)
    settings.set_bluetooth(remote())
    with pytest.raises(SettingsError):
        settings.update({"setting": "bluetooth", "value": remote()})


def test_failed_atomic_write_preserves_shared_config_and_sessions(tmp_path, monkeypatch):
    settings, sessions, path, _profile = manager(tmp_path)
    token, _ = sessions.create()
    before = path.read_bytes()
    shared = settings.config
    snapshot = copy.deepcopy(shared)

    def fail(*_args):
        raise OSError("simulated write failure")

    monkeypatch.setattr("ad_linux_tv.settings.atomic_write", fail)
    with pytest.raises(OSError):
        settings.set_bluetooth(remote())
    assert settings.config is shared
    assert shared == snapshot
    assert path.read_bytes() == before
    assert sessions.valid(token)


def test_serialized_bluetooth_and_audio_updates_both_survive(tmp_path, monkeypatch):
    settings, _sessions, path, _profile = manager(tmp_path)
    entered = Event()
    release = Event()
    audio_started = Event()
    save = settings._save_config

    def slow_save(candidate):
        if "bluetooth" in candidate and "audio" not in candidate:
            entered.set()
            assert release.wait(3)
        save(candidate)

    def audio_update():
        audio_started.set()
        settings.set_audio_level("browser", 42)

    monkeypatch.setattr(settings, "_save_config", slow_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        bluetooth_future = pool.submit(settings.set_bluetooth, remote())
        try:
            assert entered.wait(3)
            audio_future = pool.submit(audio_update)
            assert audio_started.wait(3)
        finally:
            release.set()
        bluetooth_future.result(timeout=3)
        audio_future.result(timeout=3)
    loaded = load_config(path)
    assert loaded["bluetooth"] == remote()
    assert loaded["audio"] == {"browser": 42, "player": 100}
    assert settings.bluetooth_config() == remote()
