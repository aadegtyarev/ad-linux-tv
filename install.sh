#!/usr/bin/env bash
set -euo pipefail
MODE=
AUTOSTART=1
for arg in "$@"; do
  case "$arg" in
    --dry-run|--install)
      if [[ -n "$MODE" && "$MODE" != "$arg" ]]; then
        echo 'Choose only one mode: --dry-run or --install' >&2
        exit 2
      fi
      MODE="$arg"
      ;;
    --no-autostart) AUTOSTART=0 ;;
    *) echo 'usage: install.sh [--dry-run|--install] [--no-autostart]' >&2; exit 2 ;;
  esac
done
MODE=${MODE:---dry-run}
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="$HOME/.config/ad-linux-tv/config.yaml"
AUTO="$HOME/.config/autostart/ad-linux-tv.desktop"
FIREFOX_DATA="$HOME/snap/firefox/common"
PROFILE="$FIREFOX_DATA/ad-linux-tv-profile"
XPI="$FIREFOX_DATA/ad-linux-tv-signed.xpi"
for path in "$DATA" "$DATA/venv" "$PROFILE" "$CONFIG"; do
  printf '%s %s\n' "$MODE" "$path"
done
if (( AUTOSTART )); then
  printf '%s %s\n' "$MODE" "$AUTO"
elif [[ -e "$AUTO" ]]; then
  printf '%s remove %s\n' "$MODE" "$AUTO"
fi
if [[ -n "${AD_LINUX_TV_XPI_URL:-}" || -n "${AD_LINUX_TV_XPI_SHA256:-}" ]]; then
  printf '%s %s\n' "$MODE" "$XPI"
fi
[[ "$MODE" == --dry-run ]] && exit 0
ROOT=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$DATA" "$PROFILE" "$(dirname "$CONFIG")"
cp -R "$ROOT/src" "$ROOT/extension" "$DATA/"
cp "$ROOT/pyproject.toml" "$ROOT/run.sh" "$DATA/"
python3 -m venv "$DATA/venv"
"$DATA/venv/bin/pip" install "$DATA"
if [[ ! -e "$CONFIG" ]]; then
  "$DATA/venv/bin/ad-linux-tv" init-config --config "$CONFIG"
  "$DATA/venv/bin/python" -c 'from pathlib import Path; from ad_linux_tv.settings import write_proxy_profile; write_proxy_profile(Path.home() / "snap/firefox/common/ad-linux-tv-profile/user.js", {"mode": "system"})'
fi
if (( AUTOSTART )); then
  mkdir -p "$(dirname "$AUTO")"
  cat > "$AUTO" <<EOF
[Desktop Entry]
Type=Application
Name=ad-linux-tv
Exec="$DATA/run.sh" "$CONFIG"
X-GNOME-Autostart-enabled=true
EOF
else
  rm -f "$AUTO"
fi
chmod 600 "$CONFIG"
if [[ -n "${AD_LINUX_TV_XPI_URL:-}" || -n "${AD_LINUX_TV_XPI_SHA256:-}" ]]; then
  [[ -n "${AD_LINUX_TV_XPI_URL:-}" && -n "${AD_LINUX_TV_XPI_SHA256:-}" ]] || { echo 'Both XPI URL and SHA256 are required' >&2; exit 1; }
  [[ "$AD_LINUX_TV_XPI_SHA256" =~ ^[[:xdigit:]]{64}$ ]] || { echo 'Invalid XPI SHA256 format' >&2; exit 1; }
  command -v curl >/dev/null || { echo 'curl required to download signed XPI' >&2; exit 1; }
  tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
  curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 "$AD_LINUX_TV_XPI_URL" -o "$tmp"
  printf '%s  %s\n' "$AD_LINUX_TV_XPI_SHA256" "$tmp" | sha256sum --check --status || { echo 'XPI SHA256 mismatch' >&2; exit 1; }
  cp "$tmp" "$XPI"
  command -v firefox >/dev/null || { echo 'Firefox unavailable; verified XPI was saved for manual installation' >&2; exit 1; }
  firefox --profile "$PROFILE" "$XPI"
else
  echo 'Signed XPI unavailable: release gate. Set AD_LINUX_TV_XPI_URL and AD_LINUX_TV_XPI_SHA256 after AMO signing.'
fi
