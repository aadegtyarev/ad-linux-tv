#!/usr/bin/env bash
set -euo pipefail
/usr/local/libexec/ad-linux-tv/has-monitor.sh || exit 0
test -x /home/ad-tv/.local/share/ad-linux-tv/run.sh || exit 0
test -r /home/ad-tv/.config/ad-linux-tv/config.yaml || exit 0
test -r /home/ad-tv/snap/firefox/common/ad-linux-tv-signed.xpi || exit 0
exec /usr/bin/systemctl --no-block start ad-linux-tv-kiosk.service

