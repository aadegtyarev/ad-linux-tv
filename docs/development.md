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

- `src/ad_linux_tv/`: Python server, configuration/auth, DNS-SD identity, TV audio/timers, WebSocket adapter, MPRIS cache and bounded HTML-media report/queue adapter.
- `src/ad_linux_tv/static/`: TV launcher and phone remote. `remote.js` wires screens; focused modules handle transport, settings, sound levels, pointer acceleration and media panel.
- `extension/`: Firefox MV3 bridge, owned service tabs, durable command ledger, page-player volume, fixed HTML-media functions and tab-filtered declarative view policy.
- `android/`: Kotlin shell, real WebView profiles, bounded NSD, explicit selection and optional media-only foreground connection. See [Android build](android.md#build-and-check).
- `ops/beelink/`: target-specific TV account, labwc, keyboard, overlays and systemd integration.
- `tests/`: Python server/operation tests and Node tests for the browser code.

The phone loads its page and creates a session over HTTP, then uses one authenticated WebSocket for live requests. The Firefox bridge polls the local server for queued commands, executes them at most once and acknowledges the outcome. Playback panel controls prefer Firefox's Linux MPRIS session. Installed signed0.4.1 can provide a fresh, capability-gated owned-HTML fallback; legacy signed0.3.2 cannot. Accepted tile opening is not acceptance of HTML timing/playback/seek. MPRIS does not need the new extension. The retained native notification implementation is separate from the web input socket, uses the selected profile and never retries uncertain commands. The last delivered native0.2.4 exposes notification controls through explicit settings opt-in, off by default, with no automatic permission request. S02 native0.2.5/code6 and About metadata are source-integrated/frozen only, not deployed or delivered. Service-specific focus and DRM behavior are outside the bridge's control.

Power verification must mock the fixed shutdown actuator; never start/enable its unit as a test. Display sleep shares asynchronous pause/silence/generation guards with the timer; output-on and CEC request acceptance are not physical TV observations. Historical215Python/94Node release checks and offline geometry belong to the [delivery record](verification/remote-power-2026-10-26.md), not a fresh physical acceptance run. Later frozen S02 gates are separate source-only evidence.

Run the Android unit/lint/assemble commands from its guide when changing native code. Fake NSD/Looper and DOM tests are not device/site proof. Synthetic offline renders must use isolated dev profiles/data, never an installed TV browser profile or private movie capture. The [bridge protocol](bridge-protocol.md) describes freshness, source identity, uncertain claims and reusable capabilities.

`AGENTS.md` and `docs/contracts/` describe the feature-contract workflow and observable UI/operation boundaries. These are maintainer documents; users can start with the README and usage guide. Run the full CI checks when changing shared routes or packaging. Do not commit private config, credentials, signed XPI secrets or a Firefox profile.
