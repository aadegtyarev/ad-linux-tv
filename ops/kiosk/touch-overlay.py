#!/usr/bin/python3
"""Small touch dock for the dedicated Wayland TV session."""

# GI versions must be selected before importing their modules.
# ruff: noqa: E402, I001

import json
import os
import subprocess
import tempfile
from glob import glob
from pathlib import Path
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
  border: 0; box-shadow: none; border-radius: 8px;
  font: 26px "Noto Sans Symbols 2", "Noto Sans Symbols", sans-serif;
  min-width: 50px; min-height: 53px; padding: 0; }
.drag-handle { color: #dcefff; background-color: rgba(105, 153, 188, 0.23);
  border-radius: 8px; min-width: 62px; min-height: 53px; font: 30px sans-serif; }
.touch-button:hover, .touch-button:active, .touch-button.touch-flash {
  background-color: rgba(92, 164, 255, 0.65); }
.volume-row { padding: 5px 5px 2px; }
.volume-name, .volume-label { color: white; font: 13px sans-serif; }
.volume-name { min-width: 58px; }
.volume-label { min-width: 54px; }
.timer-panel { padding: 7px; }
.timer-status { color: #e7f6ff; font: 15px sans-serif; padding: 5px; }
.timer-button { background-image: none; background-color: rgba(43, 64, 89, 0.95);
  color: white; border: 1px solid #6883a1; border-radius: 8px;
  min-width: 90px; min-height: 50px; font: 15px sans-serif; }
.timer-button:active { background-color: #176991; }
"""

AUDIO_URL = "http://127.0.0.1:8765/api/audio"
TIMER_URL = "http://127.0.0.1:8765/api/display-timer"
COMMAND_URL = "http://127.0.0.1:8765/api/command"
POSITION_FILE = Path.home() / ".config/ad-linux-tv/touch-panel-position.json"


def clamp_position(top, right, panel_width, panel_height, screen_width, screen_height):
    return {
        "top": max(0, min(top, max(0, screen_height - panel_height - 8))),
        "right": max(0, min(right, max(0, screen_width - panel_width - 8))),
    }


def load_position():
    try:
        value = json.loads(POSITION_FILE.read_text())
        if set(value) != {"top", "right"}:
            raise ValueError("invalid position")
        if any(type(value[key]) is not int or not 0 <= value[key] <= 10000 for key in value):
            raise ValueError("invalid position")
        return value
    except (OSError, TypeError, ValueError):
        return {"top": 2, "right": 12}


def save_position(value):
    POSITION_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=POSITION_FILE.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, POSITION_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def audio_request(action=None):
    headers = {"Origin": "http://127.0.0.1:8765"}
    payload = None
    if action is not None:
        payload = json.dumps(action).encode()
        headers["Content-Type"] = "application/json"
    response = request.Request(AUDIO_URL, data=payload, headers=headers)
    with request.urlopen(response, timeout=1) as reply:
        return json.load(reply)


def timer_request(minutes=None):
    headers = {"Origin": "http://127.0.0.1:8765"}
    payload = None
    if minutes is not None:
        payload = json.dumps({"minutes": minutes}).encode()
        headers["Content-Type"] = "application/json"
    response = request.Request(TIMER_URL, data=payload, headers=headers)
    with request.urlopen(response, timeout=1) as reply:
        return json.load(reply)


def toggle_fullscreen():
    """The bridge fullscreens the page's video or leaves fullscreen; failures stay silent here."""
    payload = json.dumps({"command": "fullscreen"}).encode()
    headers = {"Origin": "http://127.0.0.1:8765", "Content-Type": "application/json"}
    try:
        with request.urlopen(
            request.Request(COMMAND_URL, data=payload, headers=headers), timeout=1
        ):
            pass
    except OSError:
        pass


def history(direction):
    subprocess.Popen(
        ["/usr/local/libexec/ad-linux-tv/touch-controls.sh", direction],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
    position = load_position()
    primary = Gdk.Display.get_default().get_primary_monitor()
    if primary is not None:
        geometry = primary.get_geometry()
        position = clamp_position(
            position["top"], position["right"], 340, 180, geometry.width, geometry.height
        )
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, position["top"])
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.RIGHT, position["right"])
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
    handle = Gtk.EventBox()
    handle.get_style_context().add_class("drag-handle")
    handle.set_tooltip_text("Перетащить панель")
    handle.add(Gtk.Label(label="⋮⋮"))
    buttons.pack_start(handle, False, False, 0)

    def apply_position(top, right):
        nonlocal position
        monitor = (
            window.get_display().get_monitor_at_window(window.get_window())
            if window.get_window()
            else window.get_display().get_primary_monitor()
        )
        if monitor is not None:
            geometry = monitor.get_geometry()
            position = clamp_position(
                top,
                right,
                panel.get_allocated_width(),
                panel.get_allocated_height(),
                geometry.width,
                geometry.height,
            )
        else:
            position = {"top": max(0, top), "right": max(0, right)}
        if GtkLayerShell.get_margin(window, GtkLayerShell.Edge.TOP) != position["top"]:
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, position["top"])
        if GtkLayerShell.get_margin(window, GtkLayerShell.Edge.RIGHT) != position["right"]:
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.RIGHT, position["right"])
        return False

    drag_origin = {"top": position["top"], "right": position["right"]}
    dragging = False
    drag = Gtk.GestureDrag.new(handle)

    def drag_begin(_gesture, _x, _y):
        nonlocal dragging
        dragging = True
        drag_origin.update(position)

    def drag_update(_gesture, offset_x, offset_y):
        apply_position(
            drag_origin["top"] + round(offset_y),
            drag_origin["right"] - round(offset_x),
        )

    def drag_end(_gesture, _offset_x, _offset_y):
        nonlocal dragging
        dragging = False
        apply_position(position["top"], position["right"])
        try:
            save_position(position)
        except OSError:
            pass

    drag.connect("drag-begin", drag_begin)
    drag.connect("drag-update", drag_update)
    drag.connect("drag-end", drag_end)

    def on_panel_allocate(_widget, _allocation):
        if not dragging:
            GLib.idle_add(apply_position, position["top"], position["right"])

    panel.connect("size-allocate", on_panel_allocate)
    pinned = False
    volume_timer = None
    volume_commits = {"volume": None}
    loading_volume = False

    volume_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    volume_panel.set_no_show_all(True)
    scales = {}
    labels = {}
    for key, name in (("volume", "Громкость"),):
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

    timer_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    timer_panel.get_style_context().add_class("timer-panel")
    timer_panel.set_no_show_all(True)
    timer_status = Gtk.Label(label="Таймер выключен")
    timer_status.set_xalign(0)
    timer_status.get_style_context().add_class("timer-status")
    timer_panel.pack_start(timer_status, False, False, 0)
    for row_values in (
        ((15, "15 мин"), (30, "30 мин"), (60, "1 час")),
        ((90, "1,5 часа"), (120, "2 часа"), (0, "Отменить")),
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        for minutes, title in row_values:
            button = Gtk.Button.new_with_label(title)
            button.get_style_context().add_class("timer-button")

            def select_timer(_button, selected=minutes):
                try:
                    state = timer_request(selected)
                    show_timer_status(state)
                except (OSError, ValueError):
                    timer_status.set_text("Таймер недоступен")

            button.connect("clicked", select_timer)
            row.pack_start(button, True, True, 0)
        timer_panel.pack_start(row, False, False, 0)
    panel.pack_start(timer_panel, False, False, 0)

    def show_timer_status(state):
        if state.get("error"):
            timer_status.set_text("Ошибка таймера: экран остался включённым")
        elif state.get("asleep"):
            timer_status.set_text("Экран погашен")
        elif state.get("remaining_seconds", 0) > 0:
            minutes_left = (state["remaining_seconds"] + 59) // 60
            timer_status.set_text(f"До отключения: {minutes_left} мин")
        else:
            timer_status.set_text("Таймер выключен")

    def close_timer():
        timer_panel.hide()
        timer_panel.set_no_show_all(True)

    def on_timer(_button):
        if timer_panel.get_visible():
            close_timer()
            return
        close_volume()
        try:
            show_timer_status(timer_request())
        except (OSError, ValueError):
            timer_status.set_text("Таймер недоступен")
        timer_panel.set_no_show_all(False)
        timer_panel.show_all()
        GLib.idle_add(apply_position, position["top"], position["right"])

    def refresh_timer_status():
        if timer_panel.get_visible():
            try:
                show_timer_status(timer_request())
            except (OSError, ValueError):
                timer_status.set_text("Таймер недоступен")
        return True

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

    def on_volume(_button):
        nonlocal loading_volume
        if volume_panel.get_visible():
            close_volume()
            return
        close_timer()
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
        GLib.idle_add(apply_position, position["top"], position["right"])
        delay_volume_close()

    def on_home(_button):
        nonlocal pinned
        pinned = False
        close_volume()
        close_timer()
        set_keyboard_visible(False)
        home()

    def on_back(_button):
        close_volume()
        close_timer()
        history("back")

    def on_forward(_button):
        close_volume()
        close_timer()
        history("forward")

    def on_keyboard(_button):
        nonlocal pinned
        visible = keyboard_visible()
        if visible is None:
            return
        pinned = not visible
        if not set_keyboard_visible(pinned):
            pinned = False

    def on_touch_click(button, callback):
        context = button.get_style_context()
        context.add_class("touch-flash")

        def clear_flash():
            context.remove_class("touch-flash")
            return False

        GLib.timeout_add(360, clear_flash)
        callback(button)

    def on_fullscreen(_button):
        toggle_fullscreen()
        # Switch between the full and the compact panel without waiting for the next poll.
        GLib.timeout_add(700, update_visibility_once)

    regular_buttons = []
    fullscreen_button = None
    for label, tooltip, callback in (
        ("⛶", "Видео на весь экран или обратно", on_fullscreen),
        ("⌂", "К плиткам", on_home),
        ("←", "Назад", on_back),
        ("→", "Вперёд", on_forward),
        ("⌨", "Клавиатура", on_keyboard),
        ("🔊\ufe0e", "Громкость", on_volume),
        ("◷", "Таймер экрана", on_timer),
    ):
        button = Gtk.Button.new_with_label(label)
        button.set_tooltip_text(tooltip)
        button.get_style_context().add_class("touch-button")
        button.connect("clicked", lambda widget, action=callback: on_touch_click(widget, action))
        buttons.pack_start(button, True, True, 0)
        if callback is on_fullscreen:
            fullscreen_button = button
        else:
            regular_buttons.append(button)
    window.add(panel)
    window.connect("destroy", Gtk.main_quit)
    visible = False

    def update_visibility():
        nonlocal visible, pinned
        should_show = touch_available()
        # Over fullscreen video only the fullscreen button stays, so touch users can leave it.
        compact = fullscreen_active()
        if (not should_show or compact) and pinned:
            pinned = False
            set_keyboard_visible(False)
        if (not should_show or compact) and volume_panel.get_visible():
            close_volume()
        if (not should_show or compact) and timer_panel.get_visible():
            close_timer()
        if should_show and visible and not dragging:
            apply_position(position["top"], position["right"])
        if should_show != visible:
            if should_show:
                window.show_all()
                GLib.idle_add(apply_position, position["top"], position["right"])
            else:
                window.hide()
            visible = should_show
        if visible:
            handle.set_visible(not compact)
            for button in regular_buttons:
                button.set_visible(not compact)
            fullscreen_button.set_visible(True)
        return True

    def update_visibility_once():
        update_visibility()
        return False

    def keep_keyboard_open():
        if pinned and keyboard_visible() is False:
            set_keyboard_visible(True)
        return True

    update_visibility()
    GLib.timeout_add(150, keep_keyboard_open)
    GLib.timeout_add_seconds(2, update_visibility)
    GLib.timeout_add_seconds(5, refresh_timer_status)
    Gtk.main()


if __name__ == "__main__":
    main()
