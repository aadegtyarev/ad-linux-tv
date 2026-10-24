#!/usr/bin/env bash
set -euo pipefail
# PipeWire's PulseAudio interface can start after labwc; prefer an attached HDMI sink.
for _ in {1..20}; do
  sink=$(pactl list short sinks 2>/dev/null | awk '$2 ~ /\.hdmi-stereo/ {print $2; exit}') || true
  if [[ -n ${sink:-} ]]; then
    current=$(pactl info 2>/dev/null | sed -n 's/^Default Sink: //p') || true
    if [[ $current != "$sink" ]]; then
      pactl set-default-sink "$sink"
      pactl set-sink-volume "$sink" 75%
    fi
    pactl set-sink-mute "$sink" 0
    exit 0
  fi
  sleep 0.5
done
# Some displays have no speakers, and the analog output remains available.
exit 0
