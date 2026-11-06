#!/usr/bin/env bash
# Isolated compositor and synthetic keys only; never inspect the active TV desktop.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
base=$(mktemp -d /tmp/ad-tv-shortcut-learn.XXXXXXXX)
trap 'rm -rf "$base"' EXIT
mkdir -p "$base/run" "$base/config" "$base/home" "$base/app"
chmod 700 "$base/run"
cp "$ROOT/ops/kiosk/learn-tv-shortcut.py" "$ROOT/ops/kiosk/video_panel_client.py" \
  "$ROOT/src/ad_linux_tv/tv_shortcut_keys.py" "$base/app/"
printf '%s\n' '<labwc_config><keyboard><default/></keyboard></labwc_config>' > "$base/config/rc.xml"
cat > "$base/start" <<'SCRIPT'
#!/bin/sh
set -e
/usr/bin/python3 "$TEST_ROOT/tests/wayland/default_ok_background.py" > "$BASE/background.log" 2>&1 &
background=$!
trap 'kill ${learner:-} "$background" 2>/dev/null || true; wait ${learner:-} "$background" 2>/dev/null || true' EXIT
for i in $(seq 1 40); do grep -q '^window_fullscreen True$' "$BASE/background.log" && break; sleep .1; done
grep -q '^window_fullscreen True$' "$BASE/background.log"
AD_TV_VIDEO_PANEL_PARENT=$$ /usr/bin/python3 "$BASE/app/learn-tv-shortcut.py" > "$BASE/result" 2>/dev/null &
learner=$!
sleep 1
wtype -s 200 -k XF86Launch1
wait "$learner"; learner=
[ "$(tr -d '\n' < "$BASE/result")" = XF86Launch1 ]
wtype -s 200 -k Return -s 300
grep -q '^press Return$' "$BASE/background.log"
AD_TV_VIDEO_PANEL_PARENT=$$ /usr/bin/python3 "$BASE/app/learn-tv-shortcut.py" > "$BASE/result" 2>/dev/null &
learner=$!
sleep 1
wtype -s 200 -k a -s 200 -M shift -k XF86Launch2 -m shift -s 200
kill -0 "$learner"
[ ! -s "$BASE/result" ]
! grep -q '^press a$' "$BASE/background.log"
wtype -s 200 -k XF86Launch2
wait "$learner"; learner=
[ "$(tr -d '\n' < "$BASE/result")" = XF86Launch2 ]
AD_TV_VIDEO_PANEL_PARENT=$$ /usr/bin/python3 "$BASE/app/learn-tv-shortcut.py" > "$BASE/result" 2>/dev/null &
learner=$!
sleep 1
kill -TERM "$learner"
if wait "$learner"; then echo cancelled_key_accepted; exit 1; fi
learner=
[ ! -s "$BASE/result" ]
echo SYNTHETIC_LEARNING_PASS
SCRIPT
chmod +x "$base/start"
export BASE="$base" TEST_ROOT="$ROOT" HOME="$base/home" XDG_RUNTIME_DIR="$base/run" XDG_CONFIG_HOME="$base/config" XDG_DATA_HOME="$base/home/.local/share"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
if ! timeout 15 dbus-run-session -- labwc -C "$base/config" -S "$base/start" > "$base/log" 2>&1; then
  echo synthetic_learning_scene_failed
  tail -n 25 "$base/log"
  exit 1
fi
grep -q '^SYNTHETIC_LEARNING_PASS$' "$base/log"
echo SYNTHETIC_LEARNING_PASS
