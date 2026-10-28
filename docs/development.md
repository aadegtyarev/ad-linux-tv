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

Run `./install.sh --dry-run` and `./uninstall.sh --dry-run` after installer changes. For Android, see [Android build](android.md#build-and-check).

## Code map

| Path | Contents |
|---|---|
| `src/ad_linux_tv/` | Python server: config, auth, discovery, audio, timer, power, WebSocket, MPRIS, bridge queue |
| `src/ad_linux_tv/static/` | TV launcher and phone remote (`remote.js` plus focused modules) |
| `extension/` | Firefox MV3 bridge ([protocol](bridge-protocol.md)) |
| `android/` | Kotlin WebView shell |
| `ops/kiosk/` | [Dedicated TV computer](kiosk.md): setup, deploy, Firefox profile, labwc, overlays, systemd |
| `tests/` | Python and Node tests |
| `docs/contracts/` | Feature contracts (see `AGENTS.md`) |

## How it fits together

The phone loads the remote over HTTP, gets a session cookie and sends commands over one authenticated WebSocket. The Firefox bridge polls the server for queued commands. Playback controls prefer Firefox's MPRIS session, with the bridge's HTML media as fallback.

## Rules

- Tests must mock the shutdown actuator; never start the poweroff unit.
- Use isolated dev Firefox profiles, never an installed TV profile.
- `extension/package.sh /tmp/bridge-unsigned.zip` builds an unsigned bridge for testing; stable Firefox needs an AMO-signed XPI.
- Do not commit private config, credentials, signed XPIs or Firefox profiles.
- Fake-DOM, fake-network and unit tests are not proof of real phone or site behaviour; record physical checks in [docs/verification](verification/).
