# ad-linux-tv

Kubuntu media launcher with a phone remote and a Firefox bridge. Requires Python 3.12.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
node --test tests/layout.test.js
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

For development, use `.venv/bin/ad-linux-tv init-config --config "$HOME/.config/ad-linux-tv/config.yaml"`, then `.venv/bin/ad-linux-tv --config "$HOME/.config/ad-linux-tv/config.yaml"`. After installation, the exact CLI is `~/.local/share/ad-linux-tv/venv/bin/ad-linux-tv --config ~/.config/ad-linux-tv/config.yaml`; graphical autostart invokes `~/.local/share/ad-linux-tv/run.sh`. Install on a target only with `./install.sh --dry-run` first; `--install` prompts for the remote PIN and installs user-scoped files. Default config: `~/.config/ad-linux-tv/config.yaml`; app: `~/.local/share/ad-linux-tv`; Firefox Snap profile: `~/snap/firefox/common/ad-linux-tv-profile`. Plasma autostart is `~/.config/autostart/ad-linux-tv.desktop` unless `--no-autostart` is selected.

Open `/` on the TV and `/remote` from a trusted LAN phone. This MVP uses plain HTTP and is intended only for a trusted home LAN; do not expose it to the Internet. Firefox bridge source is in `extension/`; run `extension/package.sh /tmp/ad-linux-tv-unsigned.zip` to validate and package a development archive, then load temporarily for development. Signed XPI/AMO delivery and Snap persistence are release gates, not currently provided. See [installation](docs/installation.md), [configuration](docs/configuration.md), and [target checklist](docs/target-checklist.md).

For the Beelink target, see [staged TV/KDE deployment](docs/beelink.md). The source checkout remains separate from the installed TV-user copy.
