#!/usr/bin/env bash
# Uses a private headless compositor and synthetic keys, never the active TV session.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
base=$(mktemp -d /tmp/ad-tv-ok-lab.XXXXXXXX)
trap 'rm -rf "$base"' EXIT
mkdir -p "$base/run" "$base/config" "$base/home"
chmod 700 "$base/run"
PYTHONPATH="$ROOT/src" /usr/bin/python3 - "$ROOT/ops/kiosk/labwc/rc.xml" "$base/config/rc.xml" "${AD_TV_OK_TEMPLATE:-normal}" <<'PY'
import sys
from xml.etree import ElementTree
from ad_linux_tv.kiosk_config import _known_labwc_defaults, add_default_ok_bindings
root = ElementTree.parse(sys.argv[1]).getroot()
if sys.argv[3] == 'implicit':
    root.remove(root.find('keyboard'))
elif sys.argv[3] in ('alias', 'numeric'):
    key = 'XF86_Select' if sys.argv[3] == 'alias' else '0x1008ffa0'
    binding = ElementTree.SubElement(root.find('keyboard'), 'keybind',
                                     {'key': key, 'onRelease': 'yes'})
    ElementTree.SubElement(binding, 'action', {'name': 'Execute', 'command': '/usr/bin/wtype -k F8'})
assert _known_labwc_defaults(), 'unverified labwc defaults'
add_default_ok_bindings(root, defaults_verified=True)
ElementTree.ElementTree(root).write(sys.argv[2])
PY
cat > "$base/start" <<'SCRIPT'
#!/bin/sh
set -e
/usr/bin/python3 "$TEST_ROOT/tests/wayland/default_ok_background.py" > "$BASE/events" 2>&1 &
window=$!
trap 'kill "$window" 2>/dev/null || true; wait "$window" 2>/dev/null || true' EXIT
for i in $(seq 1 40); do grep -q '^window_fullscreen True$' "$BASE/events" && break; sleep .1; done
grep -q '^window_fullscreen True$' "$BASE/events"
sleep .3
wtype -s 100 -k Return -s 300 -k Left -s 200 -k Right -s 200 -k Up -s 200 -k Down -s 300 -k XF86Select -s 800 -k XF86OK -s 800
sleep .5
printf 'CLIENT_EVENTS\n'; grep -E '^(press|release) ' "$BASE/events" || true
expected=3
case "$OK_TEMPLATE" in alias|numeric) expected=2;; esac
[ "$(grep -c '^press Return$' "$BASE/events")" -eq "$expected" ]
[ "$(grep -c '^release Return$' "$BASE/events")" -eq "$expected" ]
case "$OK_TEMPLATE" in alias|numeric) grep -q '^press F8$' "$BASE/events";; esac
for key in Left Right Up Down; do
  grep -q "^press $key$" "$BASE/events"
  grep -q "^release $key$" "$BASE/events"
done
! grep -Eq '^(press|release) (XF86Select|Select|XF86OK|OK)$' "$BASE/events"
wtype -s 100 -P XF86Select -s 1200 -p XF86Select -s 700
sleep .4
held=$(grep -c '^press Return$' "$BASE/events")
echo "HOLD_RETURN_TOTAL=$held"
case "$OK_TEMPLATE" in
  alias|numeric) [ "$held" -eq 2 ] && [ "$(grep -c '^press F8$' "$BASE/events")" -eq 2 ];;
  *) [ "$held" -eq 4 ];;
esac
echo SYNTHETIC_OK_PASS
SCRIPT
chmod +x "$base/start"
export BASE="$base" TEST_ROOT="$ROOT" OK_TEMPLATE="${AD_TV_OK_TEMPLATE:-normal}" HOME="$base/home" XDG_RUNTIME_DIR="$base/run" XDG_CONFIG_HOME="$base/config" XDG_DATA_HOME="$base/home/.local/share"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
if ! timeout 18 dbus-run-session -- labwc -C "$base/config" -S "$base/start" > "$base/log" 2>&1; then
  echo synthetic_scene_failed
  grep -E 'CLIENT|^(press|release) |SYNTHETIC|error|Error' "$base/log" || true
  exit 1
fi
grep -q '^SYNTHETIC_OK_PASS$' "$base/log"
grep -E 'CLIENT|HOLD_RETURN|^(press|release) |SYNTHETIC' "$base/log"
