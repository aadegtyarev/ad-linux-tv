# Feature contract: Local TV pairing PIN

- Status: Complete; endpoint, LAN denial and rendered TV display verified
- Date: 2026-10-24
- Approval: User explicitly requested that the phone pairing PIN appear below the QR code on the TV tile screen.

## Goal and user-visible behavior

On the TV home screen, show the phone pairing PIN beneath the QR code. The phone can be paired without a keyboard or separate console session. The PIN is never included in a LAN response.

## Scenarios and edges

- The dedicated Beelink TV session has a private PIN file. Its local Firefox page fetches and displays the PIN near the QR code.
- A phone accessing `/remote`, `/api/services`, `/api/qr` or the new PIN endpoint over LAN cannot receive the PIN without entering it.
- A missing or unreadable PIN file leaves the launcher usable and gives a local, non-secret setup hint instead of exposing the verifier.
- PIN does not enter logs, URLs, browser storage, or extension commands; responses are not cached.

## Non-goals

- Exposing the PIN to LAN clients, changing the PIN verifier or authentication flow, or making the phone remote a PWA.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): local PIN display under QR.
- [Phone remote](../surfaces/phone-remote.md): local-only PIN endpoint security boundary.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): dedicated private PIN file path and kiosk environment.

## Interfaces and constraints

- `GET /api/local-pin` requires loopback source, exact `127.0.0.1:<port>` Host, a launcher-only request header, kiosk mode, and a configured private PIN file. It returns JSON only to the local TV browser.
- The existing LAN HTTP listener remains on port 8765; LAN responses and logs must not reveal the PIN.
- The dedicated TV user reads its own mode-0600 PIN file. KDE user's browser profile and source checkout remain untouched.

## Acceptance criteria

- The TV home screen displays the current PIN under the QR code.
- LAN attempts, including forged Host/header values, are denied; existing public GET responses contain no PIN.
- With the file unavailable, the app remains usable and the PIN display shows a local setup hint.

## Validation

- Add endpoint security tests, run Python/Node/lint/shell checks, and test local success plus LAN denial on Beelink without printing the actual PIN in logs or tool output.
- Completed: 42 Python and 23 Node tests passed; local PIN endpoint returned a nonempty value, the public service catalogue omitted it, and a forged-Host LAN request returned 403. An on-device screenshot was processed locally to confirm the rendered PIN label below QR without exporting or printing the PIN.
