# Build and release packages

CI runs Python/JavaScript tests, lint, shell syntax and installer previews on every push or pull request. A successful run uploads **`ad-linux-tv-linux-source`**, containing `ad-linux-tv-<version>-source.tar.gz` and `SHA256SUMS`. Open the workflow run on GitHub and download the artifact from its **Artifacts** section. GitHub requires access to that run and retains the artifact for 30 days. This source package can install the app but **does not contain a signed Firefox bridge**.

Locally, from a tracked Git checkout:

```sh
python3 scripts/build_package.py --output-dir dist
cd dist && sha256sum --check SHA256SUMS
```

The archive has one versioned top-level directory, portable tracked files and no private config. Extract it, then run its `./install.sh --dry-run`. The build normalizes tar/gzip metadata for reproducibility. The package builder needs a Git checkout; the extracted package needs no Git checkout to install.

## Signed release

A published GitHub Release triggers `.github/workflows/amo-sign.yml`. It signs the current `extension/` through AMO's **unlisted** channel using repository secrets `WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET`, compares the signed XPI payload with source, builds `ad-linux-tv-<version>-linux.tar.gz`, writes checksums and attaches the files to the Release. The project and Git tag versions must match, and the extension manifest version must be bumped before asking AMO to sign a new bridge version. Signing may fail if credentials, add-on ownership or AMO validation are missing; the workflow must succeed before using its asset.

The signed archive bundles `ad-linux-tv-signed.xpi` and its digest. `./install.sh --install` verifies the digest, saves the XPI and opens Firefox for a person to confirm installation. A GitHub Actions artifact is a short-lived CI download; a Release asset is the intended public package. Neither is a Debian package. Publishing and AMO signing still require the project owner to supply the necessary account settings and release decision. The source is under the MIT License.
