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
.timer-notice { background: rgba(13, 27, 48, 0.58); border: 1px solid rgba(128, 171, 200, 0.48);
  border-radius: 14px; padding: 10px; }
.timer-header { background-image: none; background-color: transparent;
  color: #e9f6ff; border: 0; box-shadow: none; padding: 0 6px; min-height: 46px; }
.timer-clock { color: #e9f6ff; font: 24px sans-serif; }
.timer-count { color: #e9f6ff; font: bold 26px sans-serif; padding: 2px 5px; }
.timer-notice.expanded { background: rgba(13, 27, 48, 0.84); }
.timer-notice.expanded .timer-header { min-height: 58px; }
.timer-notice.expanded .timer-count { font-size: 30px; }
.timer-warning { color: #ffdfa2; font: bold 20px sans-serif; padding: 5px; }
.timer-action { background-image: none; background-color: #294865; color: white;
  border: 1px solid #7697b1; border-radius: 8px; font: 17px sans-serif;
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
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, 96)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.LEFT, 18)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.panel = panel
        self.expanded = None
        panel.get_style_context().add_class("timer-notice")
        header = self.button("", lambda: self.render(self.notice.toggle()))
        header.get_style_context().remove_class("timer-action")
        header.get_style_context().add_class("timer-header")
        header.set_tooltip_text("Таймер экрана: изменить или отменить")
        header.get_accessible().set_name("Таймер отключения экрана")
        caption = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        caption.set_halign(Gtk.Align.START)
        clock = Gtk.Label(label="◷")
        clock.get_style_context().add_class("timer-clock")
        caption.pack_start(clock, False, False, 0)
        self.count = Gtk.Label()
        self.count.get_style_context().add_class("timer-count")
        caption.pack_start(self.count, False, False, 0)
        header.remove(header.get_child())
        header.add(caption)
        panel.pack_start(header, False, False, 0)
        self.warning = Gtk.Label(label="Экран скоро погаснет")
        self.warning.set_xalign(0)
        self.warning.get_style_context().add_class("timer-warning")
        panel.pack_start(self.warning, False, False, 0)

        self.actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        for label, callback in (
            ("Свернуть", self.dismiss),
            ("Изменить", self.edit),
            ("Отменить", lambda: self.set_timer(0)),
        ):
            button = self.button(label, callback)
            if label == "Свернуть":
                self.dismiss_button = button
            self.actions.pack_start(button, True, True, 0)
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
        events = Gtk.EventBox()
        events.set_visible_window(False)
        events.add(panel)
        events.connect("enter-notify-event", lambda _widget, event: self.hover(event, True))
        events.connect("leave-notify-event", lambda _widget, event: self.hover(event, False))
        self.window.add(events)
        self.window.connect("destroy", Gtk.main_quit)

    @staticmethod
    def button(label, action):
        button = Gtk.Button.new_with_label(label)
        button.get_style_context().add_class("timer-action")
        button.set_focus_on_click(False)
        button.connect("clicked", lambda _button: action())
        return button

    def render(self, state):
        if not state["visible"]:
            self.window.hide()
            return
        if self.count.get_text() != state["remaining"]:
            self.count.set_text(state["remaining"])
        if not self.window.get_visible():
            self.window.show_all()
        self.warning.set_visible(state["warning"])
        self.actions.set_visible(state["expanded"])
        self.dismiss_button.set_visible(state["warning"])
        self.presets.set_visible(state["editing"])
        if self.expanded != state["expanded"]:
            self.expanded = state["expanded"]
            context = self.panel.get_style_context()
            if self.expanded:
                context.add_class("expanded")
            else:
                context.remove_class("expanded")
            self.window.resize(1, 1)

    def hover(self, event, active):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.render(self.notice.hover(active))
        return False

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
