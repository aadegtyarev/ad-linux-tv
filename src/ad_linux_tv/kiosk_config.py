"""Render private runtime labwc configuration from the single persistent YAML config."""

import sys
from pathlib import Path
from xml.etree import ElementTree

from .config import load_config
from .settings import atomic_write


def render_labwc(config_path, template, destination):
    config = load_config(config_path)
    tree = ElementTree.parse(template)
    root = tree.getroot()
    if root.tag != "labwc_config":
        raise ValueError("unsupported compositor template")
    node = root.find("magnifier/initScale")
    if node is None:
        raise ValueError("magnifier template missing")
    node.text = format(config.get("magnifier", {"scale": 2.5})["scale"], "g")
    directory = Path(destination)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(directory / "rc.xml", ElementTree.tostring(root, encoding="unicode"))
    return config.get("magnifier", {"scale": 2.5})["scale"]


def main():
    try:
        if len(sys.argv) != 4:
            raise ValueError("expected config, template and destination")
        print(format(render_labwc(*sys.argv[1:]), "g"))
    except (OSError, ValueError, ElementTree.ParseError):
        print("Cannot prepare TV compositor configuration", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
