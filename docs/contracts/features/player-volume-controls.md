# Feature contract: Active player volume controls

- Status: Approved for implementation; target playback pending
- Date: 2026-10-24
- Approval: User asked to adjust a site's player volume from both TV and phone controls and approved Firefox extension permission for all sites.

## Goal and user-visible behavior

The phone remote Menu and the TV touch sound panel can read and set volume (0–100%) for actively playing HTML audio/video in the current managed Firefox service tab. Controls show the actual read level or a clear unavailable state. The existing output and Firefox-stream controls remain available, including as a fallback if a website player cannot be controlled.

The phone Menu also exposes Tab and Shift+Tab to place focus on site controls such as KION's first menu item. The ineffective site-dependent fullscreen buttons are removed from the phone UI at the user's request.

## Scenarios and edges

- A playing media element in the top page or a permitted HTTP(S) frame reports volume and accepts a new value. Changing it unmutes that media element; changes are scoped to the active managed tab, never all tabs.
- With no active managed tab or playing HTML media, the UI says to start playback or select a service. It never claims success from merely queueing a command.
- Rapid changes preserve each command's result until the matching UI request can observe it, within bounded time/storage. A page or browser restart may make an in-flight action uncertain under the existing at-most-once bridge contract.
- Restricted frames, shadow DOM, WebAudio or site overrides may prevent independent player control; the Firefox audio-stream slider remains usable and the UI explains the limit.

## Non-goals

Changing subscription or DRM rules, manipulating site player widgets directly, storing media or credentials, controlling arbitrary Firefox tabs, or guaranteeing volume control for every website implementation.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): touch sound panel.
- [Phone remote](../surfaces/phone-remote.md): Menu sound controls and feedback.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): signed XPI update and target checks.
- [Configuration](../surfaces/configuration.md): no schema change.

## Interfaces and constraints

Extend the existing authenticated command queue with bounded player-volume read/set operations and correlated results. The extension may use `scripting.executeScript` only for the active tab already owned by the TV launcher, with permitted HTTP(S) host access and `allFrames`. Bump the extension version and require a new signed XPI. Do not inject into unrelated tabs or change the KDE Firefox profile. Keep phone PIN session/Origin/CSRF and loopback TV restrictions.

## Acceptance criteria

- Phone and TV controls read/set a playing HTML media element and report the result or a specific unavailable state without moving the UI layout.
- A non-owned tab, no media, invalid value, or missing permission does not change playback and gives useful feedback.
- Existing Home, service opening, output volume, Firefox-stream volume, remote pairing and queue semantics keep working.
- Tab/Shift+Tab remain available from the phone Menu, and the unsupported fullscreen buttons no longer appear there.
- An updated signed XPI is installed on Beelink after Mozilla signing; real target playback is confirmed for at least one reachable service. Site-specific failures remain documented.

## Validation

Run Python/Node tests, extension manifest/package checks, Ruff/shell and a local Firefox integration test before asking for XPI signing. After installation, verify browser permission prompt, live phone/TV UI, playback response, and status on unavailable media.
