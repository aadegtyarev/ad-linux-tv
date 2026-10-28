# Android remote checkpoint — 26 October 2026

This checkpoint distinguishes reviewed source, built artifacts and the Beelink rollout from physical-phone and site acceptance. It describes the uncommitted implementation worktree; it is not a published release or a Firefox-signing record.

## What passed

| Check | Evidence and boundary |
| --- | --- |
| Python | 184 tests on the private Python 3.12 development environment; Ruff and format checks pass. |
| JavaScript | 79 Node tests pass, including identity-bound pause/seek state, input retirement, capability gating and owned-tab primitives. These are synthetic tests, not Firefox DOM/site proof. |
| Android | 18 JVM tests: 12 model/policy cases and 6 Robolectric/fake-NSD cases. `lintDebug` and `assembleDebug` pass. No physical phone was used. |
| APK | Android build-tools `apksigner verify` succeeds. This is a developer/debug signature, not a production signing or installation qualification. |
| Documentation | Maintained source/docs snapshot has clean links and Mermaid checks. Ignored external MDN research downloads are excluded; an earlier unfiltered check reported their `/en-US` links as missing project files. |
| Source security scan | Redacted, non-Git-history gitleaks scan of the maintained source snapshot reports no leaks. Installed configuration and browser data were not scanned. |
| Synthetic layout | Offline headless Chromium, 360 px viewport, root fonts 16/24/32 px: no horizontal overflow; 17 visible targets are at least 48×48 px; Главная/Таймер/Назад/Выбрать fit their buttons on one line. This is not native Android or GTK rendering proof. |

Independent read-only reviews covered discovery cleanup, managed HTML media, magnifier/view configuration, Android/client/docs and the bounded rollout script. The final client review found that a missing observed media identity could confirm an identity-bound pending action. The guard and pause/seek regression were fixed and re-reviewed before deployment.

## Built artifacts

Artifacts and receipts are local under `.cache/artifacts/`; the directory is ignored and not a publication channel.

| Artifact | Size | SHA256 |
| --- | ---: | --- |
| `ad-linux-tv-remote-0.2.0-debug.apk` | 8,889,388 bytes | `30a50f5ecaf143b6803c188fae2897909fc10fe405582b352c0374cc47b71502` |
| `ad-linux-tv-bridge-0.4.0-unsigned.zip` | 13,779 bytes | `067b828edc04d5f8f699bb6634acdaa8cb659bf6dba480ed0e75c6c1de8938cb` |
| `ad_linux_tv-0.1.0-py3-none-any.whl` | 113,396 bytes | `31c0695dfd8c9fa2dcfb90d4324a51ba70b118f664c53da112f5840fe7cbdccd` |

The wheel was built in a private environment with setuptools 75.8.2 and wheel 0.45.1. The APK uses the [documented Android toolchain](../android.md#build-and-check). Source digests are retained locally alongside the artifact receipt.

## Beelink rollout actually verified

The operator authorized updating and restarting the owned media-center service. The rollout stopped and started only `ad-linux-tv-kiosk.service` as `ad-tv`, preserved a root-only rollback snapshot, installed the reviewed wheel in the existing application venv and updated the owned timer/compositor helpers. It did not run the general setup/installer or recreate the venv. Runtime additions were pinned to zeroconf 0.151.5 and ifaddr 0.2.0; `pip check` passed.

The existing runtime is Python **3.14.4**, not the development test interpreter. The installed application payload was SHA-checked against reviewed source. Post-restart, read-only checks confirmed:

- The owned service is active; `/health` sees the actual installed bridge heartbeat and no pending commands.
- `/api/device` matches the persisted configuration and reports discovery state `announcing`. This verifies the local publisher state, **not phone reception of multicast**.
- `/remote` serves the expected page and CSP without creating an authorization cookie on that GET.
- Authorization configuration, existing discovery identity where present, unrelated preferences and Plasma autostart contents are preserved.
- The installed signed Firefox bridge **0.3.2** is byte-for-byte unchanged. New bridge capabilities remain absent.

The rollback snapshot is root-private under `/var/lib/ad-linux-tv/`; its exact path and nonsecret results are in the local `.cache/deploy/receipt.json`. It contains private configuration: never publish or attach it. Hermes/voice services, unrelated services, router/firewall settings and signing accounts were not changed. The deployment did not inspect or edit cookie/history/form stores; ordinary browser runtime writes were not measured. No live input, playback, seek, timer-expiry or private screenshot test was performed.

## Still separate acceptance

The unsigned 0.4.0 bridge must be signed and installed through the normal Firefox process before testing managed-HTML timing/seek or mobile view on actual sites. It was **not installed** during this rollout. Existing MPRIS behavior remains available; an ordered input socket can still be blocked by a synchronous MPRIS command.

Use the [target checklist](../target-checklist.md) for actual NSD reception, WebView profile/cookie isolation, phone notifications/lifecycle/camera/input, Firefox mobile/DRM/media behavior and TV panel readability/focus/expiry. The next step is not to infer these from unit tests or the publisher status.

Discovery and UUID preflight remain correlation safeguards, not peer authentication. Trusted-LAN HTTP is unencrypted and vulnerable to LAN impersonation and cookie interception. See [Android boundaries](../android.md) and the [bridge protocol](../bridge-protocol.md).

## Later phone feedback and corrective layout

The operator rejected the larger layout after looking at it on a phone. Earlier static-fixture checks did not establish a good real-phone experience: they missed feedback paragraphs entering layout flow and the lost compact composition. The approved correction restores the pre-redesign design/proportions and removes service launching, website-address entry and duplicated browser-command banks from Settings. Discovery, authorization and command safeguards remain unchanged.

The corrective gate passes 184 Python and 82 Node tests. Android 0.2.1 passes 18 JVM tests, lint, assembly and APK signature verification; its certificate matches 0.2.0. Its native header is one 48 dp row with no separate notification activation button or automatic notification start. The new APK is needed for that native change; reloading the server page updates only the web UI.

Five offline synthetic fixtures cover media present/absent, 320/360 px widths, a 600 px short viewport and an enlarged root font. Success, pending and error feedback leave the measured primary rectangles identical, without overlap or horizontal overflow; visible touch targets are at least 44 px. These tests do not prove physical Android font scaling, runtime input or phone usability. The CSS intentionally returns to mostly fixed-size compact typography rather than claiming all text follows system scaling.

The corrective static assets were deployed into the owned installed/source directories with private rollback copies and HTTP body-hash checks. The kiosk PID stayed unchanged: no service restart, config/profile/XPI writes or playback/input/seek/expiry actions were needed. Fresh read-only checks still see the actual bridge heartbeat and local discovery publisher. The earlier independent correction review initially confused baseline HTML with current HTML; it explicitly retracted that finding after reading the actual source and approved the static-only update.

The new APK is `.cache/restoration/artifacts/ad-linux-tv-remote-0.2.1-debug.apk`, 8,776,182 bytes, SHA256 `710294f637a73593eae39dff906a188f5fa1b0198c1f4a754acf25de28e5334b`. Both its initial handoff and the operator's subsequent explicit send request returned partial0/1; receipt is not confirmed and no automatic retry was performed. Local evidence/receipts are under `.cache/restoration/`. The next phone check must use this APK and a reloaded remote, not infer success from source tests.
