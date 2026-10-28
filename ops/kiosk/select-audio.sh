#!/usr/bin/env bash
set -euo pipefail
# PipeWire's PulseAudio interface can start after labwc. Apply the output saved in
# config.yaml when it is connected, otherwise the first connected HDMI output.
PYTHON=${AD_LINUX_TV_PYTHON:-/home/ad-tv/.local/share/ad-linux-tv/venv/bin/python}
CONFIG=${AD_LINUX_TV_CONFIG:-/home/ad-tv/.config/ad-linux-tv/config.yaml}
# Read once from the pre-config preference file of older installations.
LEGACY=${AD_LINUX_TV_AUDIO_FILE:-/home/ad-tv/.config/ad-linux-tv/audio-output.txt}
for _ in {1..20}; do
  status=0
  "$PYTHON" -m ad_linux_tv.audio select "$CONFIG" "$LEGACY" || status=$?
  [[ $status -eq 3 ]] || exit 0
  sleep 0.5
done
exit 0
