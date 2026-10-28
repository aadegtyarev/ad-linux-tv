# Restore the familiar phone remote

Status: implemented; static UI deployed and checked; APK handoff unconfirmed. The layout and settings corrections pass184Python/82Node and18AndroidJVM/lint/assemble/apksigner. Independent source review approved current code/static-only rollout. Five synthetic fixtures verify stable success/pending/error geometry and no overlaps, not physical phone acceptance. APK0.2.1 is ready with the same signing certificate; both the initial new-version attempt and the later explicit operator request returned partial0/1. Do not retry automatically. Keep this temporary contract until the handoff is resolved.

## Goal and visible behavior
Restore the design and composition of the pre-redesign phone remote (repository HEAD a19e967), which the operator considers close to ideal. Keep a large touchpad and compact, usable media panel; remove added prose and coarse layout styling. Fix layout jumps/unexpected effects on taps instead of replacing the design. Reconsider settings: service tile selection, website address entry and browser key/Tab command collections do not belong in Settings and are removed from the phone menu/settings UI, not moved into another equally cluttered panel.

The operator approved this as a separate corrective task including a subsequent Beelink update. Preserve discovery/selection, per-center authorization, input retirement, media identity/preconditions and uncertainty/no-replay safeguards. Remove the notification-player activation button from the primary native remote screen; do not auto-start notifications or request new permission to compensate. Widget/new notification automation is not this task.

## Scenarios
- Opening the remote shows the familiar concise top actions, large pad/edge arrows, volume and available inline media; native chrome must not crowd the web remote.
- Tapping controls gives feedback without moving controls, shrinking the pad or replacing the desired media icon in an oscillating way.
- Settings contains actual persistent parameters (sound/output, pointer, magnifier scale, PIN/proxy) rather than service launching, URL entry or duplicated browser key banks. Keep useful text/timer/navigation controls in the familiar primary layout and QR connection assistance accessible.
- Unavailable media and network errors remain understandable without persistent explanatory paragraphs consuming control space.
- Small screens/large fonts may scroll rather than overlap. Physical acceptance is not inferred from headless or unit tests.

## Affected surfaces
- [Phone remote](../surfaces/phone-remote.md)
- [Android shell](../surfaces/android-remote.md)
- [Configuration](../surfaces/configuration.md)
- [Kubuntu operation](../surfaces/kubuntu-operation.md)
TV launcher rendering, bridge permissions and server control protocols are unchanged.

## Constraints and non-goals
No broad git reset: current uncommitted discovery, backend, security, bridge and timer work must survive. No endpoint/command deletion just because a phone control is removed. No unsigned extension installation, cookie/CSRF/security relaxation, profile migration, arbitrary JS bridge, Hermes/voice or unrelated service changes. No global tool installs or commit/push/publication. Previous APK transfer returned partial0/1: no automatic retry or alternate-channel bypass in this task.

## Acceptance and verification
Compare actual HEAD/current DOM/CSS/native shell and preserve baseline proportions rather than approximating from memory. Check page geometry at ordinary phone viewport and enlarged fonts, both with/without media. Exercise press/pending/status transitions and stable pad/control geometry in tests. Verify removed settings controls do not leave querySelector/event-handler failures and preserve session/device/lifecycle tests. Run Python/Node/Ruff/shell and relevant Android build/lint/JVM gates; independent read-only review if available. Deploy only owned media-center changes with staged backups/rollback and read-only health checks; new APK only if native shell changes. Update durable docs/contracts and retire this temporary contract after verified completion. Actual phone feedback remains separate.
