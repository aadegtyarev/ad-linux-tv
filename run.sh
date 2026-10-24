#!/usr/bin/env bash
set -euo pipefail
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="${1:-$HOME/.config/ad-linux-tv/config.yaml}"
PROFILE="$DATA/firefox-profile"
"$DATA/venv/bin/ad-linux-tv" --config "$CONFIG" &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
for _ in {1..30}; do
  if "$DATA/venv/bin/python" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8765/health",timeout=1)' 2>/dev/null; then break; fi
  sleep 1
done
if command -v firefox >/dev/null 2>&1; then
  firefox --profile "$PROFILE" --new-window http://127.0.0.1:8765/
  wait "$SERVER"
else
  echo 'Firefox command unavailable; open http://127.0.0.1:8765/ manually' >&2
  wait "$SERVER"
fi
