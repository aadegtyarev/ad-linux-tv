# ad-linux-tv

`ad-linux-tv` turns a Kubuntu computer into a TV launcher. Firefox opens the service tiles on the television; a phone on the same home network becomes a remote with a touchpad, keyboard, volume controls and a display timer. The tested appliance is a Beelink running a dedicated `ad-tv` session. A standard user-session installer is also included.

## Start here

1. Download `ad-linux-tv-*-source.tar.gz` from a successful [CI run](https://github.com/aadegtyarev/ad-linux-tv/actions/workflows/ci.yml), or use a source checkout. Extract the archive and enter its directory.
2. Preview the install with `./install.sh --dry-run`. Run `./install.sh --install` to install for the current user. It needs Python 3.12+, Firefox Snap and a graphical Kubuntu session. See [installation](docs/installation.md) for the signed Firefox bridge and update steps.
3. Open `http://127.0.0.1:8765/` on the TV. Scan the QR code with a phone on the same trusted network. A new installation opens without a PIN; you can enable a four-digit PIN in **System** or phone **Menu → Settings**.

The phone has a touchpad, arrows, Tab/Enter, text input, volume/mute, timer, service menu and a QR code to pair another phone. **Menu → Sound** holds output, Firefox-stream and page-player levels. System on the TV also offers cursor magnification, proxy and audio settings. The signed Firefox bridge is needed for service tabs, playback control and player-volume features; the source CI archive does not contain a signed bridge.

The server uses plain HTTP on a private LAN. Keep it on a trusted home network and do not expose port 8765 to the Internet. Streaming sites, logins and DRM behavior depend on Firefox and each site; see the [verification limits](docs/troubleshooting.md).

## Guides

- [Install, update and remove](docs/installation.md)
- [Use the TV and phone](docs/usage.md)
- [Settings and network access](docs/configuration.md)
- [Beelink dedicated TV session](docs/beelink.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development and architecture](docs/development.md)
- [Build and release packages](docs/release.md)

The project code is available under the [MIT License](LICENSE).
