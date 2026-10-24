# Feature contract: Configured service tile colors

- Status: Complete; validation and Beelink visual confirmation obtained
- Date: 2026-10-24
- Approval: User requested service-colored TV tiles, configured where the tiles are defined.

## Goal and user-visible behavior

Each service may specify a color in `config.yaml`; the TV tile uses it as a visible accent while keeping the title readable. Generated defaults provide colors for the five built-in services; the Browser tile is gray as requested. Existing configurations without colors remain valid and keep the neutral tile style.

## Scenarios and edges

- `color` is an optional six-digit CSS hex color such as `#ff0000`; malformed values fail validation before reaching the browser.
- Service color affects only the TV tile, not the phone selector, URL, or extension permissions.
- The installed Beelink configuration gains colors for known built-in services without changing its PIN verifier or other values.

## Non-goals

- Remote fetching of brand palettes, logos, arbitrary CSS in config, or automatic contrast selection from arbitrary images.

## Affected surfaces

- [Configuration](../surfaces/configuration.md): optional validated service color.
- [TV launcher](../surfaces/tv-launcher.md): colored tile rendering and readable fallback.

## Interfaces and constraints

- `services[]` keeps required `id`, `name`, `url`; optional `color` must match `#[0-9A-Fa-f]{6}`. The existing configuration remains valid.
- Only validated colors reach a CSS custom property. Text remains high-contrast on a dark mixed background.

## Acceptance criteria

- Colored services render distinct accents; a service without color renders the previous neutral style.
- Invalid color values are rejected; existing config loads unchanged.
- Beelink TV uses colors for its built-in service tiles after deployment.

## Validation

- Add config and launcher rendering tests, run Python/Node/lint checks, and visually inspect the Beelink tile screen without exporting the on-screen pairing PIN.

## Observed validation

- Config and launcher tests passed; five Beelink services expose validated colors. User confirmed the colored tiles look good and requested Browser gray, which was applied as `#6B7280`.
