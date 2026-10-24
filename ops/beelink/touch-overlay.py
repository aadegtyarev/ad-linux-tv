#!/usr/bin/python3
"""Small touch dock for the dedicated Wayland TV session."""

# GI versions must be selected before importing their modules.
# ruff: noqa: E402, I001

import subprocess
from glob import glob

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell


STYLE = b"""
window { background: transparent; }
.touch-panel { background: rgba(13, 27, 48, 0.90); border-radius: 12px; padding: 4px; }
.touch-button { background-image: none; background-color: transparent; color: white;
  border: 0; box-shadow: none; border-radius: 9px; font: 15px sans-serif;
  min-width: 78px; min-height: 46px; padding: 2px; }
.touch-button:hover, .touch-button:active { background-color: rgba(92, 164, 255, 0.45); }
"""


def home():
    subprocess.Popen(
        ["/usr/local/libexec/ad-linux-tv/touch-controls.sh", "home"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def keyboard_visible():
    try:
        result = subprocess.run(
            [
                "/usr/bin/busctl",
                "--user",
                "get-property",
                "sm.puri.OSK0",
                "/sm/puri/OSK0",
                "sm.puri.OSK0",
                "Visible",
            ],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        return result.stdout.strip() == "b true" if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def set_keyboard_visible(visible):
    try:
        result = subprocess.run(
            [
                "/usr/bin/busctl",
                "--user",
                "call",
                "sm.puri.OSK0",
                "/sm/puri/OSK0",
                "sm.puri.OSK0",
                "SetVisible",
                "b",
                "true" if visible else "false",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def touch_available():
    for event in glob("/dev/input/event*"):
        try:
            result = subprocess.run(
                ["/usr/bin/udevadm", "info", "--query=property", f"--name={event}"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if "ID_INPUT_TOUCHSCREEN=1" in result.stdout.splitlines():
            return True
    return False


def fullscreen_active():
    try:
        result = subprocess.run(
            ["/usr/bin/wlrctl", "toplevel", "find", "state:fullscreen"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    window = Gtk.Window()
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_accept_focus(False)
    screen = Gdk.Screen.get_default()
    if screen and screen.get_rgba_visual():
        window.set_visual(screen.get_rgba_visual())
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "ad-linux-tv-touch")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, 2)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.RIGHT, 12)
    GtkLayerShell.set_exclusive_zone(window, 0)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)

    provider = Gtk.CssProvider()
    provider.load_from_data(STYLE)
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
    box.get_style_context().add_class("touch-panel")
    pinned = False

    def on_home(_button):
        nonlocal pinned
        pinned = False
        set_keyboard_visible(False)
        home()

    def on_keyboard(_button):
        nonlocal pinned
        visible = keyboard_visible()
        if visible is None:
            return
        pinned = not visible
        if not set_keyboard_visible(pinned):
            pinned = False

    for label, callback in (("⌂ Плитки", on_home), ("⌨ Клав.", on_keyboard)):
        button = Gtk.Button.new_with_label(label)
        button.get_style_context().add_class("touch-button")
        button.connect("clicked", callback)
        box.pack_start(button, True, True, 0)
    window.add(box)
    window.connect("destroy", Gtk.main_quit)
    visible = False

    def update_visibility():
        nonlocal visible, pinned
        should_show = touch_available() and not fullscreen_active()
        if not should_show and pinned:
            pinned = False
            set_keyboard_visible(False)
        if should_show != visible:
            if should_show:
                window.show_all()
            else:
                window.hide()
            visible = should_show
        return True

    def keep_keyboard_open():
        if pinned and keyboard_visible() is False:
            set_keyboard_visible(True)
        return True

    update_visibility()
    GLib.timeout_add(150, keep_keyboard_open)
    GLib.timeout_add_seconds(2, update_visibility)
    Gtk.main()


if __name__ == "__main__":
    main()
