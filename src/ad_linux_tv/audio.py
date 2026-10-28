"""Audio controls for the dedicated TV user's PipeWire/PulseAudio session."""

import json
import re
import subprocess
import sys
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


OUTPUT_ID = re.compile(r"[A-Za-z0-9_.:@-]{1,256}")


def output_id(name):
    """PipeWire may add a numeric suffix (".2") to a sink name after a restart."""
    return re.sub(r"\.\d+$", "", name)


def _active_port(item):
    active = item.get("active_port")
    return next((port for port in item.get("ports") or [] if port.get("name") == active), None)


def _available(item):
    """Outputs without port information (e.g. Bluetooth) count as available."""
    port = _active_port(item)
    return port is None or port.get("availability") != "not available"


def _find_output(sinks, wanted):
    matches = [name for name in sinks if output_id(name) == wanted]
    return next(
        (name for name in matches if _available(sinks[name])), matches[0] if matches else None
    )


def choose_output(sinks, saved=None):
    """Startup choice: the saved output if connected, otherwise the first connected HDMI."""
    if saved:
        name = _find_output(sinks, saved)
        if name and _available(sinks[name]):
            return name
    for name, item in sinks.items():
        port = _active_port(item) or {}
        if _available(item) and ("hdmi" in name.lower() or port.get("type") == "HDMI"):
            return name
    return None


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
        return any(
            not _is_firefox(item)
            # Speech Dispatcher's dummy backend leaves a persistent silent stream.
            and item.get("properties", {}).get("application.process.binary") != "sd_dummy"
            for item in inputs
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioUnavailable from exc


def _volume_percent(item):
    try:
        channel = next(iter(item["volume"].values()))
        return min(int(channel["value_percent"].rstrip("%")), 100)
    except (KeyError, StopIteration, ValueError, TypeError) as exc:
        raise AudioUnavailable from exc


def normalize_browser_volume(target=100):
    """Apply the saved Firefox stream level to current and newly created streams."""
    for item in _browser_inputs():
        try:
            channel = next(iter(item["volume"].values()))
            level = int(channel["value_percent"].rstrip("%"))
            index = str(int(item["index"]))
        except (KeyError, StopIteration, ValueError, TypeError) as exc:
            raise AudioUnavailable from exc
        if level != target:
            _pactl("set-sink-input-volume", index, f"{target}%")


def normalize_browser_mute(target=False):
    """Apply the saved Firefox mute setting to current and newly created streams."""
    for item in _browser_inputs():
        if bool(item.get("mute", False)) != target:
            _pactl("set-sink-input-mute", str(int(item["index"])), "1" if target else "0")


def browser_audio_active():
    """A Firefox sink input may stay present after its media has been paused."""
    return any(
        not item.get("corked", False) and not item.get("mute", False) for item in _browser_inputs()
    )


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
        if name.startswith("bluez_output.") and description:
            return description  # The speaker's own name, e.g. "JBL Flip".
        port = _active_port(item) or {}
        properties = item.get("properties") or {}
        # pactl prints missing values as the literal string "(null)".
        for short in (
            port.get("description"),
            properties.get("device.profile.description"),
            properties.get("node.nick"),
        ):
            if short and short != "(null)":
                return short
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
        # Only outputs with something connected, plus the current one so the choice stays truthful.
        "outputs": [
            {"id": output_id(name), "name": label(name, item)}
            for name, item in sinks.items()
            if _available(item) or name == selected
        ],
        "selected": output_id(selected),
        "volume": _volume_percent(sink),
        "muted": mute,
        "browser_volume": _volume_percent(browser[0]) if browser else None,
        "browser_muted": (
            any(bool(item.get("mute", False)) for item in browser) if browser else None
        ),
    }


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
        sinks = _sinks()
        name = _find_output(sinks, value) if isinstance(value, str) else None
        if name is None:
            raise ValueError("unknown output")
        _select_output(name)
    elif key == "volume":
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("invalid volume")
        _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{value}%")
    elif key == "browser_volume":
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("invalid browser volume")
        inputs = _browser_inputs()
        if not inputs:
            raise AudioUnavailable
        for item in inputs:
            _pactl("set-sink-input-volume", str(int(item["index"])), f"{value}%")
    elif key == "browser_muted":
        if type(value) is not bool:
            raise ValueError("invalid Firefox stream mute")
        inputs = _browser_inputs()
        if not inputs:
            raise AudioUnavailable
        for item in inputs:
            _pactl("set-sink-input-mute", str(int(item["index"])), "1" if value else "0")
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


def select_saved_output(saved):
    """Apply the startup choice. Returns False while the audio server has no outputs yet."""
    sinks = _sinks()
    if not sinks:
        return False
    name = choose_output(sinks, saved)
    if name and _pactl("get-default-sink") != name:
        _pactl("set-default-sink", name)
    if name and not saved:
        # First start: an untouched HDMI output begins audible at full level.
        _pactl("set-sink-volume", name, "100%")
        _pactl("set-sink-mute", name, "0")
    return True


def main():
    """`python -m ad_linux_tv.audio select CONFIG [LEGACY_FILE]` used by the TV session."""
    from .config import load_config

    if len(sys.argv) not in (3, 4) or sys.argv[1] != "select":
        print("usage: python -m ad_linux_tv.audio select CONFIG [LEGACY_FILE]", file=sys.stderr)
        raise SystemExit(2)
    saved = None
    try:
        saved = load_config(sys.argv[2]).get("audio", {}).get("output")
    except (OSError, ValueError):
        pass
    if saved is None and len(sys.argv) == 4:
        try:
            saved = output_id(Path(sys.argv[3]).read_text().strip()) or None
        except OSError:
            pass
    try:
        ready = select_saved_output(saved)
    except AudioUnavailable:
        ready = False
    raise SystemExit(0 if ready else 3)


if __name__ == "__main__":
    main()
