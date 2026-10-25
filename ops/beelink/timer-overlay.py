#!/usr/bin/python3
"""Small TV timer badge and actionable warning above fullscreen video."""

# GI versions must be selected before importing their modules.
# ruff: noqa: E402, I001

import json
from urllib import request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from timer_notice import TimerNotice


TIMER_URL = "http://127.0.0.1:8765/api/display-timer"
STYLE = b"""
window { background: transparent; }
.timer-notice { background: #0d1b30; border: 1px solid #6084a0;
  border-radius: 12px; padding: 8px; }
.timer-count { color: #e9f6ff; font: bold 15px sans-serif; padding: 2px 5px; }
.timer-warning { color: #ffdfa2; font: bold 15px sans-serif; padding: 5px; }
.timer-action { background-image: none; background-color: #294865; color: white;
  border: 1px solid #7697b1; border-radius: 8px; font: 13px sans-serif;
  min-width: 78px; min-height: 42px; padding: 4px 8px; }
.timer-action:active { background-color: #176991; }
"""


def timer_request(minutes=None):
    headers = {"Origin": "http://127.0.0.1:8765"}
    payload = None
    if minutes is not None:
        payload = json.dumps({"minutes": minutes}).encode()
        headers["Content-Type"] = "application/json"
    message = request.Request(TIMER_URL, data=payload, headers=headers)
    with request.urlopen(message, timeout=1) as response:
        return json.load(response)


class TimerOverlay:
    def __init__(self):
        self.notice = TimerNotice()
        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_accept_focus(False)
        screen = Gdk.Screen.get_default()
        if screen and screen.get_rgba_visual():
            self.window.set_visual(screen.get_rgba_visual())
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, "ad-linux-tv-timer")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.BOTTOM, 18)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.RIGHT, 18)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel.get_style_context().add_class("timer-notice")
        self.count = Gtk.Label()
        self.count.set_xalign(0)
        self.count.get_style_context().add_class("timer-count")
        panel.pack_start(self.count, False, False, 0)
        self.warning = Gtk.Label(label="Экран скоро погаснет")
        self.warning.set_xalign(0)
        self.warning.get_style_context().add_class("timer-warning")
        panel.pack_start(self.warning, False, False, 0)

        self.actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        for label, callback in (
            ("ОК", self.dismiss),
            ("Изменить", self.edit),
            ("Отменить", lambda: self.set_timer(0)),
        ):
            self.actions.pack_start(self.button(label, callback), True, True, 0)
        panel.pack_start(self.actions, False, False, 0)

        self.presets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for choices in (
            ((15, "15 мин"), (30, "30 мин"), (60, "1 час")),
            ((90, "1,5 часа"), (120, "2 часа")),
        ):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            for minutes, label in choices:
                row.pack_start(
                    self.button(label, lambda value=minutes: self.set_timer(value)),
                    True,
                    True,
                    0,
                )
            self.presets.pack_start(row, False, False, 0)
        panel.pack_start(self.presets, False, False, 0)
        self.window.add(panel)
        self.window.connect("destroy", Gtk.main_quit)

    @staticmethod
    def button(label, action):
        button = Gtk.Button.new_with_label(label)
        button.get_style_context().add_class("timer-action")
        button.connect("clicked", lambda _button: action())
        return button

    def render(self, state):
        if not state["visible"]:
            self.window.hide()
            return
        self.count.set_text(f"До отключения: {state['remaining']}")
        if not self.window.get_visible():
            self.window.show_all()
        self.warning.set_visible(state["warning"])
        self.actions.set_visible(state["warning"])
        self.presets.set_visible(state["editing"])

    def dismiss(self):
        self.render(self.notice.dismiss())

    def edit(self):
        self.render(self.notice.edit())

    def set_timer(self, minutes):
        try:
            self.render(self.notice.update(timer_request(minutes)))
        except (OSError, ValueError):
            self.render(self.notice.update(None))

    def poll(self):
        try:
            state = self.notice.update(timer_request())
        except (OSError, ValueError):
            state = self.notice.update(None)
        self.render(state)
        return True


def main():
    overlay = TimerOverlay()
    overlay.poll()
    GLib.timeout_add_seconds(1, overlay.poll)
    Gtk.main()


if __name__ == "__main__":
    main()
