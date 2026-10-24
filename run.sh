#!/usr/bin/env bash
set -euo pipefail
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="${1:-$HOME/.config/ad-linux-tv/config.yaml}"
PROFILE="$HOME/snap/firefox/common/ad-linux-tv-profile"
"$DATA/venv/bin/ad-linux-tv" --config "$CONFIG" &
SERVER=$!
cleanup() {
  kill "$SERVER" 2>/dev/null || true
  wait "$SERVER" 2>/dev/null || true
}
trap cleanup EXIT
READY=0
for _ in {1..30}; do
  if "$DATA/venv/bin/python" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8765/health",timeout=1)' 2>/dev/null; then READY=1; break; fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo 'ad-linux-tv server exited before it became ready' >&2
    exit 1
  fi
  sleep 1
done
if (( ! READY )); then
  echo 'ad-linux-tv server did not become ready within 30 seconds' >&2
  exit 1
fi
if command -v firefox >/dev/null 2>&1; then
  if [[ ${AD_LINUX_TV_KIOSK:-0} == 1 ]]; then
    firefox --profile "$PROFILE" --kiosk http://127.0.0.1:8765/
  else
    firefox --profile "$PROFILE" --new-window http://127.0.0.1:8765/
  fi
else
  echo 'Firefox command unavailable; open http://127.0.0.1:8765/ manually' >&2
  exit 1
fi
