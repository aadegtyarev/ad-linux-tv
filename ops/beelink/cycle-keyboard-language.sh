#!/usr/bin/env bash
set -euo pipefail

schema=org.gnome.desktop.input-sources
current=$(gsettings get "$schema" current)
case "$current" in
  "uint32 0") next=1 ;;
  "uint32 1") next=0 ;;
  *) next=0 ;;
esac
gsettings set "$schema" current "$next"
