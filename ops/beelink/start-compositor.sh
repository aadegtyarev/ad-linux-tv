#!/usr/bin/env bash
set -euo pipefail
: "${XDG_RUNTIME_DIR:?TV runtime directory unavailable}"
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="$HOME/.config/ad-linux-tv/config.yaml"
RUNTIME="$XDG_RUNTIME_DIR/ad-linux-tv-labwc"
SCALE=$("$DATA/venv/bin/python" -m ad_linux_tv.kiosk_config "$CONFIG" /etc/ad-linux-tv/labwc/rc.xml "$RUNTIME")
export AD_LINUX_TV_MAGNIFIER_SCALE="$SCALE"
exec /usr/bin/labwc -C "$RUNTIME" -S /usr/local/libexec/ad-linux-tv/tv-session.sh
