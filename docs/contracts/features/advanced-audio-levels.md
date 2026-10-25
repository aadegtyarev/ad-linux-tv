# Feature contract: advanced audio levels

- Status: Server and TV/phone controls installed on Beelink; Python/Node checks passed. Signed bridge 0.3.2 is active (`signedState=2`). Local looping HTML-audio playback was pinned to a 37% target and returned to 37% after the page requested 80%. Real service playback and phone UI acceptance remain pending, 2026-10-25.
- Approval: User confirmed all three levels in TV and phone settings, with the simple control below the touchpad retained.

## Goal and scenarios
- TV System and phone Settings show separate 0–100% controls for the selected output, Firefox audio stream, and accessible playing page media. The phone touchpad keeps its single output-volume control.
- Output volume is always available when a sink exists. Firefox and page levels show clear unavailable states when no corresponding active stream or accessible media exists. They can be changed while available; the chosen levels persist for later streams/media and through TV-session restarts.
- A change at one level leaves other selected levels unchanged. Mute and test sound continue to work. A failed change reports failure and retains the prior setting.

## Non-goals
- Per-site presets, independent volumes for individual Firefox tabs, inaccessible DRM/restricted-frame or WebAudio media, and changing KDE audio outside the TV session.

## Affected surfaces
- [Configuration](../surfaces/configuration.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)
- [Kubuntu operation](../surfaces/kubuntu-operation.md)

## Interfaces and constraints
- Store durable advanced levels in the existing private config.yaml. Existing configurations default Firefox and page media levels to 100%. Output selection/volume retain their current persistence path.
- Reuse the authenticated audio endpoint and phone WebSocket; do not add a live transport. Respect the existing local-TV versus phone auth boundaries.
- Update the signed Firefox extension for page-media level handling; installing the new extension requires a newly signed XPI. The signed 0.3.2 XPI has been installed interactively on Beelink; keep the real-service playback gate until observed.

## Acceptance and validation
- Verify level validation, persistence, stream normalization to selected target, page-media target application and later site changes, unavailable states, and TV/phone UI requests. Run Python and Node tests and lint, then validate on Beelink. Check extension signature and real playback after installing the new signed XPI.
