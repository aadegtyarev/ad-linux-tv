# Feature contract: TV audio controls

- Status: Implemented; physical Bluetooth and numeric keyboard checks pending
- Date: 2026-10-24
- Approval: User asked for a phone remote volume control and a choice of output for HDMI, Bluetooth speakers or another connected output.

## Goal and user-visible behavior

The TV System menu and paired phone remote show the currently selected TV audio output and let the user choose an available output, adjust its volume from 0 to 100%, mute or unmute, and separately adjust active Firefox-stream volume. HDMI and the current Firefox audio stream start at 100%; website player volume remains under the user’s control.

## Scenarios and edges

- Outputs appear by readable name only when PulseAudio/PipeWire reports them. Selecting one makes it the default output and moves current TV audio streams to it.
- A selected output is remembered for the dedicated `ad-tv` TV user. If absent when the TV session starts, an attached HDMI sink is preferred, then the available system default. The saved preference is retained so the user can select the device again when it reconnects.
- If audio services are unavailable, the remote shows an actionable error without changing browser commands or the KDE user’s audio settings.
- A three-icon touch panel includes a sound button that reveals separate output and active Firefox-stream volume sliders, then collapses after inactivity. The output slider uses the same local audio API and saves the TV-user choice; the Firefox slider adjusts only active Firefox audio streams, with a no-playback hint otherwise. The panel stays open for 15 seconds after the last touch change.
- A manual keyboard button keeps Squeekboard visible through transient focus loss while entering a multi-digit code, until the user closes it with the keyboard icon, returns Home, or enters fullscreen.

## Non-goals

- Pairing Bluetooth devices, modifying the KDE user’s audio profile, raising volume above 100%, automatic switching when a disconnected device reappears, or changing per-site player volume.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md): authenticated audio state, selection, volume and mute controls.
- [TV launcher](../surfaces/tv-launcher.md): the same controls under System, available only to the local kiosk.
- [Kubuntu operation](../surfaces/linux-operation.md): TV-user audio preference and HDMI startup fallback.

## Interfaces and constraints

- Audio GET/POST routes require either the local kiosk launcher over exact loopback Host or a paired private-LAN session with valid Host; remote POST also requires matching Origin and CSRF. The server invokes only fixed `pactl` commands with validated output names and 0–100 integers.
- A TV-user preference file stores only the selected sink name, with restricted permissions. No root calls or Firefox extension changes.

## Acceptance criteria

- The TV System menu and phone remote display available outputs and current volume/mute state, select an output, move active Firefox audio, and persist the choice across a TV session restart. The touch sound panel and both web UIs separately adjust output and active Firefox-stream volume.
- Unauthenticated, cross-origin, malformed and out-of-range audio requests are denied without changing audio.
- On the reference TV, HDMI sink and Firefox stream are 100%, and manually opened Squeekboard remains visible across transient focus loss.

## Validation

- Run endpoint/security tests, Node UI tests, lint/shell checks and install dry-run. Check live reference TV HDMI state and audio API without exposing login secrets. Physical Bluetooth selection and the third-party numeric entry flow require user verification.

## Observed validation

- 51 Python and 27 Node tests passed, plus Ruff and shell checks. On the reference TV, paired LAN requests read audio state and successfully set 100% volume, unmute and reselect HDMI; the output preference file is private. HDMI remains at 100%. Bluetooth output and repeated-digit touch input still need physical testing.
