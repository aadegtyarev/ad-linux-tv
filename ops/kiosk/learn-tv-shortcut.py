#!/usr/bin/python3
"""One short-lived, focused chooser; unrelated keys are never returned or logged."""

# GI requires explicit version selection before importing modules.
# ruff: noqa: E402, I001
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, GLib, GLibUnix, Gtk, GtkLayerShell

from tv_shortcut_keys import BY_VALUE
from video_panel_client import bind_parent


class Chooser:
    def __init__(self):
        self.key = None
        self.cancelled = False
        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, "ad-linux-tv-shortcut-learning")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, 80)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"window { background: #102039; } "
            b"label { color: white; font: 19px sans-serif; } "
            b"button { font: 18px sans-serif; min-height: 48px; }"
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(22)
        box.set_size_request(520, -1)
        title = Gtk.Label(label="Нажмите выбранную кнопку пульта")
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)
        hint = Gtk.Label(label="Редкая кнопка; другие клавиши и текст не сохраняются.")
        hint.set_line_wrap(True)
        box.pack_start(hint, False, False, 0)
        cancel = Gtk.Button.new_with_label("Отмена")
        cancel.connect("clicked", self._cancel)
        box.pack_start(cancel, False, False, 0)
        self.window.add(box)
        self.window.connect("key-press-event", self._pressed)
        self.window.connect("destroy", lambda *_: Gtk.main_quit())

    def _cancel(self, *_args):
        self.cancelled = True
        Gtk.main_quit()

    def _pressed(self, _window, event):
        forbidden = (
            Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.MOD1_MASK
            | Gdk.ModifierType.MOD3_MASK
            | Gdk.ModifierType.MOD4_MASK
            | Gdk.ModifierType.MOD5_MASK
            | Gdk.ModifierType.SUPER_MASK
            | Gdk.ModifierType.META_MASK
            | Gdk.ModifierType.HYPER_MASK
        )
        if not event.state & forbidden:
            key = BY_VALUE.get(event.keyval)
            if key is not None:
                self.key = key
                Gtk.main_quit()
        return True

    def run(self):
        self.window.show_all()
        GLib.timeout_add_seconds(15, lambda: (Gtk.main_quit(), False)[1])
        GLibUnix.signal_add(
            GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: (Gtk.main_quit(), False)[1]
        )
        GLibUnix.signal_add(
            GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda *_: (Gtk.main_quit(), False)[1]
        )
        Gtk.main()
        if self.cancelled:
            return 2
        if self.key is None:
            return 1
        print(self.key)
        return 0


def main():
    if not bind_parent():
        return 1
    return Chooser().run()


if __name__ == "__main__":
    sys.exit(main())
