# Feature contract: One TV volume control

- Status: Approved for implementation; target verification pending
- Date: 2026-10-25
- Approval: User requested one volume slider and the other volume stages fixed at 100%.

## Goal and user-visible behavior

The selected audio output is the one user volume control on the phone, TV System, and touch panel. Output selection, mute, and sound test remain available. Firefox-stream and active managed HTML media volumes are kept at 100% so a user does not need to adjust three controls.

## Scenarios and edges

- A new Firefox stream is normalized to 100% within two seconds; a playing managed HTML media element is normalized to 100% after a service page loads or starts playing. Changing the selected output keeps the user's output volume choice.
- The site may mute its own player, use WebAudio, or deny injection in a frame. The app does not bypass those site rules; the output slider remains the normal control, and sound errors stay visible.
- Fixing an internal stage must never force the selected output above the user's setting or affect KDE's user session.

## Non-goals

Changing site mute semantics, controlling unrelated Firefox tabs, bypassing site or DRM restrictions, or removing the ability to select an audio output.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): System sound controls and touch panel.
- [Phone remote](../surfaces/phone-remote.md): main volume control and Menu sound controls.
- [Kubuntu operation](../surfaces/linux-operation.md): TV-user Firefox and PipeWire session.

## Interfaces and constraints

Keep the authenticated audio API and existing volume commands compatible, but expose one ordinary slider in the product UI. Browser normalization is scoped to the TV user's Firefox streams. Media normalization is scoped to tabs owned by the launcher and runs in permitted HTTP(S) frames through the signed extension. A new signed XPI is required. No PIN, URL, or media content is logged.

## Acceptance criteria

- Only one user-facing volume slider remains on each surface, and it changes the selected output.
- Firefox stream and active managed HTML media are 100% during playback; the output stays at the level chosen by the user.
- YouTube playback on the reference TV is audible and responds to the single slider; output switching and mute still work.

## Validation

Python and Node tests, shell and extension package checks, then a target playback check after signing. Update durable surface contracts and delete this temporary feature contract after acceptance.
