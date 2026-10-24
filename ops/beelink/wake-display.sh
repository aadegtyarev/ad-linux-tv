#!/usr/bin/env bash
set -euo pipefail

# Called by swayidle after input. Keep the logical output and window layout intact.
if /usr/bin/wlopm --json 2>/dev/null | grep -q '"power-mode": "off"'; then
  /usr/bin/wlopm --on '*' || exit 1
  /usr/bin/curl --silent --show-error --max-time 2 \
    --header 'Origin: http://127.0.0.1:8765' \
    --header 'Content-Type: application/json' \
    --data '{"wake":true}' \
    http://127.0.0.1:8765/api/display-timer >/dev/null || true
fi
