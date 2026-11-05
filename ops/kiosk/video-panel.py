#!/usr/bin/python3
"""Focusless current-video controls above the TV player; no media data is read."""

# GI versions must be selected before importing their modules.
# ruff: noqa: E402, I001

import queue
import signal
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, GLib, GLibUnix, Gtk, GtkLayerShell

from video_panel_client import bind_parent, local_request

STYLE = b"""
window { background: transparent; }
.video-panel { background: rgba(13, 27, 48, 0.94); border: 1px solid #7697b1;
  border-radius: 14px; padding: 18px; }
.video-panel label { color: #f5f7fb; font: 18px sans-serif; }
.video-panel .video-title { font: bold 21px sans-serif; }
.video-panel button, .video-panel checkbutton, .video-panel radiobutton {
  color: #f5f7fb; font: 17px sans-serif; min-height: 42px; }
.video-panel button { background-image: none; background-color: #294865;
  border: 1px solid #7697b1; border-radius: 8px; padding: 5px 12px; }
.video-panel button:active { background-color: #176991; }
"""

MESSAGES = {
    "unavailable": "Видео недоступно или плеер не поддерживается.",
    "choose": "Выберите настройки и нажмите «Применить».",
    "changed": "Видео сменилось. Выберите настройки заново.",
    "pending": "Применяем настройки…",
    "completed": "Запрос выполнен. Проверьте изображение.",
    "unconfirmed": "Результат не подтверждён. Проверьте изображение.",
}


class VideoPanel:
    def __init__(self):
        self.state = None
        self.inflight = False
        self.rendering = False
        self.offline = True
        self.stopped = False
        self.close_intent = None
        self.jobs = queue.Queue(maxsize=1)
        self.worker = threading.Thread(target=self._worker_loop, daemon=True, name="video-panel")
        self.worker.start()
        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_accept_focus(False)
        screen = Gdk.Screen.get_default()
        if screen and screen.get_rgba_visual():
            self.window.set_visual(screen.get_rgba_visual())
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, "ad-linux-tv-video-panel")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, 80)
        GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.RIGHT, 18)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.get_style_context().add_class("video-panel")
        panel.set_size_request(440, -1)
        title = Gtk.Label(label="Формат и зеркало")
        title.set_xalign(0)
        title.get_style_context().add_class("video-title")
        panel.pack_start(title, False, False, 0)
        self.status = Gtk.Label()
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        panel.pack_start(self.status, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.choices = {}
        group = None
        for mode, label in (("original", "Исходный"), ("4:3", "4:3"), ("16:9", "16:9")):
            button = Gtk.RadioButton.new_with_label_from_widget(group, label)
            if group is None:
                group = button
            button.set_focus_on_click(False)
            button.connect("toggled", self._mode_changed, mode)
            self.choices[mode] = button
            row.pack_start(button, False, False, 0)
        panel.pack_start(row, False, False, 0)
        self.mirror = Gtk.CheckButton.new_with_label("Зеркало по горизонтали")
        self.mirror.set_focus_on_click(False)
        self.mirror.connect("toggled", self._mirror_changed)
        panel.pack_start(self.mirror, False, False, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.apply_button = Gtk.Button.new_with_label("Применить")
        self.apply_button.set_focus_on_click(False)
        self.apply_button.connect("clicked", self._apply)
        self.close_button = Gtk.Button.new_with_label("Закрыть")
        self.close_button.set_focus_on_click(False)
        self.close_button.connect("clicked", self._close)
        actions.pack_start(self.apply_button, True, True, 0)
        actions.pack_start(self.close_button, True, True, 0)
        panel.pack_start(actions, False, False, 0)
        self.window.add(panel)
        self.window.connect("destroy", self._destroyed)
        GLib.timeout_add(500, self.tick)
        self.tick()

    def stop(self):
        self.stopped = True
        try:
            self.jobs.put_nowait(None)
        except queue.Full:
            pass

    def _destroyed(self, _window):
        self.stop()
        Gtk.main_quit()

    def _request(self, body=None):
        if self.inflight or self.stopped:
            return
        self.inflight = True
        self._render()

        try:
            self.jobs.put_nowait((body,))
        except queue.Full:
            self.inflight = False
            self.offline = True
            self._render()

    def _worker_loop(self):
        while True:
            item = self.jobs.get()
            if item is None:
                return
            try:
                state, failed = local_request(item[0]), False
            except Exception:  # Disable actions on local failure; never log media.
                state, failed = None, True
            GLib.idle_add(self._received, state, failed)

    def _received(self, state, failed):
        if self.stopped:
            return False
        self.inflight = False
        if failed:
            self.offline = True
            self._render()
            return False
        self.offline = False
        self.state = state
        if self.close_intent:
            instance, opening = self.close_intent
            if state["visible"] and (state["instance"], state["opening"]) == (instance, opening):
                self._request({"action": "close", "instance": instance, "opening": opening})
                return False
            self.close_intent = None
        self._render()
        return False

    def tick(self):
        if self.stopped:
            return False
        if not self.inflight:
            self._request()
        return True

    def _render(self):
        state = self.state
        if self.close_intent or not state or not state["visible"]:
            self.window.hide()
            return
        if not self.window.get_visible():
            self.window.show_all()
        self.rendering = True
        self.choices[state["mode"]].set_active(True)
        self.mirror.set_active(state["mirror"])
        self.rendering = False
        self.status.set_text(
            "Нет связи с медиацентром." if self.offline else MESSAGES[state["status"]]
        )
        enabled = (
            state["available"] and not state["busy"] and not self.inflight and not self.offline
        )
        for button in self.choices.values():
            button.set_sensitive(enabled)
        self.mirror.set_sensitive(enabled)
        self.apply_button.set_sensitive(enabled)
        # The local close remains available after an I/O error.
        self.close_button.set_sensitive(not self.inflight)

    def _choose(self, mode, mirror):
        if (
            not self.state
            or self.inflight
            or self.offline
            or not self.state["visible"]
            or not self.state["available"]
            or self.state["busy"]
        ):
            return
        state = self.state
        self._request(
            {
                "action": "choose",
                "instance": state["instance"],
                "revision": state["revision"],
                "mode": mode,
                "mirror": mirror,
            }
        )

    def _mode_changed(self, button, mode):
        if button.get_active() and not self.rendering:
            self._choose(mode, self.mirror.get_active())

    def _mirror_changed(self, button):
        if not self.rendering and self.state:
            self._choose(self.state["mode"], button.get_active())

    def _apply(self, _button):
        if (
            self.state
            and not self.inflight
            and not self.offline
            and self.state["visible"]
            and self.state["available"]
            and not self.state["busy"]
        ):
            state = self.state
            self._request(
                {"action": "apply", "instance": state["instance"], "revision": state["revision"]}
            )

    def _close(self, _button):
        if self.state and not self.inflight:
            self.close_intent = (self.state["instance"], self.state["opening"])
            self.window.hide()
            self._request(
                {
                    "action": "close",
                    "instance": self.state["instance"],
                    "opening": self.state["opening"],
                }
            )


def main():
    if not bind_parent():
        raise SystemExit("TV video panel parent unavailable")
    panel = VideoPanel()

    def quit_main(*_args):
        Gtk.main_quit()
        return False

    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_main)
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, quit_main)
    try:
        Gtk.main()
    finally:
        panel.stop()


if __name__ == "__main__":
    main()
