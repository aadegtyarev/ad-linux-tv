# Feature contract: visible timer countdown and two-minute warning

- Status: Installed on the reference TV; Python/Node checks and live TV badge passed. Phone badge and the two-minute fullscreen warning remain live checks, 2026-10-25.
- Approval: User confirmed the proposed phone/TV countdown and TV warning actions in the session.

## Goal and scenarios
- While a display timer counts down, a small remaining-time indicator is visible on the phone's main remote and in a TV corner, including over fullscreen video. It disappears when the timer is off or the screen is asleep; an error remains visible in the existing timer controls.
- At two minutes remaining, a larger TV corner warning appears above fullscreen video. «ОК» dismisses that warning for the current timer without changing its deadline. «Изменить» reveals the existing timer presets in the corner window, and choosing one resets the deadline. «Отменить» cancels the timer.
- A newly set timer gets a new warning opportunity. Polling and UI reopening do not re-show a dismissed warning for the same timer. At expiry, the existing pause-then-HDMI-off safety behavior remains unchanged.

## Non-goals
- OS suspend, waking media automatically, push notifications outside the phone page, changing the timer presets or expiry safety decision.

## Affected surfaces
- [Phone remote](../surfaces/phone-remote.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Kubuntu operation](../surfaces/linux-operation.md)

## Interfaces and constraints
- Reuse `/api/display-timer` and the existing phone WebSocket. Expose a nonsecret timer generation identifier to distinguish a new countdown from a dismissed warning.
- Use a separate lightweight GTK layer-shell corner window in the current Wayland TV session. It is independent of touch-panel and fullscreen visibility, takes no keyboard focus, and uses the existing loopback timer API. Keep code separate from the large touch-overlay module.
- Keep the warning compact and the persistent badge unobtrusive. Errors and connection loss should not leave a stale countdown or a blocking overlay.

## Acceptance and validation
- Test countdown formatting, two-minute threshold, dismissal and rearm, change/cancel actions, phone main-screen indicator, fullscreen overlay visibility, and safe expiry unchanged. Run Python/Node tests, shell/lint checks and inspect live TV/phone screens.
