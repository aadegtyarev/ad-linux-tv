# Feature contract: One-tap TV keyboard language cycle

- Status: Physical touch confirmed; session-restart persistence pending
- Date: 2026-10-24
- Approval: User requested a large one-tap language switch on the on-screen keyboard, cycling languages with an indicator instead of the small language-selection list.

## Goal and user-visible behavior

The dedicated TV keyboard has a prominent language key. The adjacent TV touch controls retain large finger-sized icon targets. It shows the current input language and the next one, and each tap cycles between English and Russian without opening a popup.

## Scenarios and edges

- English layout shows `EN→RU`; tapping it switches to Russian, which shows `RU→EN`. The operation also works from numbers/symbols views.
- The choice is represented by the first source in the dedicated `ad-tv` source list and survives a TV session restart. KDE user input sources remain untouched.
- If the system cannot change the layout, the keyboard remains usable; the old language popup is not the primary path.

## Non-goals

- Adding more than two languages, changing phone-native keyboard behavior, modifying the KDE user keyboard or Firefox extension.

## Affected surfaces

- [Kubuntu operation](../surfaces/kubuntu-operation.md): Squeekboard layout installation and labwc binding.
- [TV launcher](../surfaces/tv-launcher.md): on-screen keyboard interaction on TV/third-party pages.

## Interfaces and constraints

- The four pinned, checksum-verified Squeekboard layouts (`us`, `us_wide`, `ru`, `ru_wide`) are customized for `ad-tv` only. The language key triggers one private labwc binding to a fixed local script; labels are static per layout and therefore indicate the current choice.
- Keep existing letter, number, symbol and Backspace behavior; preserve touch overlay and KDE recovery.

## Acceptance criteria

- A touch user can cycle EN ↔ RU with one large on-keyboard tap and see which language is active.
- No small popup is needed in normal use; switching works in letters and digits/symbols views.
- Existing TV/KDE separation and keyboard visibility behavior remain intact.

## Validation

- Validate generated YAML, script and labwc XML, run project checks, test F12-to-layout switching on Beelink without sending text to a website, and ask for physical touch confirmation. Physical tapping emitted F12 and changed `current`, but Squeekboard continued to use the first item in `sources`. Swapping the source order changed the visible layout immediately. The revised script changed the visible EN/RU layouts, and the user confirmed physical touch switching. Session-restart persistence remains to be checked without interrupting an ongoing sign-in.
