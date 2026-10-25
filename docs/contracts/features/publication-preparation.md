# Feature contract: publication preparation

- Status: Approved by the user's request to rewrite documentation, polish maintainability, and provide a downloadable CI package; implementation in progress, 2026-10-25.

## Goal and user-visible behavior
- A new reader can understand what ad-linux-tv does, which machines it supports, how to install it, open the phone remote, operate it, update it, and recover from common failures without reading project history.
- CI builds and uploads a downloadable versioned Linux `.tar.gz` package with checksums after tests. A release build includes the AMO-signed Firefox XPI and verifies that its version and add-on ID match the source; the normal CI package is clearly identified as requiring a signed XPI for stable Firefox.
- Maintainability cleanup separates large phone-remote responsibilities into focused source modules without changing URLs, commands, authentication, UI behavior, or persisted configuration.

## Scenarios and failure behavior
- CI and local packaging produce the same file list from the tracked source tree. The archive has one top-level directory, contains no credentials or local private configuration, and extracts safely. Missing or mismatched signed XPI fails the release build.
- New users find general installation guidance first; Beelink-specific setup remains clearly labeled as a tested appliance recipe, not a portable generic installer.
- The release guide distinguishes a GitHub Actions artifact from a GitHub Release asset and documents AMO signing and manual Firefox confirmation.

## Non-goals
- No publication, push, GitHub Release creation, AMO submission, new media features, changed authentication behavior, or claims that every streaming service/DRM path has been verified.
- No license will be selected without the user's choice.

## Affected surfaces
- [Kubuntu operation](../surfaces/kubuntu-operation.md)
- [Phone remote](../surfaces/phone-remote.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Configuration](../surfaces/configuration.md)

## Interfaces and constraints
- Keep `config.yaml` and the current HTTP/WebSocket routes stable. Keep installer dry-run safe and existing config/profile preserved. A signed XPI remains necessary for Firefox stable.
- The source checkout and installed TV-user copy remain separate. The Beelink appliance scripts must not silently modify another user's KDE session.
- CI release signing uses GitHub secrets only in the release job and never places them in an artifact or log.

## Acceptance and validation
- Compare all public instructions with the current source and Beelink target state. Check local links and commands, archive contents and SHA256, unsigned/signed paths, Python/JS tests, lint, shell syntax, and install/uninstall dry-runs.
- Verify the generated package can be extracted and its installer can preview installation from inside it. Confirm the existing Beelink app and phone remote still work after any deployed source cleanup.
- Review the final diff for behavior changes, private data, stale versions, and release blockers; update durable surface contracts, then retire this temporary contract after verified completion.
