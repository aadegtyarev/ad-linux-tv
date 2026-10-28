# Feature contract: Android APK through the existing TV QR

Status: server delivery completed2026-10-27 under the operator's explicit request, «Запускай» and «И деплой сам». [Installed verification](../../verification/android-apk-download-2026-10-27.md): server0.1.0/build8a, real download200/full8800658/fe6 and preserved auth/runtime; curated file0444 after a separately reviewed permission-only correction. Camera/phone install/update/profile/layout acceptance remains open, so retain this contract. Original read-only reconnaissance: external `agent-lanes/s09-same-qr-download-report.md`. Timer-window repair is a separate subsequent stage.

## Goal and scenarios

Keep the existing TV/second-phone QR payload and normal web remote. A normal phone camera opens the same `/remote` URL and offers a compact Android APK link before PIN entry. It also remains visibly available on the ordinary browser's main remote after PIN-free automatic entry or session restoration—not only on the login screen or inside a menu. Keep the familiar composition and flexible pad; no oversized extra row. Browser operation must not require app installation. This visibility detail was clarified in response to the operator's PIN-disabled question.

The native scanner/preflight/selection/profile flow stays unchanged. Device-bound pages suppress the clickable APK invitation or show non-clickable guidance to use a normal camera/browser: old0.2.4 has no appInfo constant and cannot navigate/download APK paths. Never infer browser/native identity from missing or late version metadata. Binding is presentation context, not authentication. Desktop/iOS retain web use. The later approved [iOS presentation update](../../verification/ios-apk-invitation-2026-10-28.md) hides Android invitations/guidance on recognized iPhone/iPad/iPod, including desktop-style iPadOS hints; desktop/Android/unknown retain truthful Android-only/manual-install wording. This is local presentation only, not server or authentication enforcement.

A user explicitly follows the link and handles normal Android download/install prompts. No automatic download, app launch, redirect or installation; no browser-cookie/PIN/token/profile transfer to the app.

## Artifact and interfaces

Serve only the existing0.2.5/code6 binary,8,800,658bytes, SHA-256 `fe6e335f6b88a1500f1702c6a6bbb57ba0e5b91f849efc9e406a833ce563fa71`, certificate SHA-256 `81b4092d7ce2909c2f3d1b2734020aded0e5f2c016cfeec5b3fa9907da46e05f` (matches last-delivered0.2.4). Source reference `.cache/releases/settings-versions-20261027/dist/ad-linux-tv-remote-0.2.5-code6.apk`; it is not a runtime cache path. No new APK build/key access/permissions/native code or Firefox signing.

One additive fixed GET `/download/ad-linux-tv-remote-0.2.5-code6.apk`, attachment filename `ad-linux-tv-remote-0.2.5-code6.apk`. It is a public nonsecret software artifact, available without pairing/PIN only to private/loopback source with the existing exact connection-local direct numeric/local Host semantics. Ordinary link navigation needs no Origin header. Control/session/Origin/CSRF/device fences are unchanged; no CORS relaxation or authority from QR/UUID/version/hash.

Runtime reads only `/usr/local/share/ad-linux-tv/android/ad-linux-tv-remote-0.2.5-code6.apk`, curated and atomically published by the parent, root-owned read-only regular single-link file beneath trusted non-writable/non-symlink directories. No YAML field, arbitrary request-derived path, listing, upload, command, external host/account or fallback artifact. Preserve the existing package build-fingerprint policy: APK bytes/provenance are separate metadata, not a new `.apk` hash input or self-hash cycle.

Operational clarification2026-10-27: the final curated file is root:root **0444** (all write bits clear), matching the actual artifact verifier. The initial publication recipe's0644 was an integration defect and produces fail-closed503. A narrowly reviewed one-time parent metadata normalization may change only this exact root-owned/single-link/size/hash-verified curated inode from0644 to0444 using its held descriptor; no byte write, replacement, arbitrary chmod or service restart. Unknown artifacts/permissions/links remain refusal. Future atomic publication sets0444 before rename. Root/in-place byte writers remain outside the trusted exclusive-publisher assumption.

Validate size/hash/type/ownership/path safety against the same opened artifact; never validate one path then reopen another. Missing/unreadable/symlink/special/unsafe/oversize/corrupt/substituted artifact fails closed with generic503 and no partial/substitute download or filesystem/error-detail leak. Unknown/query/traversal/encoded alternate paths do not select another file. Error guidance leaves browser remote available; no false available/version/hash claim.

Successful response: `application/vnd.android.package-archive`, exact Content-Length, fixed safe attachment disposition, `X-Content-Type-Options: nosniff`, no-store. Initial scope promises GET only, no Range/resume/HEAD/update feed. HTTP remains unencrypted trusted-LAN traffic, not peer authentication or an Internet service; normal Android signature checks are not bypassed.

## Resource and UI constraints

Binary delivery stays outside WS/RPC/control ordering and shared control/state locks. Stream bounded chunks rather than a whole response-body allocation. At most2 active APK transfers; overload fails promptly, not an unbounded queue. Bound each write to at most5seconds and the total transfer lifetime to60seconds, including failure responses/cleanup. Restore socket state or close the download connection safely. Integrity/verification locks must not remain held while streaming. Existing control workers/ordering must retain headroom; do not claim threading alone provides isolation.

Keep the48px toolbar, familiar compact proportions, flexible pad, accessibility and current settings/About behavior. No new modal gate, forced choice, oversized banner/button bank or global scaling. Download actions are not remote input and must not trigger wake/power/playback/control requests through generic UI listeners. Native binding, navigation, metadata/lifecycle/profile guards remain intact.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md): public entry/download, unavailable/compatibility/UI/security behavior.
- [Android remote](../surfaces/android-remote.md): normal camera versus native scanner and delivered-versus-installed state.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): immutable artifact placement/provenance/update and bounded own deployment.
- [TV launcher](../surfaces/tv-launcher.md): unchanged QR also reaches the browser APK link.

Configuration schema, timer/power/media/bridge behavior and unrelated services are non-goals. Stop for approval if a new configuration field, native bridge/permission, service/package/privilege provisioning, broad file server or wider reachability becomes necessary.

## Acceptance and validation

- Exact current QR/native pairing/browser auth flow preserved; no second QR or identity/credential handoff.
- Link usable before PIN and visibly present on the ordinary browser's main remote after PIN-free/session restoration; it must not blink away with the login form or become menu-only. Bound old/new native pages use guidance/suppression even without/with late appInfo. Desktop/iOS keep normal web use.
- Fixed valid bytes/header/length delivered; missing/corrupt/path/type/ownership/symlink/alternate/Host/source cases fail closed with no private reads. Same-open-file integrity and atomic publication qualified.
- Independent source/fixture tests demonstrate2-transfer saturation, write/total deadline and cleanup, no lock/WS/control blocking and no download-triggered actuation. Test real predicates rather than replacing the critical verifier with mocks.
- Focused/full Python/Node, lint/format/syntax/security, compact geometry, APK provenance and complete-source wheel/manifest gates; independent review of actual diff and artifact/deploy boundary. No Git/index/config writes or private profiles/keys/cache publication.
- Parent-only reviewed payload/artifact staging with copied-byte checks, fresh bounded backup, preservation and warning before any necessary own-kiosk restart. Do not blindly reuse the release-specific71029f/6cea helper or replay its permanent transaction marker.
- Read-only installed HTTP/body-hash/header checks do not prove real camera download, Android update/data retention, native scanner/profile isolation or phone layout. Physical checks remain explicit acceptance; no timer set/cancel, sleep/wake/CEC/media/input tests in this stage.
