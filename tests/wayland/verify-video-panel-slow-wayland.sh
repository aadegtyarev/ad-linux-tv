#!/usr/bin/env bash
# Synthetic, disposable headless compositor. No live desktop, video, or network.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
for cmd in labwc wlrctl wtype gcc timeout /usr/bin/python3; do
  command -v "$cmd" >/dev/null || { echo "Missing test dependency: $cmd" >&2; exit 1; }
done
umask 077
base=$(mktemp -d /tmp/ad-tv-panel-slow.XXXXXXXX)
trap 'rm -rf "$base"' EXIT
mkdir -p "$base/run" "$base/config" "$base/home"
printf '%s\n' '<labwc_config><keyboard><default /></keyboard></labwc_config>' > "$base/config/rc.xml"
gcc -shared -fPIC -O0 -o "$base/delay-pointer.so" "$ROOT/tests/wayland/video_panel_delay_pointer.c" -ldl -l:libwayland-client.so.0
cat > "$base/start" <<'SCRIPT'
#!/bin/sh
set -eu
server= background= panel= keyboard=
cleanup() {
  for pid in "$panel" "$keyboard" "$background" "$server"; do
    [ -z "$pid" ] || kill "$pid" 2>/dev/null || true
  done
  wait || true
}
trap cleanup EXIT
/usr/bin/python3 "$TEST_ROOT/tests/wayland/video_panel_slow_fixture.py" > "$TEST_BASE/server.log" 2>&1 & server=$!
for i in $(seq 1 50); do grep -q fixture_server_ready "$TEST_BASE/server.log" && break; kill -0 "$server"; sleep .1; done
grep -q fixture_server_ready "$TEST_BASE/server.log"
/usr/bin/python3 "$TEST_ROOT/tests/wayland/video_panel_background.py" > "$TEST_BASE/background.log" 2>&1 & background=$!
for i in $(seq 1 50); do grep -q 'fixture_background_fullscreen True' "$TEST_BASE/background.log" && break; kill -0 "$background"; sleep .1; done
grep -q 'fixture_background_fullscreen True' "$TEST_BASE/background.log"
AD_TV_VIDEO_PANEL_PARENT=$$ /usr/bin/python3 "$TEST_ROOT/tests/wayland/video_panel_trace.py" > "$TEST_BASE/panel.log" 2>&1 & panel=$!
for i in $(seq 1 100); do grep -q '^TRACE_WIDGET ratio ' "$TEST_BASE/panel.log" && break; kill -0 "$panel"; sleep .1; done
grep -q '^TRACE_WIDGET ratio ' "$TEST_BASE/panel.log"
move() { wlrctl pointer move -20000 -20000; wlrctl pointer move "$1" "$2"; }
widget() { coords=$(grep "^TRACE_WIDGET $1 " "$TEST_BASE/panel.log" | tail -1); set -- $coords; move "$3" "$4"; }
move 100 500; wlrctl pointer click; sleep .3
wtype -d 1000 abcdefghijklmnop >/dev/null 2>&1 & keyboard=$!
sleep .3
wtype -s 100 -k Return -s 200
sleep .2
grep -q fixture_background_clicked "$TEST_BASE/background.log"
grep -q 'fixture_background_key Return' "$TEST_BASE/background.log"
# Wait for an actual poll that disables Apply and its successful main-loop
# completion that re-enables Apply. The trace is emitted by the GTK thread.
for i in $(seq 1 50); do
  if grep -q '^TRACE_POLL_REQUEST 1 0$' "$TEST_BASE/panel.log" &&
     grep -q '^TRACE_POLL_RECEIVED 0 1 failed 0$' "$TEST_BASE/panel.log"; then break; fi
  kill -0 "$panel"; sleep .1
