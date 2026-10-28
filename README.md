# ad-linux-tv

`ad-linux-tv` turns a Linux computer into a TV media center. Firefox shows service tiles on the television; a phone on the same home network becomes a remote with a touchpad, keyboard, volume, media controls and a display timer.

It runs on a Linux computer with apt and snap (Ubuntu/Kubuntu 24.04+ or similar), Python 3.12+ and Firefox Snap.

## Quick start

1. Get `ad-linux-tv-*.tar.gz` from a [Release or CI run](docs/release.md) (or use a checkout) and extract it.
2. Run `./install.sh --dry-run`, then `./install.sh --install`.
3. Open `http://127.0.0.1:8765/` on the TV and scan the QR code with your phone.

For a computer that is only a TV, use the [dedicated TV computer](docs/kiosk.md) setup instead.

The server is plain HTTP for a trusted home LAN. Never forward port 8765 to the Internet.

## Guides

- [Install, update and remove](docs/installation.md)
- [Dedicated TV computer (kiosk)](docs/kiosk.md)
- [Use the TV and phone](docs/usage.md)
- [Settings](docs/configuration.md)
- [Android app](docs/android.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Tested platforms](docs/platforms.md)
- [Development](docs/development.md)
- [Firefox bridge protocol](docs/bridge-protocol.md)
- [Build and release](docs/release.md)

Dated test records are in [docs/verification](docs/verification/).

The project is available under the [MIT License](LICENSE).
