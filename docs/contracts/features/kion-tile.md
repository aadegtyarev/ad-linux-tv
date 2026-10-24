# Feature contract: KION service tile

- Status: Implemented and verified on Beelink; login, subscription and playback remain untested
- Date: 2026-10-24
- Approval: User requested adding MTS KION as a TV service.

## Goal and user-visible behavior

The Beelink launcher shows a KION tile alongside existing services. Opening it uses the official KION browser site in the dedicated Firefox profile. Newly generated configurations include the same tile.

## Scenarios and edges

- The tile links to `https://kion.ru/` and has a recognizable magenta accent.
- Existing service tiles, logins, and KDE profile are preserved. The installer does not overwrite other existing configurations.
- KION login, subscription, playback and DRM remain subject to the service and the target Firefox environment.

## Non-goals

- Installing a KION Android or TV app, sharing credentials, bypassing DRM, or changing other service addresses.

## Affected surfaces

- [Configuration](../surfaces/configuration.md): default catalogue and Beelink service list.
- [TV launcher](../surfaces/tv-launcher.md): visible tile and launch action.

## Interfaces and constraints

Use the existing validated service schema and managed Firefox tab flow; no XPI permission or authentication change. Keep the Beelink configuration private and do not print its auth fields.

## Acceptance criteria

- KION appears on Beelink, selecting it opens `https://kion.ru/` in Firefox, and the existing tiles still open.
- A newly generated configuration includes KION with a valid color; existing custom installations are not changed automatically.

## Validation

Run config and launcher tests, lint, dry-run checks, and a live Beelink tile/open check. Report any login, subscription or DRM gate observed without claiming playback works until tested.
