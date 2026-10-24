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


def get_state():
    sinks = _sinks()
    selected = _pactl("get-default-sink")
    if selected not in sinks:
        raise AudioUnavailable
    sink = sinks[selected]
    try:
        channel = next(iter(sink["volume"].values()))
        volume = int(channel["value_percent"].rstrip("%"))
        mute = bool(sink["mute"])
    except (KeyError, StopIteration, ValueError, TypeError) as exc:
        raise AudioUnavailable from exc

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
        "volume": min(volume, 100),
        "muted": mute,
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
    elif key == "muted":
        if type(value) is not bool:
            raise ValueError("invalid mute")
        _pactl("set-sink-mute", "@DEFAULT_SINK@", "1" if value else "0")
    else:
        raise ValueError("unknown audio action")
    return get_state()
