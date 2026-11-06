#!/usr/bin/python3
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

w = Gtk.Window(title="synthetic-keybind-check")
w.set_default_size(900, 600)
w.fullscreen()
e = Gtk.Entry()
w.add(e)


def key(_widget, event, kind):
    name = Gdk.keyval_name(event.keyval)
    if name in (
        "Launch1",
        "Launch2",
        "Launch3",
        "Launch4",
        "Launch5",
        "Launch6",
        "Launch7",
        "Return",
        "a",
    ):
        print(kind, name, flush=True)
    return False


e.connect("key-press-event", key, "press")
e.connect("key-release-event", key, "release")
w.connect("destroy", Gtk.main_quit)
w.show_all()
e.grab_focus()


def report_ready():
    fullscreen = bool(w.get_window().get_state() & Gdk.WindowState.FULLSCREEN)
    print("window_fullscreen", fullscreen, flush=True)
    return False


GLib.timeout_add(300, report_ready)
Gtk.main()
