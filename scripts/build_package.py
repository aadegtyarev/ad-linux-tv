#!/usr/bin/env python3
"""Build a reproducible source or signed Firefox Linux installation archive."""

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = {"README.md", "LICENSE", "pyproject.toml", "install.sh", "uninstall.sh", "run.sh"}
SOURCE_DIRS = ("src/ad_linux_tv/", "extension/", "ops/kiosk/", "scripts/")
SIGNATURE_FILES = {"META-INF/mozilla.sf", "META-INF/mozilla.rsa"}


def tracked_package_files():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    tracked = (Path(item.decode()) for item in result.stdout.split(b"\0") if item)
    files = [
        path
        for path in tracked
        if path.as_posix() in SOURCE_FILES
        or path.as_posix().startswith(SOURCE_DIRS)
        or (
            path.parent == Path("docs")
            and path.suffix == ".md"
            and path.name != "target-checklist.md"
        )
    ]
    return sorted(files, key=lambda path: path.as_posix())


def validate_signed_xpi(path):
    source_manifest = json.loads((ROOT / "extension/manifest.json").read_text())
    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())
        if not SIGNATURE_FILES <= members:
            raise ValueError("XPI lacks Firefox signature files")
        extension_files = {
            child.name
            for child in (ROOT / "extension").iterdir()
            if child.is_file() and (child.suffix == ".js" or child.name == "manifest.json")
        }
        payload = {name for name in members if not name.startswith("META-INF/")}
        if payload != extension_files:
            raise ValueError("XPI payload differs from extension source")
        if json.loads(archive.read("manifest.json")) != source_manifest:
            raise ValueError("XPI manifest differs from extension source")
        for name in extension_files - {"manifest.json"}:
            if archive.read(name) != (ROOT / "extension" / name).read_bytes():
                raise ValueError(f"XPI source mismatch: {name}")
    return source_manifest["version"]


def add_bytes(archive, name, content, timestamp, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = timestamp
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = mode
    archive.addfile(info, io.BytesIO(content))


def build(output_dir, signed_xpi=None, expect_version=None):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    if expect_version and version != expect_version:
        raise ValueError(f"release tag {expect_version} differs from project version {version}")
    files = tracked_package_files()
    required = {"README.md", "pyproject.toml", "install.sh", "uninstall.sh", "run.sh"}
    if not required <= {path.as_posix() for path in files}:
        raise ValueError("required package files are not tracked")
    extension_version = json.loads((ROOT / "extension/manifest.json").read_text())["version"]
    if signed_xpi and validate_signed_xpi(signed_xpi) != extension_version:
        raise ValueError("signed XPI version differs from extension source")
    timestamp = int(
        os.environ.get("SOURCE_DATE_EPOCH")
        or subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT, text=True
        ).strip()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    release_xpi = None
    if signed_xpi:
        release_xpi = output_dir / f"ad-linux-tv-bridge-{extension_version}-signed.xpi"
        if signed_xpi.resolve() != release_xpi.resolve():
            shutil.copyfile(signed_xpi, release_xpi)
    kind = "linux" if signed_xpi else "source"
    destination = output_dir / f"ad-linux-tv-{version}-{kind}.tar.gz"
    prefix = f"ad-linux-tv-{version}/"
    with destination.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            for path in files:
                source = ROOT / path
                mode = 0o755 if os.access(source, os.X_OK) else 0o644
                add_bytes(archive, prefix + path.as_posix(), source.read_bytes(), timestamp, mode)
            if release_xpi:
                content = release_xpi.read_bytes()
                add_bytes(archive, prefix + "ad-linux-tv-signed.xpi", content, timestamp)
                digest = hashlib.sha256(content).hexdigest().encode() + b"\n"
                add_bytes(archive, prefix + "ad-linux-tv-signed.xpi.sha256", digest, timestamp)
            info = (
                f"Project version: {version}\nFirefox bridge version: {extension_version}\n"
                f"Signed XPI bundled: {'yes' if signed_xpi else 'no'}\n"
            ).encode()
            add_bytes(archive, prefix + "PACKAGE-INFO.txt", info, timestamp)
    artifacts = [destination]
    if release_xpi:
        artifacts.append(release_xpi)
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts
    )
    (output_dir / "SHA256SUMS").write_text(sums)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--signed-xpi", type=Path)
    parser.add_argument("--expect-version")
    args = parser.parse_args()
    print(build(args.output_dir, args.signed_xpi, args.expect_version))


if __name__ == "__main__":
    main()
