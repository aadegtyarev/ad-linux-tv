#!/usr/bin/python3
"""Small touch dock for the dedicated Wayland TV session."""

# GI versions must be selected before importing their modules.
# ruff: noqa: E402, I001

import json
import subprocess
from glob import glob
from urllib import request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell


STYLE = b"""
window { background: transparent; }
.touch-panel { background: rgba(13, 27, 48, 0.90); border-radius: 10px; padding: 3px; }
.touch-button { background-image: none; background-color: transparent; color: white;
  border: 0; box-shadow: none; border-radius: 8px; font: 26px sans-serif;
  min-width: 50px; min-height: 53px; padding: 0; }
.touch-button:hover, .touch-button:active { background-color: rgba(92, 164, 255, 0.45); }
.volume-row { padding: 5px 5px 2px; }
.volume-name, .volume-label { color: white; font: 13px sans-serif; }
.volume-name { min-width: 58px; }
.volume-label { min-width: 54px; }
"""

AUDIO_URL = "http://127.0.0.1:8765/api/audio"


def audio_request(action=None):
    headers = {"Origin": "http://127.0.0.1:8765"}
    payload = None
    if action is not None:
        payload = json.dumps(action).encode()
        headers["Content-Type"] = "application/json"
    response = request.Request(AUDIO_URL, data=payload, headers=headers)
    with request.urlopen(response, timeout=1) as reply:
        return json.load(reply)


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
    panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    panel.get_style_context().add_class("touch-panel")
    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    buttons.set_halign(Gtk.Align.END)
    panel.pack_start(buttons, False, False, 0)
    pinned = False
    volume_timer = None
    volume_commits = {"volume": None, "browser_volume": None}
    loading_volume = False

    volume_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    volume_panel.set_no_show_all(True)
    scales = {}
    labels = {}
    for key, name in (("volume", "Выход"), ("browser_volume", "Firefox")):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.get_style_context().add_class("volume-row")
        title = Gtk.Label(label=name)
        title.get_style_context().add_class("volume-name")
        row.pack_start(title, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        scale.set_draw_value(False)
        scale.set_size_request(155, -1)
        row.pack_start(scale, True, True, 0)
        value = Gtk.Label(label="100%")
        value.get_style_context().add_class("volume-label")
        row.pack_start(value, False, False, 0)
        scales[key] = scale
        labels[key] = value
        volume_panel.pack_start(row, False, False, 0)
    panel.pack_start(volume_panel, False, False, 0)

    def close_volume():
        nonlocal volume_timer
        volume_panel.hide()
        volume_panel.set_no_show_all(True)
        if volume_timer is not None:
            GLib.source_remove(volume_timer)
        volume_timer = None
        return False

    def delay_volume_close():
        nonlocal volume_timer
        if volume_timer is not None:
            GLib.source_remove(volume_timer)

        def timeout_close():
            nonlocal volume_timer
            volume_timer = None
            return close_volume()

        volume_timer = GLib.timeout_add_seconds(15, timeout_close)

    def commit_volume(key):
        volume_commits[key] = None
        try:
            audio_request({key: round(scales[key].get_value())})
        except (OSError, ValueError):
            labels[key].set_text("Ошибка")
        return False

    def volume_changed(scale, key):
        if loading_volume:
            return
        labels[key].set_text(f"{round(scale.get_value())}%")
        delay_volume_close()
        if volume_commits[key] is not None:
            GLib.source_remove(volume_commits[key])
        volume_commits[key] = GLib.timeout_add(250, commit_volume, key)

    for key, scale in scales.items():
        scale.connect("value-changed", volume_changed, key)

    def enable_browser_when_playing():
        nonlocal loading_volume
        browser = scales["browser_volume"]
        if volume_panel.get_visible() and not browser.get_sensitive():
            try:
                level = audio_request()["browser_volume"]
                if level is not None:
                    loading_volume = True
                    browser.set_value(level)
                    browser.set_sensitive(True)
                    labels["browser_volume"].set_text(f"{level}%")
            except (OSError, ValueError, KeyError):
                pass
            finally:
                loading_volume = False
        return True

    def on_volume(_button):
        nonlocal loading_volume
        if volume_panel.get_visible():
            close_volume()
            return
        try:
            state = audio_request()
            loading_volume = True
            for key, scale in scales.items():
                level = state[key]
                scale.set_sensitive(level is not None)
                if level is None:
                    labels[key].set_text("Нет звука")
                    scale.set_tooltip_text("Начните воспроизведение в Firefox")
                else:
                    scale.set_value(level)
                    labels[key].set_text(f"{level}%")
        except (OSError, ValueError, KeyError):
            for scale in scales.values():
                scale.set_sensitive(False)
            for label in labels.values():
                label.set_text("Ошибка")
        finally:
            loading_volume = False
        volume_panel.set_no_show_all(False)
        volume_panel.show_all()
        delay_volume_close()

    def on_home(_button):
        nonlocal pinned
        pinned = False
        close_volume()
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

    for label, tooltip, callback in (
        ("⌂", "К плиткам", on_home),
        ("⌨", "Клавиатура", on_keyboard),
        ("🔊", "Громкость", on_volume),
    ):
        button = Gtk.Button.new_with_label(label)
        button.set_tooltip_text(tooltip)
        button.get_style_context().add_class("touch-button")
        button.connect("clicked", callback)
        buttons.pack_start(button, True, True, 0)
    window.add(panel)
    window.connect("destroy", Gtk.main_quit)
    visible = False

    def update_visibility():
        nonlocal visible, pinned
        should_show = touch_available() and not fullscreen_active()
        if not should_show and pinned:
            pinned = False
            set_keyboard_visible(False)
        if not should_show and volume_panel.get_visible():
            close_volume()
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
    GLib.timeout_add_seconds(1, enable_browser_when_playing)
    GLib.timeout_add_seconds(2, update_visibility)
    Gtk.main()


if __name__ == "__main__":
    main()
