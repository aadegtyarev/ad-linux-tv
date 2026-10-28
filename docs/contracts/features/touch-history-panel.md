# Feature contract: Movable touch panel and browser history

- Status: Implemented on the reference TV; awaiting physical touch feedback
- Date: 2026-10-24
- Approval: User asked for Back/Forward on the TV touch panel and phone remote, and for the touch panel to be draggable on the touchscreen.

## Goal and user-visible behavior

The small TV touch panel has distinct Back and Forward actions plus a drag handle. The paired phone remote has matching Back and Forward actions. The panel keeps its position across TV session restarts.

## Scenarios and edges

- Back and Forward navigate the active Firefox tab history only while Firefox is the active TV window. With no entry in that direction, the page stays in place.
- Dragging starts only on the handle, so tapping a control never moves the panel. The position is clamped to the active display so the handle remains reachable, including after resolution changes or an expanded sound popup.
- Fullscreen and no-touchscreen rules still hide the panel. A broken or missing saved position falls back to the upper-right default.

## Non-goals

- Page-specific back buttons or swipe gestures, navigation outside the dedicated TV session, and moving the panel between displays.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): touch panel and browser history.
- [Phone remote](../surfaces/phone-remote.md): matching history actions with authenticated input.
- [Kubuntu operation](../surfaces/linux-operation.md): dedicated TV-user panel position.

## Interfaces and constraints

- Check the active Firefox window, then use Alt+Left/Alt+Right virtual keys in the existing TV session; phone actions require the existing PIN session, Origin and CSRF protection. No XPI update.
- Store only bounded top/right margins in a private TV-user configuration file. Do not alter KDE user settings or other Firefox profiles.

## Acceptance criteria

- Touch Back and Forward work on a page with history. Phone Back and Forward work on the same page.
- Dragging the handle moves the panel and survives a session restart, while buttons remain tappable and the panel remains onscreen.
- Existing Home, keyboard, sound, fullscreen hiding and KDE recovery remain usable.

## Validation

- Run Python/Node, Ruff, shell and dry-run checks. Inspect panel dimensions and stored position on the reference TV; ask for physical touch/phone confirmation. Keep the feature contract until target verification is complete.
