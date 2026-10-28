# Power and compact-remote delivery — 26 October 2026

This record separates **installed delivery and offline source checks** from physical acceptance. It covers the original approved power/compact-remote work, not later queued media features. The documentation completion used retained receipts and source/tests offline; it did not contact the TV, phone, browser or APIs, run deployment helpers, or actuate input, media, sleep, CEC or shutdown.

## What was delivered

- One phone ⏻ beside Timer. Tap requests explicit display sleep/wake; a1.2-second hold opens whole-host confirmation and never also sends a tap. Motion/cancel, blur/visibility loss, auth expiry and selection retirement cancel/fence pending UI work.
- Sleep reuses bounded asynchronous managed-media pause, verified silence and generation fencing. Unknown/active audio leaves HDMI on. New timer/wake/input invalidates stale work. Wake never resumes media automatically. Output-on is not proof of a physical TV wake; the hint tells the user to use the TV remote if the picture stays dark.
- Optional CEC uses only an already available trusted `cec-ctl` and accessible kernel adapter, with a bounded directed TV wake. No packages, drivers, permissions, TV settings, standby, blind toggle, broadcast or input switch are provisioned. A request acknowledgement is not observation of TV state.
- Whole-host shutdown is kiosk-only and requires session, Origin and CSRF even on loopback. Strict prepare/shutdown DTOs use a20-second session-bound one-use challenge, bounded to64 owners. It is consumed before the fixed actuator; requested/uncertain dispatch latches without automatic retry. The warning explains that all host tasks stop and this phone cannot restart the fully stopped computer: use the physical computer button.
- Inline Text stays above the volume footer, has a44px close target and fences duplicate submission. Success clears/closes the field and phone keyboard; failed/uncertain input is not replayed. Resume/focus/pageshow/visibility reconciliation retires a stuck media GET without resending playback/seek or reviving an old selection. This is regression coverage, not proof the reported physical reopening symptom is fixed.
- Two-finger scrolling supports both axes/diagonals. Server DTOs retain vertical-only compatibility with optional `scroll_x`; both axes are strict integers within±64, not both zero. Ordered/coalesced transport and cancellation prevent accidental clicks.

## Installation and rollback evidence

Retained `.cache/power/deploy-receipt2.json` records final status `deployed`, source-payload verification and the owned kiosk active after its necessary restart. Installed reviewed wheel SHA-256:

```text
0b8caa8a0ee5350fdac292d0745dbab0a8b4ae4b780dd807833e4c8703776ce1
```

Root-private backup: `/var/lib/ad-linux-tv/power-rollback-20261026-182007`. The delivery preserved private configuration/auth, the prior absence of Plasma autostart, signed XPI, profile isolation and unrelated Firefox preferences. The receipt's signed0.4.0 field describes that installation moment; the later normally installed signed0.4.1 and operator-accepted tile-open repair are documented [separately](tile-open-zoom-2026-10-26.md). Do not downgrade that later bridge or restore an old profile merely to match this receipt.

The root-owned `ad-linux-tv-poweroff.service` has a fixed two-second grace then fixed poweroff. The only added sudoers permission is the exact command to start this unit, not arbitrary systemctl, shell, unit or argument privileges. Unit/sudoers syntax was checked without starting or enabling the shutdown unit. It remained inactive/not started. Scoped audit `.cache/lanes/power-review-followup.md` passed the deployment gate, including rejection of a stale wheel before stopping the kiosk.

Rollback is retained evidence, not an instruction to run an old cached helper now. Any restoration needs a separately approved owned-service maintenance window, artifact review and preservation of newer accepted bridge/config/auth/profile state. No restoration or deployment was performed for this documentation pass.

Earlier static grid receipt `.cache/slices/01d-grid/deploy-receipt.json` records deployment with the service PID unchanged, no restart, no config access, unchanged signed bridge, heartbeat/discovery and served-asset hashes. Its backup is `/var/lib/ad-linux-tv/ui-slice01d-rollback-20261026-181619`. It did not include input, playback, seek or timer expiry.

Historical `.cache/power/read-only-postcheck.json` records served power UI/script hash agreement and expected unauthenticated `/api/power`403. Its mobile200 settings snapshot is historical, not current configuration or a fresh probe. Before the overnight freeze the live common setting was explicitly desktop125 for all six services with no individual Kinopoisk override. Current source also derives desktop125 on omission/reset without rewriting YAML on load; that source default is not an installed-backend reset test. Per-site S01 UI remains held/unmerged. The earlier approved mobile200 default was subsequently superseded in source, not silently rewritten as though it had never existed.

