"""The warning stays dismissed only for the current timer generation."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "timer_notice", Path(__file__).resolve().parents[1] / "ops/kiosk/timer_notice.py"
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
        "expanded": False,
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


def test_compact_panel_hover_click_and_edit_before_warning():
    notice = module.TimerNotice()
    assert not notice.update(state(1, 7200))["expanded"]
    assert notice.hover(True)["expanded"]
    assert not notice.hover(False)["expanded"]
    assert notice.toggle()["expanded"]
    assert notice.hover(False)["expanded"]  # Click-open stays open when pointer leaves.
    assert notice.edit()["editing"]
    assert notice.update(state(1, 7199))["editing"]  # Polling must not close the picker.
    assert not notice.dismiss()["expanded"]
    assert not notice.update(state(2, 1800))["editing"]
    assert notice.update(state(2, 120))["expanded"]  # Same panel, automatic warning.
    assert not notice.dismiss()["expanded"]
    assert notice.hover(True)["expanded"]  # Dismissed warning still permits editing.
    assert notice.edit()["editing"]
    assert not notice.update(None)["expanded"]


def test_overlay_single_panel_position_opacity_and_readability():
    source = (Path(__file__).resolve().parents[1] / "ops/kiosk/timer-overlay.py").read_text()
    assert "GtkLayerShell.Edge.TOP, True" in source
    assert "GtkLayerShell.Edge.LEFT, True" in source
    assert "GtkLayerShell.Edge.RIGHT" not in source
    assert "GtkLayerShell.Edge.BOTTOM" not in source
    assert "rgba(13, 27, 48, 0.58)" in source
    assert "bold 26px" in source and "font-size: 30px" in source
    assert "KeyboardMode.NONE" in source
    assert 'self.actions.set_visible(state["expanded"])' in source
