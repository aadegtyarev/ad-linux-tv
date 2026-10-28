# Build and release

## Packages

| Package | Where | Signed bridge |
|---|---|---|
| `ad-linux-tv-<version>-source.tar.gz` | CI artifact `ad-linux-tv-linux-source` (kept 30 days) | No |
| `ad-linux-tv-<version>-linux.tar.gz` | GitHub Release asset | Yes (`ad-linux-tv-signed.xpi` + checksum) |

CI runs tests, lint, shell checks and installer previews on every push and pull request.

## Build locally

From a Git checkout (only tracked files are packaged):

```sh
python3 scripts/build_package.py --output-dir dist
cd dist && sha256sum --check SHA256SUMS
```

The archive is reproducible and contains no private config. Commit new files before building.

## Firefox bridge

Prepare the unsigned signing input:

```sh
mkdir -p .cache/artifacts
./extension/package.sh "$PWD/.cache/artifacts/ad-linux-tv-bridge-<version>-unsigned.zip"
```

Bump `version` in `extension/manifest.json` before each new signed version. Never install an unsigned ZIP in stable Firefox or bypass signing.

## Signed release

1. Make the project version and Git tag match; bump the extension version if it changed.
2. Publish a GitHub Release.
3. `.github/workflows/amo-sign.yml` signs `extension/` on AMO's unlisted channel (secrets `WEB_EXT_API_KEY`, `WEB_EXT_API_SECRET`), checks the signed payload against source, builds the linux archive with checksums and attaches it to the Release.

Use the asset only after the workflow succeeds.

## Android APK

See [Android build](android.md#build-and-check). The output is a developer-signed debug APK; keep signing keys outside the repository.

Dated deployment records: [docs/verification](verification/).
