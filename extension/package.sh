#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-"$ROOT/ad-linux-tv-unsigned.zip"}
python3 -m json.tool "$ROOT/manifest.json" >/dev/null
python3 - <<'PY' "$ROOT/manifest.json"
import json, sys
m=json.load(open(sys.argv[1], encoding="utf-8"))
assert m["manifest_version"] == 3
assert m["background"].get("scripts") == ["tabs.js", "bridge.js", "background.js"]
assert "service_worker" not in m["background"]
version = tuple(map(int, m["browser_specific_settings"]["gecko"]["strict_min_version"].split(".")))
assert version >= (157, 0)
assert m["browser_specific_settings"]["gecko"]["data_collection_permissions"]["required"] == ["none"]
PY
(cd "$ROOT" && zip -q -j "$OUT" manifest.json tabs.js bridge.js background.js launcher.js)
sha256sum "$OUT"
echo 'Unsigned development archive only; Firefox stable installation requires AMO-signed XPI.' >&2
