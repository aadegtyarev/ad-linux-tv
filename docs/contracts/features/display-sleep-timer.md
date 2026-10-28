# Feature contract: TV display sleep timer

- Status: Approved for implementation; target verification pending
- Date: 2026-10-25
- Approval: User requested a TV-style timer, then clarified that it must be accessible during viewing: a Timer button on the phone remote opens controls on the phone without leaving the video, and a Timer button in the touch-only floating TV panel opens controls over video. TV System remains a secondary entry point. At expiry, pause playback and turn off only the monitor image, leaving reference TV and the TV session running. A phone command or monitor touch wakes the image.

## Goal and user-visible behavior

The phone remote's primary screen opens a dedicated timer screen, and the floating TV touch panel opens an over-video timer panel. TV System also offers Off, 15, 30, 60, 90 and 120-minute presets, remaining time, and cancellation. Countdown begins when selected, regardless of activity. At expiry the active managed HTML media is paused, then HDMI output power turns off. reference TV, SSH, Firefox and KDE recovery remain available. The next phone control action or touchscreen interaction turns the output on; the timer is then cleared.

## Scenarios and edges

- A new preset replaces the old deadline; Off cancels it. The remaining time is server-owned, so leaving or reloading the browser page does not lose it.
- A normal phone command wakes a dark screen before acting. Touch activity also wakes it. Wake never resumes playback automatically.
- The bridge may report no playing HTML media, or a restricted site may prevent pausing. Other Firefox tabs or another TV-session app may also remain audible. In these cases the timer reports a clear limitation and must not leave audible playback behind a dark screen; screen-off is withheld if playback cannot be safely paused or checked.
- A TV session restart cancels the timer and restores output power. The countdown need not survive machine reboot.
- An offline bridge, unavailable Wayland output-power protocol, or failed pause leaves the screen on and reports an error.

## Non-goals

Powering off or suspending reference TV, switching to KDE, controlling another user's session, resuming a paused video on wake, or bypassing DRM.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): System and touch-overlay controls, active managed media, and touch wake.
- [Phone remote](../surfaces/phone-remote.md): main-remote timer entry, timer controls and wake on authenticated commands.
- [Kubuntu operation](../surfaces/linux-operation.md): `wlopm`/`swayidle` packages and session lifecycle.

## Interfaces and constraints

Use a bounded, authenticated timer API with phone session, Origin and CSRF checks; allow only exact kiosk loopback for the TV UI. Keep state in the TV server rather than browser JavaScript. Use the compositor's output power protocol (`wlopm`), leaving logical output layout unchanged. `swayidle` watches activity to wake the monitor. Pause only playing HTML media in the active managed Firefox tab using a newly signed bridge version. Do not expose URLs, credentials or media content in status.

## Acceptance criteria

- Phone and TV show the same remaining time; setting/replacing/cancelling works and retains normal navigation. The phone can set a timer without changing the TV video tab; on a touch monitor the floating panel can open timer controls over video.
- At expiry a test video pauses before HDMI goes off, and touch plus a phone action each turn the image back on without resuming the video.
- If pause or output power fails, HDMI stays on and the UI explains why.
- KDE and the existing reference TV boot flow remain unaffected.

## Validation

Unit tests for timer state, authorization and bridge pause; JS UI tests; Ruff, shell, package and Firefox integration. On the reference TV verify `wlopm` off/on, `swayidle` touch wake, signed XPI update and real playback. Delete this temporary contract after target acceptance and durable surface-contract updates.
