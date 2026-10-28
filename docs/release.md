# Build and release packages

CI runs Python/JavaScript tests, lint, shell syntax and installer previews on every push or pull request. A successful run uploads **`ad-linux-tv-linux-source`**, containing `ad-linux-tv-<version>-source.tar.gz` and `SHA256SUMS`. Open the workflow run on GitHub and download the artifact from its **Artifacts** section. GitHub requires access to that run and retains the artifact for 30 days. This source package can install the app but **does not contain a signed Firefox bridge**.

Locally, from a tracked Git checkout:

```sh
python3 scripts/build_package.py --output-dir dist
cd dist && sha256sum --check SHA256SUMS
```

The archive has one versioned top-level directory, portable tracked files and no private config. Extract it, then run its `./install.sh --dry-run`. The build normalizes tar/gzip metadata for reproducibility. The package builder needs a Git checkout; the extracted package needs no Git checkout to install.

## Android APK and bridge source package

See [Android build/checks](android.md#build-and-check) for the Gradle wrapper, JVM tests, lint and `assembleDebug`. Its output is developer-signed `android/app/build/outputs/apk/debug/app-debug.apk`; a successful build is not physical phone acceptance. Keep signing keys, SDK paths and caches outside source packages.

To prepare, but not install or sign, the current bridge source:

```sh
mkdir -p .cache/artifacts
./extension/package.sh "$PWD/.cache/artifacts/ad-linux-tv-bridge-0.4.1-unsigned.zip"
```

Version0.4.1 repairs tile-open zoom by validating the existing automatic/per-tab scope before setZoom, without the failing setZoomSettings call. It retains 0.4.0's ID and permissions, bounded HTML-media/view capabilities and owned-tab-only mobile User-Agent policy. The normally signed 0.4.1 is already installed on the Beelink and the actual tile-open repair is operator-accepted; this does not publish a public release or qualify service playback. The [verification record](verification/tile-open-zoom-2026-10-26.md) records unsigned/signed hashes and payload checks. An unsigned ZIP is only a signing input, never a replacement to install in stable Firefox. Use normal AMO signing and Firefox confirmation, without signature bypasses. Inspect the [protocol and limits](bridge-protocol.md). Python/UI/discovery/magnifier updates can be staged independently; unsupported new operations remain gated.

The source-package builder intentionally takes tracked files. An uncommitted working tree with new untracked modules is not a complete distributable source snapshot. Review and track intended source before a release; never broaden the archive to include private ignored caches/configs merely to make packaging pass. Publishing, committing and AMO account access are separate operator decisions.

## Installed server versus Android candidate

The [power/compact-remote record](verification/remote-power-2026-10-26.md) remains historical evidence for the fixed power unit/sudoers and outstanding physical gates. The later [2026-10-27 settings/version deployment](verification/settings-versions-2026-10-27.md) installed the complete47-runtime-file S01/S02 wheel71029fad…5a95fa8, server0.1.0/build03c898b93f8fee48. Its independently reviewed app-only updater used root-locked copied-hash verification, a fresh private snapshot and only the own-kiosk restart. Signed0.4.1 was unchanged; tile-open acceptance remains a separate earlier result.

The later [same-QR APK deployment](verification/android-apk-download-2026-10-27.md) installed the48-runtime-file wheel91661d41…f94de, server0.1.0/build8a95389cf0c507a6, and serves native0.2.5/code6 as a separate root-owned0444 artifact. A full HTTP body/hash/header check passed; phone installation remains unverified. The source verifier rejects0644: use the corrected0444 publication procedure, not the historical0644 recipe. New app transactions are release-specific; never replay/delete a successful marker. Do not deploy the pre-fix49a/f787 wheel or infer physical phone/site acceptance from source or read-only checks.

The [2026-10-28 timer-window repair](verification/timer-window-icon-2026-10-28.md) separately updates the external libexec timer script324582de…6d52e8. It leaves package/build8a, APK, signed bridge and private configuration unchanged. Native countdown/automatic-warning captures and normal expiry are verified; one-file root publication and the existing supervisor avoid a kiosk restart. This is not a reason to replay either successful app transaction.

The [iOS invitation follow-up](verification/ios-apk-invitation-2026-10-28.md) changes only the package's remote.js: server0.1.0/buildb8799eb2b67487f7, complete wheel1a7ff9ae…c5a4f. Recognized iOS browsers keep the web remote without Android invitations. A fresh ios-apk-ui-app transaction preserves the existing APK0444/timer324/signed bridge/private state; never replay its successful marker. Installed-page UA emulation is not physical Safari acceptance.

## Signed release

A published GitHub Release triggers `.github/workflows/amo-sign.yml`. It signs the current `extension/` through AMO's **unlisted** channel using repository secrets `WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET`, compares the signed XPI payload with source, builds `ad-linux-tv-<version>-linux.tar.gz`, writes checksums and attaches the files to the Release. The project and Git tag versions must match, and the extension manifest version must be bumped before asking AMO to sign a new bridge version. Signing may fail if credentials, add-on ownership or AMO validation are missing; the workflow must succeed before using its asset.

The signed archive bundles `ad-linux-tv-signed.xpi` and its digest. `./install.sh --install` verifies the digest, saves the XPI and opens Firefox for a person to confirm installation. A GitHub Actions artifact is a short-lived CI download; a Release asset is the intended public package. Neither is a Debian package. Publishing and AMO signing still require the project owner to supply the necessary account settings and release decision. The source is under the MIT License.
