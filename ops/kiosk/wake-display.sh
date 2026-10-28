#!/usr/bin/env bash
set -euo pipefail

# Called by swayidle after input. Reassert on even if output status is unavailable.
/usr/bin/wlopm --on '*' >/dev/null 2>&1 || true
/usr/bin/curl --silent --show-error --max-time 2 \
  --header 'Origin: http://127.0.0.1:8765' \
  --header 'Content-Type: application/json' \
  --data '{"wake":true}' \
  http://127.0.0.1:8765/api/display-timer >/dev/null || true
