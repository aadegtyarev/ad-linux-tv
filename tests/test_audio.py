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


def sink(name, port_type=None, available=True, description=None, volume="100%"):
    item = {"name": name, "volume": {"left": {"value_percent": volume}}, "mute": False}
    if description:
        item["description"] = description
    if port_type:
        port = f"[Out] {port_type}"
        item["active_port"] = port
        item["ports"] = [
            {
                "name": port,
                "type": port_type,
                "availability": "available" if available else "not available",
                "description": f"{port_type} Output",
            }
        ]
    return item


def test_output_selection_uses_stable_ids_and_moves_streams(monkeypatch):
    calls = []
    outputs = [
        sink("card.HiFi__HDMI1__sink.2", "HDMI", description="Long card name HDMI"),
        sink("card.HiFi__Headphones__sink", "Headphones", available=False),
        sink("bluez_output.test", description="Bluetooth speaker", volume="60%"),
    ]
    default = "card.HiFi__HDMI1__sink.2"

    def pactl(*args):
        nonlocal default
        calls.append(args)
        if args == ("-f", "json", "list", "sinks"):
            return json.dumps(outputs)
        if args == ("-f", "json", "list", "sink-inputs"):
            return json.dumps([{"index": 7}])
        if args == ("get-default-sink",):
            return default
        if args[0] == "set-default-sink":
            default = args[1]
        return ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    state = audio.get_state()
    assert state["outputs"] == [
        {"id": "card.HiFi__HDMI1__sink", "name": "HDMI Output"},
        {"id": "bluez_output.test", "name": "Bluetooth speaker"},
    ]
    assert state["selected"] == "card.HiFi__HDMI1__sink"
    state = audio.apply({"output": "bluez_output.test"})
    assert state["selected"] == "bluez_output.test"
    assert state["volume"] == 60
    assert ("move-sink-input", "7", "bluez_output.test") in calls
    audio.apply({"output": "card.HiFi__HDMI1__sink"})
    assert default == "card.HiFi__HDMI1__sink.2"


def test_startup_choice_prefers_saved_then_connected_hdmi():
    sinks = {
        "card.HiFi__Speaker__sink": sink("card.HiFi__Speaker__sink"),
        "card.HiFi__HDMI2__sink.3": sink("card.HiFi__HDMI2__sink.3", "HDMI", available=False),
        "card.HiFi__HDMI1__sink.3": sink("card.HiFi__HDMI1__sink.3", "HDMI"),
    }
    assert audio.choose_output(sinks) == "card.HiFi__HDMI1__sink.3"
    assert audio.choose_output(sinks, "card.HiFi__Speaker__sink") == "card.HiFi__Speaker__sink"
    # A saved but disconnected output falls back to the connected HDMI.
    assert audio.choose_output(sinks, "card.HiFi__HDMI2__sink") == "card.HiFi__HDMI1__sink.3"
    assert audio.choose_output({"spk": sink("spk")}) is None


def test_startup_selection_sets_full_level_only_without_saved_output(monkeypatch, tmp_path):
    calls = []
    sinks = [sink("card.HiFi__HDMI1__sink.2", "HDMI")]

    def pactl(*args):
        calls.append(args)
        if args == ("-f", "json", "list", "sinks"):
            return json.dumps(sinks)
        return "other" if args == ("get-default-sink",) else ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    assert audio.select_saved_output(None) is True
    assert ("set-default-sink", "card.HiFi__HDMI1__sink.2") in calls
    assert ("set-sink-volume", "card.HiFi__HDMI1__sink.2", "100%") in calls
    calls.clear()
    assert audio.select_saved_output("card.HiFi__HDMI1__sink") is True
    assert not [call for call in calls if call[0] == "set-sink-volume"]
    sinks.clear()
    assert audio.select_saved_output(None) is False


def test_failed_stream_move_restores_default_output(monkeypatch):
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
    with pytest.raises(audio.AudioUnavailable):
        audio.apply({"output": "bluetooth"})
    assert current == "hdmi"
    assert calls[-1] == ("set-default-sink", "hdmi")


