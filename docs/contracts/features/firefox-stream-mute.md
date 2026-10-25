# Feature contract: visible Firefox stream mute

- Status: Saved setting installed on Beelink; 92 Python and 44 JS checks passed. With no stream, POST saved mute=true; a later silent stereo Firefox-named stream became muted, POST mute=false unmuted it, and config returned to false. TV System at 1360×768 shows the enabled button with no stream. Real phone Settings acceptance remains pending, 2026-10-25.

## Goal and user-visible behavior
- TV System and phone Settings show whether the Firefox sound stream is muted and offer one button to mute or unmute it. The existing output mute remains distinct and keeps its current control.
- The control remains available without a Firefox stream; it shows the saved desired state and applies it to future streams. When a stream exists, the server brings its mute state to the saved state. WirePlumber's own remembered state is not the source of truth.
- The button affects Firefox sink inputs only, including multiple Firefox inputs, and leaves HDMI/output mute, output level, Firefox level and page-player level unchanged.

## Non-goals
- No per-site mute, Firefox tab-mute UI, or extension permission change. The global saved setting is allowed to override a stream's independent mute state.

## Affected surfaces
- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)
- [Configuration](../surfaces/configuration.md)
- [Kubuntu operation](../surfaces/kubuntu-operation.md)

## Interfaces and constraints
- Reuse authenticated `GET/POST /api/audio` and phone WebSocket routing. Keep `browser_muted: boolean|null` for current stream state; add `browser_mute_target: boolean` for the saved setting. Accept one-field `{browser_muted: boolean}` POST even when no stream exists. Keep existing local-TV and phone session/CSRF checks.
- Add optional `audio.browser_muted: boolean` to config.yaml, default false for existing installations and explicit false for new ones. Save atomically without changing existing audio levels or sessions. The two-second Firefox stream normalizer applies both saved volume and mute targets.
- Expose the button beside the Firefox stream level in both Settings views. Its label follows the saved target; the hint distinguishes an absent stream from an active stream.

## Acceptance and validation
- A muted Firefox stream is reported, can be unmuted from TV and phone Settings, and becomes audible while playback continues. TV System can also toggle the saved mute target with no stream; the next stream follows it. Re-reading state reflects the action; unrelated streams/output are untouched. Invalid types fail safely.
- Run Python/Node tests and lint; deploy to Beelink; verify the live settings show unmuted Firefox and the current Kinopoisk stream remains audible.
