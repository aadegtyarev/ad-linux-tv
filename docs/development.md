# Development

Use Python 3.12+ and Node.js 20+ from the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
node --test tests/*.test.js
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Run `./install.sh --dry-run` and `./uninstall.sh --dry-run` before changing installer behavior. `extension/package.sh /tmp/ad-linux-tv-unsigned.zip` validates a development bridge archive; Firefox stable still requires an AMO-signed XPI.

## Code map

- `src/ad_linux_tv/`: Python server, configuration, authentication, TV audio, timers, WebSocket adapter and MPRIS media control.
- `src/ad_linux_tv/static/`: TV launcher and phone remote. `remote.js` wires screens; focused modules handle transport, settings, sound levels, pointer acceleration and media panel.
- `extension/`: Firefox MV3 bridge, managed service tabs, command ledger and page-player volume control.
- `ops/beelink/`: target-specific TV account, labwc, keyboard, overlays and systemd integration.
- `tests/`: Python server/operation tests and Node tests for the browser code.

The phone loads its page and creates a session over HTTP, then uses one authenticated WebSocket for live requests. The Firefox bridge polls the local server for queued commands, executes them at most once and acknowledges the outcome. Playback panel controls use Firefox's Linux MPRIS session through the Python server; they do not need a new signed extension. Service-specific focus and DRM behavior are outside the bridge's control.

`AGENTS.md` and `docs/contracts/` describe the feature-contract workflow and observable UI/operation boundaries. These are maintainer documents; users can start with the README and usage guide. Run the full CI checks when changing shared routes or packaging. Do not commit private config, credentials, signed XPI secrets or a Firefox profile.
