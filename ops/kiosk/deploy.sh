#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--install) ;;
  *) echo 'usage: deploy.sh [--dry-run|--install]' >&2; exit 2 ;;
esac
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TV_HOME=/home/ad-tv

if [[ "$MODE" == --dry-run ]]; then
  echo "Source checkout preserved: $ROOT"
  HOME="$TV_HOME" "$ROOT/install.sh" --dry-run --no-autostart
  exit 0
fi

if (( EUID != 0 )); then echo 'Run with sudo for --install.' >&2; exit 1; fi
if ! id -u ad-tv >/dev/null 2>&1; then
  echo 'Run ops/kiosk/setup.sh --install first.' >&2
  exit 1
fi
stage=$(mktemp -d /tmp/ad-linux-tv-stage.XXXXXX)
trap 'rm -rf "$stage"' EXIT
cp -R "$ROOT/src" "$ROOT/extension" "$ROOT/install.sh" "$ROOT/run.sh" "$ROOT/pyproject.toml" "$stage/"
chown -R ad-tv:ad-tv "$stage"
runuser -u ad-tv -- env HOME="$TV_HOME" "$stage/install.sh" --install --no-autostart
"$ROOT/ops/kiosk/configure-firefox.sh" --configure
echo 'Application installed for ad-tv. Source checkout was not changed.'
