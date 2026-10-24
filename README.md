# ad-linux-tv

Kubuntu media launcher with a phone remote and a Firefox bridge. Requires Python 3.12.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Use `ad-linux-tv init-config` to create a private PIN verifier configuration, then run `ad-linux-tv`. Install on a target only with `./install.sh --dry-run` first; `--install` prompts for the remote PIN and installs user-scoped files. Default config: `~/.config/ad-linux-tv/config.yaml`; app and dedicated Firefox profile are under `~/.local/share/ad-linux-tv` (`firefox-profile`); Plasma autostart: `~/.config/autostart/ad-linux-tv.desktop`.

Open `/` on the TV and `/remote` from a trusted LAN phone. This MVP uses plain HTTP and is intended only for a trusted home LAN; do not expose it to the Internet. Firefox bridge source is in `extension/`; load temporarily for development. Signed XPI/AMO delivery and Snap persistence are release gates, not currently provided. See [installation](docs/installation.md), [configuration](docs/configuration.md), and [target checklist](docs/target-checklist.md).
