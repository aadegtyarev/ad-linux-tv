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
        self.current_request = None
        self.draft = None
        self.notice = None
        self.rendering = False
        self.offline = True
        self.stopped = False
        self.close_intent = None
        self.close_sent = False
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
        # Only update the action button here: rendering radio buttons from their
        # toggled handler can reenter GTK and undo the user’s selection.
        self.apply_button.set_sensitive(False)
        self.current_request = body
        if body and body.get("action") == "close":
            self.close_sent = True
        try:
            self.jobs.put_nowait((body,))
        except queue.Full:
            self.inflight = False
            self.current_request = None
            self.draft = None
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
        request = self.current_request
        self.current_request = None
        self.inflight = False
        if failed:
            if request is not None:
                self.notice = "Не удалось подтвердить запрос. Проверьте настройки заново."
            elif self.draft:
                self.notice = "Выбор не сохранён. Проверьте настройки заново."
            self.draft = None
            self.offline = True
            self._render()
            return False
        self.offline = False
        previous = self.state
        self.state = state
        if previous and (
            not state["visible"]
            or (state["instance"], state["opening"]) != (previous["instance"], previous["opening"])
        ):
            self.notice = None
        if self.close_intent:
            instance, opening = self.close_intent
            if state["visible"] and (state["instance"], state["opening"]) == (instance, opening):
                if not self.close_sent:
                    self._request({"action": "close", "instance": instance, "opening": opening})
                self._render()
                return False
            self.close_intent = None
            self.close_sent = False
        if self.draft:
            same = (
                previous
                and state["visible"]
                and state["available"]
                and not state["busy"]
                and (state["instance"], state["opening"])
                == (previous["instance"], previous["opening"])
            )
            if request and request.get("action") == "choose":
                same = (
                    same
                    and state["revision"] == request["revision"] + 1
                    and (state["mode"], state["mirror"]) == (request["mode"], request["mirror"])
                )
            else:
                same = same and state["revision"] == previous["revision"]
            if not same:
                self.draft = None
                self.notice = "Выбор не сохранён. Проверьте настройки заново."
            elif (state["mode"], state["mirror"]) == self.draft:
                self.draft = None
            else:
                self._send_choice()
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
        mode, mirror = self.draft or (state["mode"], state["mirror"])
        self.choices[mode].set_active(True)
        self.mirror.set_active(mirror)
        self.rendering = False
        self.status.set_text(
            "Нет связи с медиацентром. Проверьте настройки заново."
            if self.offline
            else self.notice or MESSAGES[state["status"]]
        )
        enabled = (
            state["available"]
            and not state["busy"]
            and not self.offline
            and not (
                self.current_request and self.current_request.get("action") in ("apply", "close")
            )
        )
        for button in self.choices.values():
            button.set_sensitive(enabled)
        self.mirror.set_sensitive(enabled)
        self.apply_button.set_sensitive(enabled and not self.inflight and not self.draft)
        # The local close remains available after an I/O error.
        self.close_button.set_sensitive(True)

    def _choose(self, mode, mirror):
        if (
            not self.state
            or self.offline
            or self.close_intent
            or not self.state["visible"]
            or not self.state["available"]
            or self.state["busy"]
            or (self.current_request and self.current_request.get("action") != "choose")
            and self.current_request is not None
        ):
            return
        self.draft = (mode, mirror)
        self.notice = None
        if not self.inflight:
            self._send_choice()
        # Do not render here: GTK radio toggle signals can be reentrant.

    def _send_choice(self):
        state = self.state
        mode, mirror = self.draft
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
            self._choose((self.draft or (self.state["mode"], False))[0], button.get_active())

    def _apply(self, _button):
        if (
            self.state
            and not self.inflight
            and not self.draft
            and not self.close_intent
            and not self.offline
            and self.state["visible"]
            and self.state["available"]
            and not self.state["busy"]
        ):
            state = self.state
            self.notice = None
            self.status.set_text(MESSAGES["pending"])
            for button in self.choices.values():
                button.set_sensitive(False)
            self.mirror.set_sensitive(False)
            self._request(
                {"action": "apply", "instance": state["instance"], "revision": state["revision"]}
            )

    def _close(self, _button):
        if self.state and not self.close_intent:
            self.close_intent = (self.state["instance"], self.state["opening"])
            self.close_sent = False
            self.draft = None
            self.window.hide()
            if not self.inflight:
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
