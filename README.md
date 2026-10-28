# ad-linux-tv

`ad-linux-tv` turns a Kubuntu computer into a TV launcher. Firefox opens the service tiles on the television; a phone on the same home network becomes a remote with a touchpad, keyboard, volume controls and a display timer. The tested appliance is a Beelink running a dedicated `ad-tv` session. A standard user-session installer is also included.

## Start here

1. Download `ad-linux-tv-*-source.tar.gz` from a successful [CI run](https://github.com/aadegtyarev/ad-linux-tv/actions/workflows/ci.yml), or use a source checkout. Extract the archive and enter its directory.
2. Preview the install with `./install.sh --dry-run`. Run `./install.sh --install` to install for the current user. It needs Python 3.12+, Firefox Snap and a graphical Kubuntu session. See [installation](docs/installation.md) for the signed Firefox bridge and update steps.
3. Open `http://127.0.0.1:8765/` on the TV. Scan the QR code with a phone on the same trusted network. A new installation opens without a PIN; you can enable a four-digit PIN in **System** or phone **Menu → Settings**.

The phone has a touchpad with two-axis scrolling, arrows, Tab/Enter, inline text input, volume/mute, timer, settings and a QR code to pair another phone. Tap ⏻ beside Timer for display sleep/wake; hold it for a separate whole-computer shutdown confirmation. Shutdown stops all host tasks and requires the computer's physical button to restart; output-on does not guarantee the TV wakes. Read [power controls and verification limits](docs/usage.md#power-beside-the-timer) before using them. Settings omit service launching, direct website entry and duplicate browser-key banks. The [Android app](docs/android.md) adds LAN discovery, manual/QR entry, saved media centers with isolated authorization and explicit switching in a compact header. It requires a modern WebView with multi-profile support; phone runtime acceptance is separate from automated builds. **Menu → Sound** holds output, Firefox-stream and page-player levels. System on the TV also offers cursor magnification, proxy and audio settings. The signed Firefox bridge is needed for service tabs and page-player features; the source CI archive does not contain one. MPRIS media controls work without the new extension when the site exposes them. Signed bridge 0.4.1 is installed on the Beelink; its tile-open zoom repair passed an actual tile click and operator confirmation. It also reports capability-gated HTML media and view support, which does not guarantee site playback or seek. See the [verification record](docs/verification/tile-open-zoom-2026-10-26.md). [Reusable bridge operations](docs/bridge-protocol.md) keep ordinary server/UI changes independent of extension signing.

The server uses plain HTTP on a private LAN. Keep it on a trusted home network and do not expose port 8765 to the Internet. Streaming sites, logins and DRM behavior depend on Firefox and each site; see the [verification limits](docs/troubleshooting.md).

## Guides

- [Install, update and remove](docs/installation.md)
- [Use the TV and phone](docs/usage.md)
- [Android setup, switching and APK build](docs/android.md)
- [Settings and network access](docs/configuration.md)
- [Beelink dedicated TV session](docs/beelink.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development and architecture](docs/development.md)
- [Build and release packages](docs/release.md)

The project code is available under the [MIT License](LICENSE).
