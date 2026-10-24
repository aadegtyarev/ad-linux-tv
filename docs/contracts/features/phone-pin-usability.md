# Feature contract: Four-digit TV pairing PIN and phone visibility control

- Status: Implemented on Beelink; awaiting physical phone feedback
- Date: 2026-10-24
- Approval: User requested a four-digit numeric PIN and an eye control in the phone PIN field for the trusted local LAN.

## Goal and user-visible behavior

The Beelink TV shows a fresh four-digit pairing PIN below the QR code. The phone entry has a clear eye button that shows or hides the entered digits without resetting them.

## Scenarios and edges

- The current eight-character Beelink PIN is replaced with a random four-digit numeric PIN. Sessions using the old verifier end when the PIN rotates; the new code appears only on the local TV screen. The phone restores a valid paired session after page reload or service restart and asks for PIN after 14 days.
- The eye control is finger-sized, announces its show/hide state, and leaves numeric input active. Hiding the PIN is the default after page load.
- A wrong code still follows the existing rate limit. Remote source, Origin, session and CSRF controls are unchanged.

## Non-goals

- Sending the PIN to the phone automatically, exposing it over LAN, disabling login, changing the length of PINs on other existing installations, or changing authentication requirements for other installations.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md): PIN entry.
- [TV launcher](../surfaces/tv-launcher.md): local PIN display.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): private Beelink PIN rotation.

## Interfaces and constraints

- Keep the existing PBKDF2 verifier in private config and mode-0600 local PIN file in sync. Do not print the new PIN to commands, logs, or chat. Do not store it in source control.
- Preserve PIN support for other deployments using 4–128 characters; the phone field must not truncate their existing PINs.

## Acceptance criteria

- On Beelink, only the new four-digit PIN logs in; incorrect attempts are rate limited.
- The TV shows the new code locally and the phone eye button toggles visibility without altering digits or submission. Valid sessions restore without PIN on phone reload and after TV service restart.
- Existing phone remote controls and security checks remain functional.

## Validation

- Test phone UI, login endpoint and PIN-file consistency without exposing the PIN. Verify mode-0600 files and successful TV service restart; ask the user to confirm real-phone entry.
