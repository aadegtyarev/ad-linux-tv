# Signed bridge 0.4.1: tile-open zoom repair

Status: repair installed through normal Firefox signing/confirmation and accepted by the operator on 2026-10-26. This record covers service-tile opening, not service playback. Documentation reconciliation used frozen receipts offline; it made no new target requests or runtime changes.

## Failure and bounded repair

On Firefox 158.0.1, a real Browser-tile click failed with `operation` in signed 0.4.0, both with mobile200 and desktop100. Native `getZoomSettings` already returned automatic/per-tab with `defaultZoomFactor: 1`. Firefox hydrated the setter's omitted `defaultZoomFactor` to `null` and rejected `setZoomSettings` with `Unsupported zoom settings`. Native getter → setZoom(2) → getZoom returned 2. The profile scope was already correct; the mobile header's window filter was not the cause.

Source `extension/view_policy.js` in 0.4.1 now:

1. Requires `getZoomSettings` for view support and bounds its read to 1.5 seconds.
2. Rechecks ownership after the read and accepts only automatic/per-tab settings.
3. Calls `setZoom`, never `setZoomSettings`; getter failure or incompatible scope prevents the write.

The existing tab/window-filtered mobile header policy, ownership/generation fencing and before-navigation setup remain. No unmanaged-tab or per-origin fallback was added. Dispatched write timeouts remain uncertain and are never automatically replayed. See the durable [TV launcher contract](../contracts/surfaces/tv-launcher.md#installed-bridge-capabilities-and-tile-open-repair), [configuration contract](../contracts/surfaces/configuration.md) and [bridge protocol](../bridge-protocol.md).

## Source, regression and review evidence

- `tests/view_policy.test.js` models Firefox schema hydration/equality. The old setter fails with hydrated null; the repaired getter/write path passes. Coverage includes incompatible scope, getter rejection, ownership retirement, header isolation, legacy Home and setup before navigation.
- Focused suite: **7 passed, 0 failed**; manifest JSON validation passed.
- Canonical full Node suite: **95 passed, 0 failed**, exit 0, no skipped/cancelled/todo. The isolated fix snapshot lacked unrelated static dependencies, so its attempted full run was not the successful canonical full-suite result.
- Independent bounded code/package review: **PASS**, no blocking P1 finding. Review covered the three changed source/test files, unchanged ID/permissions, runtime member list and unsigned package. It was not a live-site review.

Frozen evidence is held outside shipped source under `/home/adegtyarev/.cache/ad-linux-tv/incident-control/`: `zoom-fix/.cache/handoff.md`, `zoom-fix/.cache/review.md`, `node-full.log` and `node-full.exit`. These stage-specific records predate signing/installation; their then-pending delivery statements do not describe the final state below.

## Signed payload and actual tile acceptance

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `ad-linux-tv-bridge-0.4.1-unsigned.zip` | 13,805 | `d62230812692cea30c104b15d2fbf5096c965628f935c3b99941dadb7545bc1e` |
| `a73bc1b7f03b4274b512-0.4.1.xpi` | 22,058 | `5397ff8bab6b3ce778cedff3cef523ff6c9889d0a328483ea820dbec48a71264` |

The signed payload's JavaScript is byte-equal to the reviewed unsigned runtime; the manifest is semantically equal after AMO reformatting. RSA/COSE signature entries are present. ID and permissions are unchanged from 0.4.0. The installed signed payload's digest matches, and normal Firefox installation was confirmed. No signature bypass, enterprise-policy workaround or browser replacement was used.

Final signed-payload and installed-digest checks plus explicit operator confirmation are recorded in frozen `release-041.json`. Frozen `acceptance-041.json` records an actual click on the served Browser tile, not merely a native API test or synthetic queue submission:

- A new command was enqueued with **202 accepted**.
- Afterwards the bridge was online, pending commands were 0 and last failure was null.
- Fresh `html_media_v1` and `tab_view_v1` were present; `view_pending` was false.
- The operator explicitly confirmed «работает».

202 and capability reports alone would not prove the tile opened. The actual UI action and operator confirmation complete this repair's acceptance; they do not establish playback, seek or physical fullscreen behavior.

## State and remaining limits

- Installed: signed bridge 0.4.1 alongside the previously deployed power/grid backend. Frozen `common-desktop125-live.json` records explicit common desktop125 across all six sites, no individual Kinopoisk override, only view settings changed and no video reload. This is not evidence that the installed backend derives desktop125 when the setting is absent.
- Source only: backend omission/reset default desktop125 is grounded in `src/ad_linux_tv/view_config.py` and `tests/test_common_view.py`. The S01 per-site UI is held/unmerged; this repair does not deliver it.
- Native/server delivery is separate: native 0.2.4 is the last delivered app, not a verified installed-version claim. S02 app 0.2.5 and server build `49a8395b77ea486a` are integrated/frozen source, not deployed or sent. Existing S02 metadata docs remain candidate documentation.
- The signed 0.3.2 local HTML-audio 37% test on 2026-10-25 remains historical. It is not 0.4.1 service acceptance.
- Null/unavailable media, KION notification-shade behavior, site audio/advertising, protected/live/restricted players, DRM, physical power, fullscreen and horizontal video flip are not fixed or accepted by this zoom repair. No new sleep/shutdown/seek/playback/CEC test was performed for it.
- Capability freshness, version/build and unknown-version displays are not authentication. LAN HTTP remains unencrypted; use only a trusted private network. Normal AMO signing and Firefox confirmation remain required. No private configuration, profile preferences or autostart changes were made by the zoom repair or this documentation pass.
