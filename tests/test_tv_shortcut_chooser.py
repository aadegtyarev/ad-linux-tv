"""The focused chooser ignores unrelated input without retaining or returning it."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from ad_linux_tv import tv_shortcut_keys


def test_rejected_keys_and_modifiers_do_not_end_the_prompt(monkeypatch):
    gi = ModuleType("gi")
    gi.require_version = lambda *_args: None
    repository = ModuleType("gi.repository")
    names = ("SHIFT", "CONTROL", "MOD1", "MOD3", "MOD4", "MOD5", "SUPER", "META", "HYPER")
    masks = SimpleNamespace(**{f"{name}_MASK": 1 << index for index, name in enumerate(names)})
    repository.Gdk = SimpleNamespace(ModifierType=masks)
    quits = []
    repository.Gtk = SimpleNamespace(main_quit=lambda: quits.append(True))
    repository.GLib = repository.GLibUnix = repository.GtkLayerShell = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    monkeypatch.setitem(sys.modules, "tv_shortcut_keys", tv_shortcut_keys)
    monkeypatch.setitem(
        sys.modules, "video_panel_client", SimpleNamespace(bind_parent=lambda: True)
    )
    path = Path(__file__).resolve().parents[1] / "ops/kiosk/learn-tv-shortcut.py"
    spec = importlib.util.spec_from_file_location("shortcut_chooser_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chooser = module.Chooser.__new__(module.Chooser)
    chooser.key = None
    keyval = tv_shortcut_keys.KEYSYMS["XF86Launch2"]
    assert chooser._pressed(None, SimpleNamespace(state=0, keyval=ord("a")))
    assert chooser._pressed(None, SimpleNamespace(state=masks.SHIFT_MASK, keyval=keyval))
    assert chooser.key is None and not quits
    assert chooser._pressed(None, SimpleNamespace(state=0, keyval=keyval))
    assert chooser.key == "XF86Launch2" and quits == [True]
