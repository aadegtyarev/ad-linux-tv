# Shared site settings and version information — 2026-10-27

The combined S01/S02 server and web UI package was installed on the own Beelink. Only `ad-linux-tv-kiosk.service` was stopped and started, after an operator warning. The computer was not rebooted. This record separates installed-code/read-only verification from physical phone, TV and site acceptance.

## Installed payload

| Item | Verified identity |
|---|---|
| Server distribution | `ad-linux-tv` 0.1.0 |
| Runtime build fingerprint | `03c898b93f8fee48` |
| Complete wheel SHA-256 | `71029fad9df1547b15a1f96ea3a68f9c546d6cea1a891a65bb3bd439a5a95fa8` |
| Reviewed app-only updater SHA-256 | `6cea2cc214a4c1825141c1fa360ae328be1342922ecb016c2919975981de622c` |
| Pinned release manifest SHA-256 | `91459260889a8421d8f1e0e9ff296257273777c75ee2077ff48485393c0aaf54` |
| Firefox extension | Normally signed 0.4.1, unchanged |
| Android | Last delivered 0.2.4; 0.2.5/code6 remains a local, undelivered candidate |

The wheel has exactly53 members, including all47 actual runtime files. It includes the S01 backend/form, S02 server/About information and complete-string wrapping correction. The old `49a8395b77ea486a` / `f78777a2…` wheel predates these corrections and is not a deployment input.

## Behavior included

Phone and TV share one compact «Вид сайтов» form. «Все сайты» edits the common view; choosing a configured site edits its override. Without an override it inherits the common value; «Как для всех сайтов» removes only that override. Common omission/reset means desktop125; legacy explicitly specified mode-only views retain desktop100/mobile200 zoom defaults.

Saving does not navigate, reload video or restart the kiosk. Server readiness determines whether the user must explicitly restart before reopening a service. Matching acknowledgements immediately update the restart action and truthful saved/apply feedback. Read/write/edit/scope fences prevent stale responses from replacing newer drafts or acknowledged view state.

The collapsed «О программе» group displays server version/build through ordinary settings synchronization. Native app information is shown only when a supported Android shell supplies its fixed public constant. Browser-only pages hide that row; missing metadata is unknown, not guessed. Values wrap without truncation. These fields are not authentication and add no polling or callable native bridge.

See [configuration](../configuration.md) and [usage](../usage.md).

## Gates and deployment boundary

Canonical source gates passed:232 Python tests,171 Node tests, Ruff/format for65 Python files, syntax/JSON/shell/diff and maintained documentation checks. Synthetic layout covered58 states, not physical devices.

The initial updater was not used: it retained old payload/extension assumptions. Its replacement was corrected for the actual Python3.14.4 target, separate readable root staging, execution uncertainty and complete installed metadata/CLI verification. Independent review passed on the exact updater above:37 normal and37 optimized tests, actual-method old-RED/new-GREEN timeout and metadata probes, separate metadata corruption and service-state ambiguity probes. A timed-out descendant is **not** claimed killed: uncertain writes produce manual recovery, never an automatic restore/start/retry.

The parent copied exactly the updater, wheel and pinned manifest once into a fresh root-owned stage, then checked the **copied** hashes before execution. Staging used `/var/lib/ad-linux-tv-staging`, root:TV-group0750/files0640. Existing private `/var/lib/ad-linux-tv`, root:root0700, was not broadened. TV-user runuser/pip read-only qualification and available capacity were checked before installation. No updater code was executed from the writable checkout.

The transaction completed with `status: deployed` and exit0. Fresh package/metadata/CLI/mirror backup and receipts remain private under `/var/lib/ad-linux-tv/settings-app-transaction`. This permanent transaction marker is not an invitation to rerun the helper; future maintenance must establish actual state before archiving it. Do not restore a historical config/profile/XPI or delete a marker merely to retry an uncertain operation.

## Read-only installed checks

- Own kiosk active/running under `ad-tv`; the port8765 Python listener is a descendant of its fresh main PID, with the expected UID and interpreter. Its user-session cgroup differs from the literal system-unit cgroup; ancestry establishes attribution.
- All47 installed runtime files and the owned source mirror match the reviewed payload. Actual served settings JavaScript and CSS match source.
- `/health` returned200. Settings returned server `0.1.0` / `03c898b93f8fee48`, six service views, common desktop125, no individual overrides, profile ready and no restart required.
- Reviewed preservation comparisons passed for private config/auth/PIN/session state, optional autostart and preferences. The pinned wrapper and signed0.4.1 bytes remain unchanged; the browser profile was not replaced. Cookie/history/form databases were not inspected or copied.
- The whole-host poweroff unit remained inactive. An unauthenticated `/api/power` read returned403. No power, input or media action was used as a test.

Frozen release/evidence: `.cache/releases/settings-versions-20261027/{release.json,deployment/}`. Private transaction files remain0600 beneath the unchanged0700 directory. No Git/index/config write, commit, push or public release was performed.

## Remaining acceptance and separate work

Physical phone/TV rendering, arrows/OK/Back, settings save/reset/reopen and site/DRM behavior are not established by these checks. The [site-view](../contracts/features/site-view-overrides.md) and [version-info](../contracts/features/remote-version-info.md) feature contracts remain for those delivery/acceptance boundaries. Android0.2.5/code6 was not sent or installed; exact phone-installed version is still unverified.

APK download through the existing TV QR is a separate queued feature, not part of this payload. KION notification behavior, audio policy, actual video fullscreen/reflection and contextual Android Back were not changed. Real playback/seek, display sleep/wake, CEC and whole-host shutdown were not tested.
