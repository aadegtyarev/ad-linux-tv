# Install, update and remove

This installs the app for the current user in their normal graphical session. For a computer used only as a TV, see [Dedicated TV computer](kiosk.md).

## Requirements

- A Linux computer with apt and snap (Ubuntu/Kubuntu 24.04+ or similar), see [Tested platforms](platforms.md).
- Python 3.12+ with `venv`, Firefox Snap, a display and a graphical session.

## Install

From an extracted archive or a checkout:

```sh
./install.sh --dry-run
./install.sh --install
```

Add `--no-autostart` to both commands if something else starts the TV page. No root access is needed.

| What | Where |
|---|---|
| App | `~/.local/share/ad-linux-tv` |
| Config | `~/.config/ad-linux-tv/config.yaml` (created only if missing) |
| TV Firefox profile | `~/snap/firefox/common/ad-linux-tv-profile` |

Open `http://127.0.0.1:8765/` on the TV. To start it manually:

```sh
~/.local/share/ad-linux-tv/run.sh ~/.config/ad-linux-tv/config.yaml
```

## Firefox bridge

Service tabs and page-player features need the AMO-signed bridge extension. The source archive does not contain it.

- The signed release archive includes `ad-linux-tv-signed.xpi`; the installer checks its SHA256 and opens it in Firefox for you to confirm.
- Or pass a URL and checksum:

```sh
AD_LINUX_TV_XPI_URL='https://example.org/bridge.xpi' \
AD_LINUX_TV_XPI_SHA256='<64-hex-digest>' ./install.sh --install
```

Then check that `ad-linux-tv bridge` is enabled in `about:addons` and `http://127.0.0.1:8765/health` shows `extension_online: true`.

## Update

Back up `config.yaml`, extract the new archive and run the same `--dry-run` / `--install` commands. Config and Firefox profile are kept. After a bridge update, restart the TV session so old tabs stop playing.

## Remove

```sh
./uninstall.sh --dry-run
./uninstall.sh --remove
```

Config and Firefox profile are kept.
