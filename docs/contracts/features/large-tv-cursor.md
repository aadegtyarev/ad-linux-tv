# Feature contract: visible TV cursor

- Status: Complete; target visual check passed
- Date: 2026-10-25
- Approval: User asked to make the phone-controlled cursor about three times larger and visible against dark video.

## Goal and user-visible behavior

The Beelink TV session uses a bright cursor about 72 pixels wide so the phone touchpad pointer can be found from a viewing distance.

## Scenarios and edges

- Cursor theme and size apply only to the dedicated `ad-tv` labwc session, including Firefox; the existing KDE user keeps their settings.
- A TV session restart applies the new cursor. The phone remote's movement and clicking stay unchanged.
- The chosen cursor theme is installed by Beelink setup on a new target.

## Non-goals

Changing pointer speed, touchscreen calibration, site hit targets, or KDE appearance.

## Affected surfaces

- [Kubuntu operation](../surfaces/kubuntu-operation.md): TV session environment and setup package.
- [TV launcher](../surfaces/tv-launcher.md): visible pointer for the phone remote.

## Interfaces and constraints

Use labwc's `XCURSOR_THEME` and `XCURSOR_SIZE` environment variables in the TV systemd unit. Do not modify the KDE user's profile or global cursor defaults.

## Acceptance criteria

- On Beelink after a TV session restart, the pointer is white, visibly larger, and still clicks accurately.
- KDE settings remain untouched; source setup can install the theme on a new machine.

## Validation

Unit syntax and setup dry-run passed. The installed theme contains a native 72 px cursor; the restarted labwc process has both cursor variables, Firefox bridge reconnected, and the user confirmed the pointer is visible and convenient.
