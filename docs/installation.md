# Install, update and remove

## Requirements

Use Kubuntu with Python 3.12 or newer, Firefox Snap, a display and a graphical user session. The generic installer creates a user-scoped app and optional Plasma autostart. The dedicated Beelink TV session has [separate setup steps](beelink.md).

## Install

From an extracted archive or checkout:

```sh
./install.sh --dry-run
./install.sh --install
```

The preview lists destinations. Installation writes the app to `~/.local/share/ad-linux-tv`, creates a Python virtual environment and initializes `~/.config/ad-linux-tv/config.yaml` only if absent. The TV Firefox profile is `~/snap/firefox/common/ad-linux-tv-profile`. Plasma autostart is enabled by default; pass `--no-autostart` in both commands when another session manager runs the TV. No root access is required. A new config has phone PIN access off.

Open `http://127.0.0.1:8765/` on the TV. If the graphical session does not autostart it, run:

```sh
~/.local/share/ad-linux-tv/run.sh ~/.config/ad-linux-tv/config.yaml
```

A stable Firefox needs the AMO-signed bridge to control service tabs. A source CI archive has no signed XPI. If you have the signed release archive, its `ad-linux-tv-signed.xpi` is verified against the bundled SHA256 and opened for **interactive confirmation in Firefox** during install. Alternatively supply an HTTPS XPI URL and its SHA256:

```sh
AD_LINUX_TV_XPI_URL='https://example.org/bridge.xpi' \
AD_LINUX_TV_XPI_SHA256='64-hex-character-digest' ./install.sh --install
```

Replace both example values with real release data. The installer does not bypass Firefox signing or approve the add-on automatically. Confirm `ad-linux-tv bridge` is enabled in `about:addons`; then check `http://127.0.0.1:8765/health` for `extension_online: true`.

## Update

Back up `~/.config/ad-linux-tv/config.yaml`, extract the new archive and rerun `./install.sh --dry-run` then `./install.sh --install` with the same autostart choice. Existing config and Firefox profile are preserved. Confirm a new signed bridge update in Firefox if prompted. Restart the TV session after updating the bridge so old browser tabs cannot keep playing behind the tiles.

## Remove

```sh
./uninstall.sh --dry-run
./uninstall.sh --remove
```

Removal keeps the config and Firefox profile, including any signed XPI. Review the preview before removal.
