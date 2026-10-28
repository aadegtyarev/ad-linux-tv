# Feature contract: KION PIN on the TV keyboard

- Status: Approved for implementation; physical target check pending
- Date: 2026-10-24
- Approval: User reported that touching digits on the reference TV on-screen keyboard does not enter a KION profile PIN and asked to make KION usable.

## Goal and user-visible behavior

Numeric keys on the TV on-screen keyboard enter digits in KION's PIN field while preserving ordinary numeric entry on other sites and the EN/RU switch.

## Scenarios and edges

- Squeekboard numeric buttons send keyboard key events for digits 0–9, including on the wide touchscreen layout.
- Text fields on other sites continue to accept numbers. If KION still ignores key events, the phone remote's authenticated text entry remains a recovery path and the limitation is reported.
- No PIN is read, stored, logged, or transmitted by this change.

## Non-goals

Changing KION's authentication flow, bypassing a profile PIN, or changing the user's PIN.

## Affected surfaces

- [Kubuntu operation](../surfaces/linux-operation.md): dedicated TV keyboard layout installation.

## Interfaces and constraints

Update only the dedicated `ad-tv` Squeekboard layouts and their installer. The KDE user's keyboard and Firefox profile remain separate. Preserve the upstream layout checksum verification.

## Acceptance criteria

- Touching digits enters KION PIN dots after the field is focused.
- Digits still enter a regular website text field; EN/RU cycling still works.
- Installer dry-run and syntax checks pass; target layout files remain owned by `ad-tv`.

## Validation

Run shell checks and a layout generation check, then test on the reference TV touchscreen without exposing the PIN.
