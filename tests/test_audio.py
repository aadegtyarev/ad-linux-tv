"""Audio commands are bounded and move existing streams to a selected sink."""

import json
from pathlib import Path

import pytest

from ad_linux_tv import audio


def test_volume_rejects_out_of_range_and_boolean(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "_pactl", lambda *args: calls.append(args))
    monkeypatch.setattr(audio, "_sinks", lambda: {"hdmi": {}})
    for value in (-1, 101, True, "50"):
        with pytest.raises(ValueError):
            audio.apply({"volume": value})
    with pytest.raises(ValueError):
        audio.apply({"muted": "false"})
    with pytest.raises(ValueError):
        audio.apply({"output": "unlisted"})
    assert calls == []


def test_output_selection_moves_streams_and_remembers_choice(monkeypatch, tmp_path):
    calls = []
    outputs = [
        {
            "name": "hdmi",
            "description": "HDMI",
            "volume": {"left": {"value_percent": "100%"}},
            "mute": False,
        },
        {
            "name": "bluez_output.test",
            "description": "Bluetooth speaker",
            "volume": {"left": {"value_percent": "60%"}},
            "mute": False,
        },
    ]

    def pactl(*args):
        calls.append(args)
        if args == ("-f", "json", "list", "sinks"):
            return json.dumps(outputs)
        if args == ("-f", "json", "list", "sink-inputs"):
            return json.dumps([{"index": 7}])
        if args == ("get-default-sink",):
            return "bluez_output.test"
        return ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    preference = tmp_path / "audio-output.txt"
    monkeypatch.setenv("AD_LINUX_TV_AUDIO_FILE", str(preference))
    state = audio.apply({"output": "bluez_output.test"})
    assert state["selected"] == "bluez_output.test"
    assert state["volume"] == 60
    assert ("move-sink-input", "7", "bluez_output.test") in calls
    assert preference.read_text() == "bluez_output.test\n"
    assert preference.stat().st_mode & 0o777 == 0o600


def test_failed_stream_move_restores_default_output(monkeypatch, tmp_path):
    current = "hdmi"
    calls = []

    def pactl(*args):
        nonlocal current
        calls.append(args)
        if args == ("-f", "json", "list", "sinks"):
            return json.dumps([{"name": "hdmi"}, {"name": "bluetooth"}])
        if args == ("-f", "json", "list", "sink-inputs"):
            return json.dumps([{"index": 7}])
        if args == ("get-default-sink",):
            return current
        if args[0] == "set-default-sink":
            current = args[1]
            return ""
        if args[0] == "move-sink-input":
            raise audio.AudioUnavailable
        return ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    preference = tmp_path / "audio-output.txt"
    monkeypatch.setenv("AD_LINUX_TV_AUDIO_FILE", str(preference))
    with pytest.raises(audio.AudioUnavailable):
        audio.apply({"output": "bluetooth"})
    assert current == "hdmi" and not preference.exists()
    assert calls[-1] == ("set-default-sink", "hdmi")


def test_volume_change_remembers_current_output(monkeypatch, tmp_path):
    calls = []

    def pactl(*args):
        calls.append(args)
        return "hdmi" if args == ("get-default-sink",) else ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    monkeypatch.setattr(audio, "get_state", lambda: {"volume": 45})
    preference = tmp_path / "audio-output.txt"
    monkeypatch.setenv("AD_LINUX_TV_AUDIO_FILE", str(preference))
    assert audio.apply({"volume": 45})["volume"] == 45
    assert ("set-sink-volume", "@DEFAULT_SINK@", "45%") in calls
    assert preference.read_text() == "hdmi\n"


def test_browser_volume_targets_only_firefox_streams(monkeypatch):
    calls = []
    items = [
        {
            "index": 7,
            "properties": {"application.name": "Firefox"},
            "volume": {"left": {"value_percent": "75%"}},
        },
        {
            "index": 8,
            "properties": {"application.name": "Other"},
            "volume": {"left": {"value_percent": "20%"}},
        },
    ]

    def pactl(*args):
        calls.append(args)
        if args == ("-f", "json", "list", "sink-inputs"):
            return json.dumps(items)
        return ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    monkeypatch.setattr(audio, "get_state", lambda: {"browser_volume": 55})
    assert audio.apply({"browser_volume": 55})["browser_volume"] == 55
    assert ("set-sink-input-volume", "7", "55%") in calls
    assert not any(call[0] == "set-sink-input-volume" and call[1] == "8" for call in calls)
    for value in (-1, 101, True, "55"):
        with pytest.raises(ValueError):
            audio.apply({"browser_volume": value})


def test_browser_volume_requires_active_audio(monkeypatch):
    monkeypatch.setattr(audio, "_pactl", lambda *_args: "[]")
    with pytest.raises(audio.AudioUnavailable):
        audio.apply({"browser_volume": 50})


def test_audio_sample_requires_sound_and_uses_default_sink(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "get_state", lambda: {"muted": False, "volume": 60})
    monkeypatch.setattr(
        audio.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs))
    )
    assert audio.apply({"test": True})["volume"] == 60
    assert calls[0][0][0:2] == ["/usr/bin/paplay", "--device=@DEFAULT_SINK@"]
    assert calls[0][1]["timeout"] == 5
    assert Path(calls[0][0][2]).is_file()
    with pytest.raises(ValueError):
        audio.apply({"test": False})
    monkeypatch.setattr(audio, "get_state", lambda: {"muted": True, "volume": 60})
    with pytest.raises(audio.AudioUnavailable):
        audio.apply({"test": True})
    assert len(calls) == 1
