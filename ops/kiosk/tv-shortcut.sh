#!/usr/bin/env bash
# Fixed labwc actions; no key, URL or arbitrary command is accepted from input.
set -euo pipefail
case ${1:-} in
  video_panel)
    [[ $# -eq 1 ]] || exit 2
    exec /usr/bin/curl --fail --silent --show-error --max-time 3 --output /dev/null \
      -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8765' \
      -H 'X-AD-Linux-TV-Video-Panel: video-panel-v1' \
      --data '{"action":"open"}' http://127.0.0.1:8765/api/local-video-panel
    ;;
  magnifier)
    [[ $# -eq 1 ]] || exit 2
    exec /usr/bin/curl --fail --silent --show-error --max-time 3 --output /dev/null \
      -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8765' \
      --data '{"setting":"magnifier_toggle","value":true}' http://127.0.0.1:8765/api/settings
    ;;
  fullscreen)
    [[ $# -eq 1 ]] || exit 2
    exec /usr/bin/curl --fail --silent --show-error --max-time 3 --output /dev/null \
      -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8765' \
      --data '{"command":"fullscreen"}' http://127.0.0.1:8765/api/command
    ;;
  *) exit 2 ;;
esac
