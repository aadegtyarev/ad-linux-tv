#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob
for path in /sys/class/drm/card*-HDMI-A-*/status /sys/class/drm/card*-DP-*/status /sys/class/drm/card*-eDP-*/status; do
  if [[ $(< "$path") == connected ]]; then
    exit 0
  fi
done
exit 1

