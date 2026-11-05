#!/usr/bin/env bash
# Disposable headless compositor only: no owner desktop, device or video is used.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
for command in labwc dbus-run-session wlrctl wtype grim /usr/bin/python3; do
  command -v "$command" >/dev/null || { echo "Missing test dependency: $command" >&2; exit 1; }
done
base=$(mktemp -d /tmp/ad-tv-video-panel-test.XXXXXX)
trap 'rm -rf "$base"' EXIT
mkdir -p "$base/run" "$base/config" "$base/home"
chmod 700 "$base/run"
printf '%s\n' '<labwc_config><keyboard><default /></keyboard></labwc_config>' > "$base/config/rc.xml"
cat > "$base/start" <<'SCRIPT'
#!/bin/sh
set -e
/usr/bin/python3 "$TEST_ROOT/tests/wayland/video_panel_fixture.py" > "$TEST_BASE/server.log" 2>&1 &
server=$!
# Refuse to start the panel if the synthetic server could not bind its port.
for i in $(seq 1 50); do grep -q fixture_server_ready "$TEST_BASE/server.log" && break; kill -0 "$server" || exit 1; sleep .1; done
grep -q fixture_server_ready "$TEST_BASE/server.log"
/usr/bin/python3 "$TEST_ROOT/tests/wayland/video_panel_background.py" > "$TEST_BASE/background.log" 2>&1 &
background=$!
trap 'kill ${panel:-} "$background" "$server" ${keyboard:-} 2>/dev/null || true; wait ${panel:-} "$background" "$server" ${keyboard:-} 2>/dev/null || true' EXIT
for i in $(seq 1 50); do grep -q 'fixture_background_fullscreen True' "$TEST_BASE/background.log" && break; sleep .1; done
grep -q 'fixture_background_fullscreen True' "$TEST_BASE/background.log"
grim "$TEST_BASE/background.png"
AD_TV_VIDEO_PANEL_PARENT=$$ /usr/bin/python3 "$TEST_ROOT/ops/kiosk/video-panel.py" > "$TEST_BASE/panel.log" 2>&1 &
panel=$!
sleep 1
kill -0 "$panel" && kill -0 "$server"
grim "$TEST_BASE/panel.png"
if cmp -s "$TEST_BASE/background.png" "$TEST_BASE/panel.png"; then echo fixture_panel_not_visible; exit 1; fi
move() { wlrctl pointer move -20000 -20000; wlrctl pointer move "$1" "$2"; }
move 100 500; wlrctl pointer click; sleep .3
grep -q fixture_background_clicked "$TEST_BASE/background.log"
# Keep the synthetic keyboard alive while checking that panel clicks do not steal focus.
wtype -d 1000 abcdefgh > /dev/null 2>&1 &
keyboard=$!
sleep .5
grep -q fixture_background_focus_in "$TEST_BASE/background.log"
move 965 200; wlrctl pointer click; sleep .6
move 837 257; wlrctl pointer click; sleep .6
move 930 318; wlrctl pointer click; sleep .6
grep -q 'fixture_action apply mode 4:3 mirror True' "$TEST_BASE/server.log"
if grep -q fixture_background_focus_out "$TEST_BASE/background.log"; then echo fixture_focus_stolen; exit 1; fi
kill "$keyboard" 2>/dev/null || true; wait "$keyboard" 2>/dev/null || true
move 1150 318; wlrctl pointer click; sleep .6
grep -q 'fixture_action close' "$TEST_BASE/server.log"
before=$(grep -c fixture_background_clicked "$TEST_BASE/background.log")
move 930 318; wlrctl pointer click; sleep .3
after=$(grep -c fixture_background_clicked "$TEST_BASE/background.log")
[ "$after" -gt "$before" ]
kill "$panel"; wait "$panel" || true
if kill -0 "$panel" 2>/dev/null; then echo fixture_panel_survived_cleanup; exit 1; fi
panel=
echo fixture_panel_wayland_pass
SCRIPT
chmod +x "$base/start"
export TEST_ROOT="$ROOT" TEST_BASE="$base" HOME="$base/home" XDG_RUNTIME_DIR="$base/run"
export XDG_CONFIG_HOME="$base/config" XDG_DATA_HOME="$base/home/.local/share"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
if ! timeout 20 dbus-run-session -- labwc -C "$base/config" -S "$base/start" > "$base/log" 2>&1; then
  echo 'Headless video-panel scene failed.' >&2
  tail -n 30 "$base/log" "$base/panel.log" "$base/server.log" "$base/background.log" 2>/dev/null || true
  exit 1
fi
if ! grep -q '^fixture_panel_wayland_pass$' "$base/log"; then
  echo 'Headless video-panel scene did not finish.' >&2
  tail -n 30 "$base/log" "$base/panel.log" "$base/server.log" "$base/background.log" 2>/dev/null || true
  exit 1
fi
grep '^fixture_panel_wayland_pass$' "$base/log"
