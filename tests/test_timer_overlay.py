"""Execute the native panel's actual methods with GI and all I/O fenced off."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Widget:
    def __init__(self, label="", **kwargs):
        self.text = label
        self.children = []
        self.classes = set()
        self.signals = {}
        self.visible = False
        self.text_writes = 0
        self.resizes = []
        self.properties = kwargs

    @classmethod
    def new_with_label(cls, label):
        button = cls(label)
        button.add(cls(label))
        return button

    def get_style_context(self):
        return self

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)

    def add(self, child):
        self.children.append(child)

    def pack_start(self, child, *_args):
        self.add(child)

    def remove(self, child):
        self.children.remove(child)

    def get_child(self):
        return self.children[0]

    def connect(self, signal, callback):
        self.signals[signal] = callback

    def click(self):
        self.signals["clicked"](self)

    def get_accessible(self):
        return self

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text
        self.text_writes += 1

    def set_visible(self, value):
        self.visible = value

    def get_visible(self):
        return self.visible

    def show_all(self):
        self.visible = True
        for child in self.children:
            child.show_all()

    def hide(self):
        self.visible = False

    def resize(self, *size):
        self.resizes.append(size)

    def load_from_data(self, data):
        self.css = data

    def __getattr__(self, name):
        # Only inert properties used by the constructor; no image API fallback.
        if name in {
            "set_decorated",
            "set_resizable",
            "set_accept_focus",
            "set_visual",
            "set_tooltip_text",
            "set_name",
            "set_halign",
            "set_xalign",
            "set_visible_window",
            "set_focus_on_click",
        }:
            return lambda value: self.properties.__setitem__(name, value)
        raise AssertionError(f"Unexpected GTK API: {name}")


def forbidden(*_args, **_kwargs):
    raise AssertionError("Image lookup, native loop, scheduling or real I/O is forbidden")


class FakeGtk(ModuleType):
    def __getattr__(self, name):
        raise AssertionError(f"Forbidden/unsupported GTK API: {name}")


@pytest.fixture
def overlay_module(monkeypatch):
    gi = ModuleType("gi")
    gi.require_version = Mock()
    repository = ModuleType("gi.repository")
    gtk = FakeGtk("Gtk")
    for name in ("Window", "Box", "Label", "Button", "EventBox", "CssProvider"):
        setattr(gtk, name, Widget)
    gtk.Orientation = SimpleNamespace(VERTICAL=1, HORIZONTAL=2)
    gtk.Align = SimpleNamespace(START=1)
    gtk.STYLE_PROVIDER_PRIORITY_APPLICATION = 600
    gtk.StyleContext = SimpleNamespace(add_provider_for_screen=Mock())
    gtk.main = gtk.main_quit = forbidden
    layer = SimpleNamespace(
        Layer=SimpleNamespace(OVERLAY=1),
        Edge=SimpleNamespace(TOP=1, LEFT=2),
        KeyboardMode=SimpleNamespace(NONE=0),
    )
    for name in (
        "init_for_window",
        "set_namespace",
        "set_layer",
        "set_anchor",
        "set_margin",
        "set_exclusive_zone",
        "set_keyboard_mode",
    ):
        setattr(layer, name, Mock())
    repository.Gtk = gtk
    repository.Gdk = SimpleNamespace(
        Screen=SimpleNamespace(get_default=lambda: None),
        NotifyType=SimpleNamespace(INFERIOR=1),
    )
    repository.GLib = SimpleNamespace(timeout_add_seconds=forbidden)
    repository.GtkLayerShell = layer
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    spec = importlib.util.spec_from_file_location(
        "timer_notice", ROOT / "ops/beelink/timer_notice.py"
    )
    notice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notice)
    monkeypatch.setitem(sys.modules, "timer_notice", notice)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    spec = importlib.util.spec_from_file_location(
        "timer_overlay_under_test", ROOT / "ops/beelink/timer-overlay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.timer_request = Mock(side_effect=forbidden)
    return module


def update(overlay, seconds, generation=1, phase="countdown"):
    overlay.render(
        overlay.notice.update(
            {
                "generation": generation,
                "remaining_seconds": seconds,
                "phase": phase,
            }
        )
    )


def test_constructor_text_clock_and_focusless_header(overlay_module):
    overlay = overlay_module.TimerOverlay()
    header = overlay.panel.children[0]
    clock, count = header.get_child().children
    assert clock.text == "◷" and clock.classes == {"timer-clock"}
    assert count is overlay.count and count.classes == {"timer-count"}
    assert b".timer-clock" in overlay_module.STYLE
    assert b"font: 24px sans-serif" in overlay_module.STYLE
    assert b"bold 26px" in overlay_module.STYLE
    assert b"font-size: 30px" in overlay_module.STYLE
    assert header.properties["set_name"] == "Таймер отключения экрана"
    assert header.properties["set_focus_on_click"] is False
    assert overlay.window.properties["set_accept_focus"] is False
    assert not overlay.window.visible
    overlay_module.timer_request.assert_not_called()


def test_render_transitions_and_in_place_ticks(overlay_module):
    overlay = overlay_module.TimerOverlay()
    panel, count = overlay.panel, overlay.count
    update(overlay, 900)
    assert overlay.window.visible and count.text == "15 мин"
    assert not overlay.actions.visible and not overlay.warning.visible
    assert not overlay.presets.visible and "expanded" not in panel.classes
    writes, resizes = count.text_writes, len(overlay.window.resizes)
    update(overlay, 899)
    assert count.text_writes == writes and len(overlay.window.resizes) == resizes
    overlay.panel.children[0].click()
    assert overlay.actions.visible and "expanded" in panel.classes
    overlay.actions.children[1].click()
    assert overlay.presets.visible
    update(overlay, 898)
    assert overlay.presets.visible
    update(overlay, 120, generation=2)
    assert overlay.warning.visible and overlay.dismiss_button.visible
    assert count.text == "2:00" and not overlay.presets.visible
    overlay.dismiss_button.click()
    update(overlay, 60, generation=2)
    assert not overlay.warning.visible and not overlay.actions.visible
    update(overlay, 120, generation=3)
    assert overlay.warning.visible
    update(overlay, 0, generation=4, phase="idle")
    assert not overlay.window.visible
    update(overlay, 900, generation=5)
    overlay.render(overlay.notice.update(None))
    assert not overlay.window.visible
    assert overlay.panel is panel and overlay.count is count
    overlay_module.timer_request.assert_not_called()


def test_hover_and_header_callbacks_do_not_mutate_timer(overlay_module):
    overlay = overlay_module.TimerOverlay()
    update(overlay, 900)
    assert overlay.hover(SimpleNamespace(detail=0), True) is False
    assert overlay.actions.visible
    overlay.hover(SimpleNamespace(detail=1), False)
    assert overlay.actions.visible  # Inferior crossing must be ignored.
    overlay.hover(SimpleNamespace(detail=0), False)
    assert not overlay.actions.visible
    header = overlay.panel.children[0]
    header.click()
    header.click()
    assert not overlay.actions.visible
    overlay_module.timer_request.assert_not_called()


@pytest.mark.parametrize("minutes", [15, 30, 60, 90, 120, 0])
def test_explicit_preset_and_cancel_callbacks_only(overlay_module, minutes):
    overlay = overlay_module.TimerOverlay()
    update(overlay, 900)
    overlay_module.timer_request.assert_not_called()
    overlay_module.timer_request.side_effect = None
    overlay_module.timer_request.return_value = {
        "generation": 2,
        "remaining_seconds": minutes * 60,
        "phase": "countdown" if minutes else "idle",
    }
    if minutes:
        buttons = [button for row in overlay.presets.children for button in row.children]
        buttons[[15, 30, 60, 90, 120].index(minutes)].click()
    else:
        overlay.actions.children[2].click()
    overlay_module.timer_request.assert_called_once_with(minutes)
    assert overlay.window.visible is bool(minutes)
