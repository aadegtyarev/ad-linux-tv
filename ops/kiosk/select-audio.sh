#!/usr/bin/env bash
set -euo pipefail
# PipeWire's PulseAudio interface can start after labwc. Honor the TV user's
# selected output when connected, otherwise prefer HDMI over the analog default.
preference=${AD_LINUX_TV_AUDIO_FILE:-/home/ad-tv/.config/ad-linux-tv/audio-output.txt}
preferred=
if [[ -r $preference ]]; then IFS= read -r preferred < "$preference" || true; fi
for _ in {1..20}; do
  outputs=$(pactl list short sinks 2>/dev/null) || true
  sink=
  if [[ -n $preferred ]]; then
    sink=$(awk -v target="$preferred" '$2 == target {print $2; exit}' <<< "${outputs:-}")
  fi
  if [[ -z $sink ]]; then
    sink=$(awk '$2 ~ /\.hdmi-stereo/ {print $2; exit}' <<< "${outputs:-}")
  fi
  if [[ -n ${sink:-} ]]; then
    current=$(pactl info 2>/dev/null | sed -n 's/^Default Sink: //p') || true
    if [[ $current != "$sink" ]]; then
      pactl set-default-sink "$sink"
    fi
    if [[ ! -f $preference ]]; then
      pactl set-sink-volume "$sink" 100%
      pactl set-sink-mute "$sink" 0
    fi
    exit 0
  fi
  if [[ -n ${outputs:-} ]]; then exit 0; fi
  sleep 0.5
done
# Some displays have no speakers, and the analog output remains available.
exit 0
