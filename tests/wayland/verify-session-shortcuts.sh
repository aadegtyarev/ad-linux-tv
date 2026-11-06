#!/usr/bin/env bash
# Real generated bindings, private labwc, synthetic keys and inert test actions.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
base=$(mktemp -d /tmp/ad-tv-shortcut-bindings.XXXXXXXX)
trap 'rm -rf "$base"' EXIT
mkdir -p "$base/run" "$base/config" "$base/home"
chmod 700 "$base/run"
for action in video_panel magnifier fullscreen volume_up volume_down standard_up standard_down; do
  printf '#!/bin/sh\nprintf "%%s\\n" "%s" >> "%s/actions"\n' "$action" "$base" > "$base/$action"
  chmod +x "$base/$action"
done
PYTHONPATH="$ROOT/src" /usr/bin/python3 - "$ROOT/ops/kiosk/labwc/rc.xml" "$base" "${AD_TV_SHORTCUT_TEMPLATE:-stock}" <<'PY'
import sys
from pathlib import Path
from xml.etree import ElementTree
from ad_linux_tv.kiosk_config import (_SHORTCUT_COMMANDS, _known_labwc_defaults,
                                      add_default_volume_bindings, add_selected_shortcuts)
root = ElementTree.parse(sys.argv[1]).getroot()
if sys.argv[3] == 'legacy':
    keyboard = root.find('keyboard')
    for key in ('XF86_AudioRaiseVolume', 'XF86_AudioLowerVolume'):
        keyboard.remove(keyboard.find(f"keybind[@key='{key}']"))
    add_default_volume_bindings(root, defaults_verified=_known_labwc_defaults())
choices = {'video_panel': 'XF86Launch1', 'magnifier': 'XF86Launch2', 'fullscreen': 'XF86Launch3',
           'ok': 'XF86Launch4', 'volume_up': 'XF86Launch5', 'volume_down': 'XF86Launch6'}
assert _known_labwc_defaults(), 'unverified labwc defaults'
assert add_selected_shortcuts(root, choices, defaults_verified=_known_labwc_defaults()) == choices
for action, key in choices.items():
    binding = root.find(f"keyboard/keybind[@key='{key}']")
    command = binding.find('action')
    assert command.get('command') == _SHORTCUT_COMMANDS[action]
    assert binding.get('onRelease') == ('no' if action in ('volume_up', 'volume_down') else 'yes')
    if action != 'ok':
        command.set('command', str(Path(sys.argv[2]) / action))
for key, action in [('XF86_AudioRaiseVolume', 'standard_up'), ('XF86_AudioLowerVolume', 'standard_down')]:
    command = root.find(f"keyboard/keybind[@key='{key}']/action")
    assert command.get('command').startswith('/usr/bin/wpctl set-volume')
    command.set('command', str(Path(sys.argv[2]) / action))
ElementTree.ElementTree(root).write(Path(sys.argv[2]) / 'config/rc.xml')
PY
cat > "$base/start" <<'SCRIPT'
#!/bin/sh
set -e
/usr/bin/python3 "$TEST_ROOT/tests/wayland/shortcut_background.py" > "$BASE/events" 2>&1 &
background=$!
trap 'kill "$background" 2>/dev/null || true; wait "$background" 2>/dev/null || true' EXIT
for i in $(seq 1 40); do grep -q '^window_fullscreen True$' "$BASE/events" && break; sleep .1; done
grep -q '^window_fullscreen True$' "$BASE/events"
sleep .3
wtype -s 100 -k Return -s 200 -k XF86Launch7 -s 200 -k XF86Launch1 -s 200 -k XF86Launch2 -s 200 -k XF86Launch3 -s 200 -k XF86Launch4 -s 400 -k XF86Launch5 -s 200 -k XF86Launch6 -s 200 -k XF86AudioRaiseVolume -s 200 -k XF86AudioLowerVolume -s 200 -k a -s 300
sleep .5
for action in video_panel magnifier fullscreen volume_up volume_down standard_up standard_down; do [ "$(grep -c "^$action$" "$BASE/actions")" -eq 1 ]; done
[ "$(grep -c '^press Return$' "$BASE/events")" -eq 2 ]; [ "$(grep -c '^release Return$' "$BASE/events")" -eq 2 ]
grep -q '^press Launch7$' "$BASE/events"; grep -q '^release Launch7$' "$BASE/events"
grep -q '^press a$' "$BASE/events"; grep -q '^release a$' "$BASE/events"
! grep -Eq '^(press|release) Launch[123456]$' "$BASE/events"
for n in 1 2 3 4 5 6; do wtype -s 100 -P "XF86Launch$n" -s 1200 -p "XF86Launch$n" -s 300; done
sleep .5
for action in video_panel magnifier fullscreen; do [ "$(grep -c "^$action$" "$BASE/actions")" -eq 2 ]; done
[ "$(grep -c '^press Return$' "$BASE/events")" -eq 3 ]
[ "$(grep -c '^volume_up$' "$BASE/actions")" -gt 2 ]
[ "$(grep -c '^volume_down$' "$BASE/actions")" -gt 2 ]
[ "$(grep -c '^standard_up$' "$BASE/actions")" -eq 1 ]
[ "$(grep -c '^standard_down$' "$BASE/actions")" -eq 1 ]
echo SYNTHETIC_SHORTCUTS_PASS
SCRIPT
chmod +x "$base/start"
export BASE="$base" TEST_ROOT="$ROOT" HOME="$base/home" XDG_RUNTIME_DIR="$base/run" XDG_CONFIG_HOME="$base/config" XDG_DATA_HOME="$base/home/.local/share"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
if ! timeout 30 dbus-run-session -- labwc -C "$base/config" -S "$base/start" > "$base/log" 2>&1; then
  echo synthetic_shortcuts_scene_failed
  tail -n 25 "$base/log"
  exit 1
fi
grep -q '^SYNTHETIC_SHORTCUTS_PASS$' "$base/log"
echo SYNTHETIC_SHORTCUTS_PASS
