"""The warning stays dismissed only for the current timer generation."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "timer_notice", Path(__file__).resolve().parents[1] / "ops/beelink/timer_notice.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def state(generation, remaining):
    return {"generation": generation, "remaining_seconds": remaining, "phase": "countdown"}


def test_warning_threshold_dismissal_and_new_timer():
    notice = module.TimerNotice()
    assert notice.update(state(1, 900)) == {
        "visible": True,
        "warning": False,
        "editing": False,
        "remaining": "15 мин",
    }
    assert notice.update(state(1, 120))["warning"] is True
    assert notice.edit()["editing"] is True
    assert notice.dismiss()["warning"] is False
    assert notice.update(state(1, 60))["warning"] is False
    assert notice.update(state(2, 120))["warning"] is True
    assert notice.update(None)["visible"] is False
    stopped = {"generation": 3, "remaining_seconds": 0, "phase": "idle"}
    assert notice.update(stopped)["visible"] is False
