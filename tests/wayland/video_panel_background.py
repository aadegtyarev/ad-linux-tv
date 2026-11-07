#!/usr/bin/env python3
"""Synthetic fullscreen window; no video or private content is used."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

window = Gtk.Window(title="synthetic-fullscreen-player")
window.set_default_size(1280, 720)
window.fullscreen()
window.add_events(1 << 8)
window.connect("button-press-event", lambda *_: print("fixture_background_clicked", flush=True))
window.connect("focus-in-event", lambda *_: print("fixture_background_focus_in", flush=True))
window.connect("focus-out-event", lambda *_: print("fixture_background_focus_out", flush=True))
entry = Gtk.Entry()
entry.connect("button-press-event", lambda *_: print("fixture_background_clicked", flush=True))
entry.connect(
    "key-press-event",
    lambda _w, event: print("fixture_background_key", Gdk.keyval_name(event.keyval), flush=True),
)
window.add(entry)
window.connect("destroy", Gtk.main_quit)
window.show_all()
entry.grab_focus()


def report_fullscreen():
    active = bool(window.get_window().get_state() & Gdk.WindowState.FULLSCREEN)
    print("fixture_background_fullscreen", active, flush=True)
    return False


GLib.timeout_add(300, report_fullscreen)
print("fixture_background_ready", flush=True)
Gtk.main()
