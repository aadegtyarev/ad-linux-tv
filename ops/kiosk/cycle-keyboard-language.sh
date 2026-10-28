#!/usr/bin/env bash
set -euo pipefail

schema=org.gnome.desktop.input-sources
sources=$(gsettings get "$schema" sources)
case "$sources" in
  "[('xkb', 'us'), ('xkb', 'ru')]") next="[('xkb', 'ru'), ('xkb', 'us')]" ;;
  "[('xkb', 'ru'), ('xkb', 'us')]") next="[('xkb', 'us'), ('xkb', 'ru')]" ;;
  *) echo "Unexpected TV keyboard sources: $sources" >&2; exit 1 ;;
esac
gsettings set "$schema" sources "$next"
gsettings set "$schema" current 0
