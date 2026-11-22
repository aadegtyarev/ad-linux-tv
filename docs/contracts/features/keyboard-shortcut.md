# Remote button for the on-screen keyboard

Status: approved by the operator (2026-11-22); implemented and source-verified, reference-TV check (criterion 3) pending.

## Goal and user-visible behavior
The owner can assign one rare remote/keyboard button that shows or hides the Squeekboard on-screen keyboard in the dedicated TV session, without a touchscreen. Phone Settings → **Кнопки пульта** gains a seventh action, «Клавиатура», learned, saved and cleared exactly like the other six. The button toggles: hidden → shown and kept open, shown → hidden. It shares one state with the touch panel's keyboard button, so either control closes what the other opened. The touch panel's Home still hides the keyboard.

## Scenarios and edge cases
- No touchscreen: the touch overlay process still runs; the shortcut opens the keyboard and keeps it open across focus changes until toggled again or Home.
- Fullscreen video still drops the kept-open keyboard, as for the touch button.
- Touchscreen disconnect drops only a touch-opened keyboard, not one opened by the remote button.
- Overlay not running or not reachable: the button does nothing; no error UI.
- Squeekboard D-Bus unavailable: state stays hidden, as for the touch button.

## Non-goals
Keyboard layouts/appearance, phone text entry, automatic display on field focus, a phone-remote keyboard button, a new IPC framework.

## Affected surfaces
[configuration](../surfaces/configuration.md), [TV launcher](../surfaces/tv-launcher.md), [phone remote](../surfaces/phone-remote.md), [Linux operation](../surfaces/linux-operation.md).

## Interfaces and constraints
- `tv_shortcuts.keyboard`: same allowlist, one key, distinct from the other actions.
- labwc binding runs the fixed `tv-shortcut.sh keyboard`; it signals the exact touch-overlay process of the TV user with SIGUSR1. No input reaches the command.
- The overlay installs the SIGUSR1 handler before entering the GTK loop.
- Assignments apply after a TV-mode restart, as for the existing actions.

## Acceptance criteria
1. `keyboard` is accepted by config validation, the learner/save path and the phone wizard; duplicates are rejected.
2. Rendered labwc config binds the saved key to `tv-shortcut.sh keyboard`.
3. On the reference TV, the assigned button shows the keyboard, it stays open while focus moves, and a second press hides it.

## Validation
`.venv/bin/pytest -q`, `node --test tests/*.test.js`, `ruff check` / `ruff format --check`, `bash -n ops/kiosk/tv-shortcut.sh`, then criterion 3 on the reference TV after the operator approves deployment.
