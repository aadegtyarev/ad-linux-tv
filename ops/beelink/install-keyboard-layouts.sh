#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--install) ;;
  *) echo 'usage: install-keyboard-layouts.sh [--dry-run|--install]' >&2; exit 2 ;;
esac
TARGET=/home/ad-tv/.local/share/squeekboard/keyboards
printf '%s labeled English/Russian keyboard layouts in %s\n' "$MODE" "$TARGET"
[[ "$MODE" == --dry-run ]] && exit 0
(( EUID == 0 )) || { echo 'Run with sudo for --install.' >&2; exit 1; }

# Source: Debian squeekboard 1.43.1-1, GPL-3+. Labels replace SVG icons,
# and the language key emits F12 for the dedicated labwc cycle binding.
declare -A digest=(
  [us]=bf985df2f4136e3050ce473c072d8147a70f7c0744ed5bd1478c6030b0e03159
  [us_wide]=376ae74706f26a2f098ad2d5bd00630d7959ba86d6ef04e57ee0e8662309d2e4
  [ru]=c8e37e0fe582ef9bb6dca7949c87e6c6d88394ed67f2cd5cbef259b0fc625513
  [ru_wide]=83cb365f0abf5c6bdc6c83c0a818c17b6002eff8175ca4d096bc31064e070179
)
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.local /home/ad-tv/.local/share
install -d -o ad-tv -g ad-tv -m 755 /home/ad-tv/.local/share/squeekboard "$TARGET"
for name in us us_wide ru ru_wide; do
  original=$(mktemp)
  modified=$(mktemp)
  trap 'rm -f "$original" "$modified"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
    "https://sources.debian.org/data/main/s/squeekboard/1.43.1-1/data/keyboards/$name.yaml" -o "$original"
  printf '%s  %s\n' "${digest[$name]}" "$original" | sha256sum --check --status || {
    echo "Layout checksum mismatch: $name" >&2; exit 1;
  }
  case "$name" in
    us*) language_label='EN→RU' ;;
    ru*) language_label='RU→EN' ;;
  esac
  sed -e 's/icon: "key-shift"/label: "⇧"/' \
      -e 's/icon: "edit-clear-symbolic"/label: "⌫"/' \
      -e 's/icon: "keyboard-mode-symbolic"/label: "Язык"/' \
      -e 's/icon: "key-enter"/label: "↵"/' \
      -e 's/action: "show_prefs"/keysym: "F12"/' \
      -e '/^    preferences:/,/^    show_numbers:/ s/outline: "special[^"]*"/outline: "change-view-2"/' \
      -e "s/label: \"Язык\"/label: \"$language_label\"/" \
      "$original" > "$modified"
  install -o ad-tv -g ad-tv -m 644 "$modified" "$TARGET/$name.yaml"
  rm -f "$original" "$modified"
  trap - EXIT
done
echo 'Keyboard labels installed; restart the TV session to apply them.'
