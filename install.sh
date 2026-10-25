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
ROOT=$(cd "$(dirname "$0")" && pwd)
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="$HOME/.config/ad-linux-tv/config.yaml"
AUTO="$HOME/.config/autostart/ad-linux-tv.desktop"
FIREFOX_DATA="$HOME/snap/firefox/common"
PROFILE="$FIREFOX_DATA/ad-linux-tv-profile"
XPI="$FIREFOX_DATA/ad-linux-tv-signed.xpi"
BUNDLED_XPI="$ROOT/ad-linux-tv-signed.xpi"
BUNDLED_XPI_SHA256="$ROOT/ad-linux-tv-signed.xpi.sha256"
for path in "$DATA" "$DATA/venv" "$PROFILE" "$CONFIG"; do
  printf '%s %s\n' "$MODE" "$path"
done
if (( AUTOSTART )); then
  printf '%s %s\n' "$MODE" "$AUTO"
elif [[ -e "$AUTO" ]]; then
  printf '%s remove %s\n' "$MODE" "$AUTO"
fi
if [[ -n "${AD_LINUX_TV_XPI_URL:-}" || -n "${AD_LINUX_TV_XPI_SHA256:-}" || -f "$BUNDLED_XPI" ]]; then
  printf '%s %s\n' "$MODE" "$XPI"
fi
[[ "$MODE" == --dry-run ]] && exit 0
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
elif [[ -f "$BUNDLED_XPI" ]]; then
  [[ -f "$BUNDLED_XPI_SHA256" ]] || { echo 'Bundled XPI checksum is missing' >&2; exit 1; }
  expected=$(tr -d '\r\n' < "$BUNDLED_XPI_SHA256")
  [[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] || { echo 'Invalid bundled XPI checksum' >&2; exit 1; }
  printf '%s  %s\n' "$expected" "$BUNDLED_XPI" | sha256sum --check --status || {
    echo 'Bundled XPI checksum mismatch' >&2; exit 1;
  }
  cp "$BUNDLED_XPI" "$XPI"
  command -v firefox >/dev/null || { echo 'Firefox unavailable; verified XPI was saved for manual installation' >&2; exit 1; }
  firefox --profile "$PROFILE" "$XPI"
elif [[ -f "$XPI" ]]; then
  echo 'Existing signed XPI preserved; no replacement was supplied.'
else
  echo 'No signed XPI supplied. Install an AMO-signed bridge to control Firefox.'
fi
