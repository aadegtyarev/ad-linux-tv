# Feature contract: TV display sleep timer

- Status: Approved for implementation; target verification pending
- Date: 2026-10-25
- Approval: User requested a TV-style timer in the phone remote and TV System. At expiry, pause playback and turn off only the monitor image, leaving Beelink and the TV session running. A phone command or monitor touch wakes the image.

## Goal and user-visible behavior

The phone Menu and TV System offer Off, 15, 30, 60, 90 and 120-minute presets, remaining time, and cancellation. Countdown begins when selected, regardless of activity. At expiry the active managed HTML media is paused, then HDMI output power turns off. Beelink, SSH, Firefox and KDE recovery remain available. The next phone control action or touchscreen interaction turns the output on; the timer is then cleared.

## Scenarios and edges

- A new preset replaces the old deadline; Off cancels it. The remaining time is server-owned, so leaving or reloading the browser page does not lose it.
- A normal phone command wakes a dark screen before acting. Touch activity also wakes it. Wake never resumes playback automatically.
- The bridge may report no playing HTML media, or a restricted site may prevent pausing. Other Firefox tabs or another TV-session app may also remain audible. In these cases the timer reports a clear limitation and must not leave audible playback behind a dark screen; screen-off is withheld if playback cannot be safely paused or checked.
- A TV session restart cancels the timer and restores output power. The countdown need not survive machine reboot.
- An offline bridge, unavailable Wayland output-power protocol, or failed pause leaves the screen on and reports an error.

## Non-goals

Powering off or suspending Beelink, switching to KDE, controlling another user's session, resuming a paused video on wake, or bypassing DRM.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): System controls, active managed media, and touch wake.
- [Phone remote](../surfaces/phone-remote.md): timer controls and wake on authenticated commands.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): `wlopm`/`swayidle` packages and session lifecycle.

## Interfaces and constraints

Use a bounded, authenticated timer API with phone session, Origin and CSRF checks; allow only exact kiosk loopback for the TV UI. Keep state in the TV server rather than browser JavaScript. Use the compositor's output power protocol (`wlopm`), leaving logical output layout unchanged. `swayidle` watches activity to wake the monitor. Pause only playing HTML media in the active managed Firefox tab using a newly signed bridge version. Do not expose URLs, credentials or media content in status.

## Acceptance criteria

- Phone and TV show the same remaining time; setting/replacing/cancelling works and retains normal navigation.
- At expiry a test video pauses before HDMI goes off, and touch plus a phone action each turn the image back on without resuming the video.
- If pause or output power fails, HDMI stays on and the UI explains why.
- KDE and the existing Beelink boot flow remain unaffected.

## Validation

Unit tests for timer state, authorization and bridge pause; JS UI tests; Ruff, shell, package and Firefox integration. On Beelink verify `wlopm` off/on, `swayidle` touch wake, signed XPI update and real playback. Delete this temporary contract after target acceptance and durable surface-contract updates.
