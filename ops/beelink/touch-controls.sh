#!/usr/bin/env bash
set -euo pipefail
case ${1:-} in
  home)
    curl --fail --silent --show-error --max-time 3 \
      -X POST -H 'Content-Type: application/json' \
      -H 'Origin: http://127.0.0.1:8765' \
      --data '{"command":"home"}' \
      http://127.0.0.1:8765/api/command >/dev/null
    ;;
  keyboard)
    visible=$(busctl --user get-property sm.puri.OSK0 /sm/puri/OSK0 sm.puri.OSK0 Visible)
    if [[ $visible == 'b true' ]]; then
      busctl --user call sm.puri.OSK0 /sm/puri/OSK0 sm.puri.OSK0 SetVisible b false >/dev/null
    else
      busctl --user call sm.puri.OSK0 /sm/puri/OSK0 sm.puri.OSK0 SetVisible b true >/dev/null
    fi
    ;;
  *) echo 'usage: touch-controls.sh home|keyboard' >&2; exit 2 ;;
esac
