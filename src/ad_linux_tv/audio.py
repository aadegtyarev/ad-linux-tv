"""Audio controls for the dedicated TV user's PipeWire/PulseAudio session."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


class AudioUnavailable(Exception):
    """The session audio server or selected output is unavailable."""


def _pactl(*args):
    try:
        return subprocess.run(
            ["/usr/bin/pactl", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AudioUnavailable from exc


def _sinks():
    try:
        data = json.loads(_pactl("-f", "json", "list", "sinks"))
        return {sink["name"]: sink for sink in data}
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioUnavailable from exc


def _browser_inputs():
    try:
        inputs = json.loads(_pactl("-f", "json", "list", "sink-inputs"))
        return [item for item in inputs if _is_firefox(item)]
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioUnavailable from exc


def _is_firefox(item):
    properties = item.get("properties", {})
    return (
        properties.get("application.process.binary") == "firefox"
        or properties.get("application.name") == "Firefox"
    )


def non_browser_audio_present():
    """Be conservative if another application has an output stream."""
    try:
        inputs = json.loads(_pactl("-f", "json", "list", "sink-inputs"))
        return any(not _is_firefox(item) for item in inputs)
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioUnavailable from exc


def _volume_percent(item):
    try:
        channel = next(iter(item["volume"].values()))
        return min(int(channel["value_percent"].rstrip("%")), 100)
    except (KeyError, StopIteration, ValueError, TypeError) as exc:
        raise AudioUnavailable from exc


def normalize_browser_volume():
    """Keep Firefox stream gain neutral; the selected sink is the user's volume control."""
    for item in _browser_inputs():
        try:
            channel = next(iter(item["volume"].values()))
            level = int(channel["value_percent"].rstrip("%"))
            index = str(int(item["index"]))
        except (KeyError, StopIteration, ValueError, TypeError) as exc:
            raise AudioUnavailable from exc
        if level != 100:
            _pactl("set-sink-input-volume", index, "100%")


def get_state():
    sinks = _sinks()
    selected = _pactl("get-default-sink")
    if selected not in sinks:
        raise AudioUnavailable
    sink = sinks[selected]
    try:
        mute = bool(sink["mute"])
    except KeyError as exc:
        raise AudioUnavailable from exc
    browser = _browser_inputs()

    def label(name, item):
        description = item.get("description")
        if description and description != "(null)":
            return description
        if "analog" in name:
            return "Аналоговый выход"
        if "hdmi" in name:
            return "HDMI"
        if name.startswith("bluez_output."):
            return "Bluetooth-колонка"
        return name

    return {
        "outputs": [{"id": name, "name": label(name, item)} for name, item in sinks.items()],
        "selected": selected,
        "volume": _volume_percent(sink),
        "muted": mute,
        "browser_volume": _volume_percent(browser[0]) if browser else None,
    }


def _remember_output(name):
    filename = os.environ.get("AD_LINUX_TV_AUDIO_FILE")
    if not filename:
        raise AudioUnavailable
    target = Path(filename)
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(name + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except OSError as exc:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        raise AudioUnavailable from exc


def _sink_input_ids():
    try:
        inputs = json.loads(_pactl("-f", "json", "list", "sink-inputs"))
        return [str(int(item["index"])) for item in inputs]
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioUnavailable from exc


def _select_output(name):
    previous = _pactl("get-default-sink")
    inputs = _sink_input_ids()
    _pactl("set-default-sink", name)
    moved = []
    try:
        for input_id in inputs:
            try:
                _pactl("move-sink-input", input_id, name)
            except AudioUnavailable:
                # A stream can finish between the snapshot and the move.
                if input_id in _sink_input_ids():
                    raise
            else:
                moved.append(input_id)
        _remember_output(name)
    except AudioUnavailable:
        for input_id in moved:
            try:
                _pactl("move-sink-input", input_id, previous)
            except AudioUnavailable:
                pass
        try:
            _pactl("set-default-sink", previous)
        except AudioUnavailable:
            pass
        raise


def apply(action):
    if not isinstance(action, dict) or len(action) != 1:
        raise ValueError("invalid audio action")
    key, value = next(iter(action.items()))
    if key == "output":
        if not isinstance(value, str) or value not in _sinks():
            raise ValueError("unknown output")
        _select_output(value)
    elif key == "volume":
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("invalid volume")
        _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{value}%")
        _remember_output(_pactl("get-default-sink"))
    elif key == "browser_volume":
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("invalid browser volume")
        inputs = _browser_inputs()
        if not inputs:
            raise AudioUnavailable
        for item in inputs:
            _pactl("set-sink-input-volume", str(int(item["index"])), f"{value}%")
    elif key == "test":
        if value is not True:
            raise ValueError("invalid audio test")
        state = get_state()
        if state["muted"] or state["volume"] == 0:
            raise AudioUnavailable
        try:
            subprocess.run(
                [
                    "/usr/bin/paplay",
                    "--device=@DEFAULT_SINK@",
                    str(Path(__file__).parent / "static/audio-check.wav"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise AudioUnavailable from exc
    elif key == "muted":
        if type(value) is not bool:
            raise ValueError("invalid mute")
        _pactl("set-sink-mute", "@DEFAULT_SINK@", "1" if value else "0")
    else:
        raise ValueError("unknown audio action")
    return get_state()
