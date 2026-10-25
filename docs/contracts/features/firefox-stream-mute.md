# Feature contract: visible Firefox stream mute

- Status: Installed on Beelink; 90 Python and 44 JS checks passed, TV System fit checked at 1360×768. Live mute/unmute through the audio API passed on a silent stream named Firefox, and WirePlumber retained mute=false; phone Settings acceptance remains pending, 2026-10-25.

## Goal and user-visible behavior
- TV System and phone Settings show whether the Firefox sound stream is muted and offer one button to mute or unmute it. The existing output mute remains distinct and keeps its current control.
- When no Firefox stream exists, show that the control is unavailable. A new stream uses WirePlumber's saved stream state; the user can correct it when it appears.
- The button affects Firefox sink inputs only, including multiple Firefox inputs, and leaves HDMI/output mute, output level, Firefox level and page-player level unchanged.

## Non-goals
- No new persistent mute field in config.yaml, per-site mute, automatic unmute of deliberately muted tabs, or extension permission change.

## Affected surfaces
- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)
- [Kubuntu operation](../surfaces/kubuntu-operation.md)

## Interfaces and constraints
- Reuse authenticated `GET/POST /api/audio` and phone WebSocket routing. Add `browser_muted: boolean|null` to audio state; accept one-field `{browser_muted: boolean}` POST. Null means no current Firefox stream. Keep existing local-TV and phone session/CSRF checks.
- Expose the button beside the Firefox stream level in both Settings views, with an unambiguous label and disabled state when no stream exists.

## Acceptance and validation
- A muted Firefox stream is reported, can be unmuted from TV and phone Settings, and becomes audible while playback continues. Re-reading state reflects the action; unrelated streams/output are untouched. Invalid types and no-stream actions fail safely.
- Run Python/Node tests and lint; deploy to Beelink; verify the live settings show unmuted Firefox and the current Kinopoisk stream remains audible.