done
grep -q '^TRACE_POLL_REQUEST 1 0$' "$TEST_BASE/panel.log"
grep -q '^TRACE_POLL_RECEIVED 0 1 failed 0$' "$TEST_BASE/panel.log"
# A real press is held across a completed poll; its release selects 4:3.
widget choice
LD_PRELOAD="$TEST_BASE/delay-pointer.so" wlrctl pointer click
for i in $(seq 1 50); do grep -q 'fixture_action choose mode 4:3 mirror False' "$TEST_BASE/server.log" && break; sleep .1; done
grep -q 'fixture_action choose mode 4:3 mirror False' "$TEST_BASE/server.log"
sleep .8
# Apply may be insensitive during a poll. Retry until the one actual request starts.
for i in $(seq 1 40); do widget apply; wlrctl pointer click; sleep .05; grep -q TRACE_APPLY_WAIT "$TEST_BASE/panel.log" && break; done
grep -q TRACE_APPLY_WAIT "$TEST_BASE/panel.log"
# During the delayed worker, attempted changes must not be accepted.
sleep .2
widget mirror; wlrctl pointer click
widget ratio; wlrctl pointer click
sleep .85
[ "$(grep '^TRACE_STATE ' "$TEST_BASE/panel.log" | tail -1 | cut -d' ' -f2-5)" = '1 0 0 0' ]
for i in $(seq 1 50); do grep -q 'fixture_action apply mode 4:3 mirror False' "$TEST_BASE/server.log" && break; sleep .1; done
grep -q 'fixture_action apply mode 4:3 mirror False' "$TEST_BASE/server.log"
for i in $(seq 1 50); do grep -q 'TRACE_STATE 1 1 1 .*Запрос выполнен' "$TEST_BASE/panel.log" && break; sleep .1; done
grep -q 'TRACE_STATE 1 1 1 .*Запрос выполнен' "$TEST_BASE/panel.log"
! grep -q fixture_background_focus_out "$TEST_BASE/background.log"
# Panel clicks must not reach the surrounding window; a subsequent outside click must.
[ "$(grep -c fixture_background_clicked "$TEST_BASE/background.log")" -eq 1 ]
move 100 500; wlrctl pointer click; sleep .3
[ "$(grep -c fixture_background_clicked "$TEST_BASE/background.log")" -eq 2 ]
wtype -s 100 -k Return -s 200; sleep .2
[ "$(grep -c 'fixture_background_key Return' "$TEST_BASE/background.log")" -eq 2 ]
/usr/bin/python3 - "$TEST_BASE/panel.log" "$TEST_BASE/server.log" <<'PY'
import sys
panel = open(sys.argv[1]).read().splitlines()
server = open(sys.argv[2]).read().splitlines()
press = panel.index('TRACE_PRESS 4:3')
release = panel.index('TRACE_RELEASE 4:3', press)
assert 'TRACE_POLL_END' in panel[press:release], 'no completed GET during held press'
assert 'TRACE_POLL_RECEIVED 0 1 failed 0' in panel[press:release], 'no successful GTK poll update during held press'
# Assert the same poll cycle actually disabled and restored Apply.
cycle = next(i for i, line in enumerate(panel) if line == 'TRACE_POLL_REQUEST 1 0')
assert 'TRACE_POLL_END' in panel[cycle:], 'poll did not finish'
end = panel.index('TRACE_POLL_END', cycle)
received = next(line for line in panel[end:] if line.startswith('TRACE_POLL_RECEIVED '))
assert received == 'TRACE_POLL_RECEIVED 0 1 failed 0', 'Apply not restored after poll'
toggle = panel.index('TRACE_TOGGLE_END 4:3 active True')
apply = panel.index('TRACE_APPLY_WAIT', toggle)
assert all(line.split()[1] == '1' for line in panel[toggle:apply] if line.startswith('TRACE_STATE ')), 'selection reverted'
assert sum(line.startswith('TRACE_TOGGLE_BEGIN ') for line in panel) == 1, 'unexpected toggle'
assert server.count('fixture_received choose') == 1, 'duplicate choice request'
assert server.count('fixture_received apply') == 1, 'duplicate apply request'
assert sum(line.startswith('fixture_action choose ') for line in server) == 1, 'unexpected choice'
assert sum(line.startswith('fixture_action apply ') for line in server) == 1, 'unexpected apply'
PY
echo fixture_slow_panel_wayland_pass
SCRIPT
chmod +x "$base/start"
export TEST_ROOT="$ROOT" TEST_BASE="$base" HOME="$base/home" XDG_RUNTIME_DIR="$base/run"
export XDG_CONFIG_HOME="$base/config" XDG_DATA_HOME="$base/home/.local/share"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export DBUS_SESSION_BUS_ADDRESS="unix:path=$base/no-bus" NO_AT_BRIDGE=1
unset WAYLAND_DISPLAY DISPLAY HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
if ! timeout 35 labwc -C "$base/config" -S "$base/start" > "$base/log" 2>&1 ||
   ! grep -qx fixture_slow_panel_wayland_pass "$base/log"; then
  echo 'Headless slow video-panel scene failed.' >&2
  tail -n 40 "$base/log" "$base/panel.log" "$base/server.log" "$base/background.log" 2>/dev/null || true
  exit 1
fi
echo fixture_slow_panel_wayland_pass