def test_volume_change_applies_to_default_output(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "_pactl", lambda *args: calls.append(args) or "")
    monkeypatch.setattr(audio, "get_state", lambda: {"volume": 45})
    assert audio.apply({"volume": 45})["volume"] == 45
    assert ("set-sink-volume", "@DEFAULT_SINK@", "45%") in calls


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


def test_firefox_mute_affects_only_firefox_streams_and_requires_one(monkeypatch):
    calls = []
    inputs = [
        {"index": 7, "properties": {"application.name": "Firefox"}, "mute": True},
        {"index": 8, "properties": {"application.name": "Other"}, "mute": True},
        {"index": 9, "properties": {"application.name": "Firefox"}, "mute": True},
    ]

    def pactl(*args):
        calls.append(args)
        if args == ("-f", "json", "list", "sink-inputs"):
            return json.dumps(inputs)
        return ""

    monkeypatch.setattr(audio, "_pactl", pactl)
    monkeypatch.setattr(audio, "get_state", lambda: {"browser_muted": False})
    assert audio.apply({"browser_muted": False})["browser_muted"] is False
    assert ("set-sink-input-mute", "7", "0") in calls
    assert ("set-sink-input-mute", "9", "0") in calls
    assert ("set-sink-input-mute", "8", "0") not in calls
    with pytest.raises(ValueError):
        audio.apply({"browser_muted": 0})
    inputs[:] = [inputs[1]]
    with pytest.raises(audio.AudioUnavailable):
        audio.apply({"browser_muted": False})


def test_audio_state_reports_firefox_stream_mute(monkeypatch):
    monkeypatch.setattr(
        audio,
        "_sinks",
        lambda: {"hdmi": {"mute": False, "volume": {"left": {"value_percent": "80%"}}}},
    )
    monkeypatch.setattr(audio, "_pactl", lambda *_args: "hdmi")
    inputs = [{"mute": True, "volume": {"left": {"value_percent": "100%"}}}]
    monkeypatch.setattr(audio, "_browser_inputs", lambda: inputs)
    assert audio.get_state()["browser_muted"] is True
    inputs[0]["mute"] = False
    assert audio.get_state()["browser_muted"] is False
    inputs.clear()
    assert audio.get_state()["browser_muted"] is None


def test_browser_streams_return_to_neutral_without_changing_output(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "_pactl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        audio,
        "_browser_inputs",
        lambda: [
            {"index": 4, "volume": {"front-left": {"value_percent": "55%"}}},
            {"index": 5, "volume": {"front-left": {"value_percent": "100%"}}},
        ],
    )
    audio.normalize_browser_volume()
    assert calls == [("set-sink-input-volume", "4", "100%")]


def test_browser_streams_follow_saved_target(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "_pactl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        audio,
        "_browser_inputs",
        lambda: [{"index": 4, "volume": {"left": {"value_percent": "100%"}}}],
    )
    audio.normalize_browser_volume(35)
    assert calls == [("set-sink-input-volume", "4", "35%")]


def test_browser_mute_normalizer_uses_saved_target(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "_pactl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        audio,
        "_browser_inputs",
        lambda: [{"index": 4, "mute": True}, {"index": 5, "mute": False}],
    )
    audio.normalize_browser_mute(False)
    assert calls == [("set-sink-input-mute", "4", "0")]


def test_non_browser_stream_blocks_sleep(monkeypatch):
    import json

    streams = [
        {"properties": {"application.process.binary": "firefox"}},
        {"properties": {"application.process.binary": "sd_dummy"}},
        {"properties": {"application.name": "Music Player"}},
    ]
    monkeypatch.setattr(audio, "_pactl", lambda *_args: json.dumps(streams))
    assert audio.non_browser_audio_present() is True
    streams.pop()
    assert audio.non_browser_audio_present() is False


def test_corked_firefox_stream_is_not_audible(monkeypatch):
    monkeypatch.setattr(audio, "_browser_inputs", lambda: [{"corked": True, "mute": False}])
    assert audio.browser_audio_active() is False
    monkeypatch.setattr(audio, "_browser_inputs", lambda: [{"corked": False, "mute": False}])
    assert audio.browser_audio_active() is True


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