## Offline checks and geometry

Historical release logs `.cache/power/pytest-release.log`, `node-release.log` and `source-final.log` record215Python tests,94Node tests and Ruff/format/shell checks passing. Host-power tests inject/mock the actuator; gesture tests cover no tap after hold, cancellation, expiry and late callbacks. Timer tests cover pause/audio failures and stale generations. These are retained runs, not tests rerun during documentation completion.

Synthetic offline geometry evidence under `.cache/slices/01d-grid/` records:

| Matrix | Result | Scope |
| --- | --- | --- |
| Source60states (`geometry60.json`) | PASS | Main/timer/menu/settings/QR, widths320/360/393, legacy/power toolbar and active/inactive timer |
| Actual staged legacy30states (`matrix-staged-geometry.json`) | PASS | Same five pages and widths, active/inactive timer |

Checks found no overlap/horizontal overflow or feedback-driven target movement. Home/Return share a48px header anchor. Active timer padding14px and a smaller timer icon keep the badge inside the button. Media feedback is a transient five-second top overlay, not a reserved layout row; remaining viewport height primarily expands the touchpad. Fixtures use synthetic content and isolated offline browser state. These measurements do not prove Android insets, physical touch, all fonts or every phone size.

## Native delivery versus S02 source-only state

The last delivered native artifact is **0.2.4**, with dark adaptive TV icon, compact header, dark picker/manual entry and existing inset/startup/notification guards. Its APK SHA-256 is:

```text
f22a9d3688499303a91584406cc91663d9335c2bd2c73b33d0f10f0456b81275
```

Public signing-certificate SHA-256:

```text
81b4092d7ce2909c2f3d1b2734020aded0e5f2c016cfeec5b3fa9907da46e05f
```

Exact installed phone version is unverified. The0.2.2 inset improvement was operator-confirmed; it is not exhaustive layout/lifecycle acceptance. Cold start attempts only the saved last ID+origin through cookie-free preflight/profile-before-load; failures open the picker without other-center fallback. An explicitly opened picker survives recreation. Notification media controls remain opt-in/default false, with explicit permission and blocked-channel handling. The operator reported shade controls working in VK; KION's cause remains unknown. No full phone/icon-mask qualification follows from artifact delivery.

S02 About/server metadata and native0.2.5/code6 are source-integrated and frozen only, **not deployed or sent**. Frozen runtime fingerprint `49a8395b77ea486a` and `.cache/releases/s02-versions/release.json` record232Python/100Node/32JVM gates plus lint/assemble. They do not establish installed-backend behavior or replace the delivered0.2.4 artifact. This documentation work does not alter S01/S02 contracts, source or frozen artifacts.

## Still unverified

- Real display sleep/wake after timer expiry, physical hold/dialog/lifecycle behavior and manual-TV-remote fallback. Prior bounded diagnosis found output already on with no exposed CEC and the operator restored the picture with the TV remote; this is not universal wake support.
- Actual full-host shutdown and physical-button restart. **Never perform shutdown merely as a development/deployment test**; it stops all host tasks and needs separate explicit destructive acceptance.
- Real playback/pause/seek, managed-HTML timing with null MPRIS timing, protected/live/ambiguous players, mobile layouts and DRM across services. Signed0.4.1 tile opening is accepted, not media qualification.
- All physical phone sizes/fonts/IME, physical WebView profile-isolation behavior, native callback/fragment lifecycle, multicast reception, icon masks and notification/background cases. VK shade success does not qualify KION or universal controls.
- Audio/ad causality: source audits of zero-level raising, unchanged muted flags and asynchronous pin races do not establish why an advertisement behaved differently. No audio fix was deployed by this documentation completion. Fullscreen-video, horizontal picture flip and new Back behavior remain unimplemented queued work, not delivered fixes.

Use the unchecked [target gates](../target-checklist.md#power-and-compact-remote-acceptance) for separately authorized physical acceptance. Durable behavior is in the [phone](../contracts/surfaces/phone-remote.md), [operation](../contracts/surfaces/kubuntu-operation.md), [launcher](../contracts/surfaces/tv-launcher.md), [configuration](../contracts/surfaces/configuration.md) and [Android](../contracts/surfaces/android-remote.md) contracts. Delivery/source verification is not whole-task physical completion; feature-contract retirement remains a parent lifecycle decision.
