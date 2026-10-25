"""The downloadable archive contains only portable project files."""

import hashlib
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_package_is_reproducible_and_safe_to_extract(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    prefix = f"ad-linux-tv-{version}"
    archives = []
    for output in (tmp_path / "first", tmp_path / "second"):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_package.py"), "--output-dir", str(output)],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        archive = output / f"{prefix}-source.tar.gz"
        assert archive.is_file()
        assert (output / "SHA256SUMS").read_text().split()[0] == hashlib.sha256(
            archive.read_bytes()
        ).hexdigest()
        archives.append(archive)
    assert archives[0].read_bytes() == archives[1].read_bytes()

    with tarfile.open(archives[0]) as package:
        members = package.getmembers()
        names = {member.name for member in members}
        assert f"{prefix}/install.sh" in names
        assert f"{prefix}/extension/manifest.json" in names
        assert f"{prefix}/scripts/build_package.py" in names
        assert all(member.isfile() for member in members)
        assert all(name.startswith(prefix + "/") for name in names)
        assert not any("/.git/" in name or "/config.yaml" in name for name in names)
        package.extractall(tmp_path / "unpacked", filter="data")
    installer = tmp_path / "unpacked" / prefix / "install.sh"
    subprocess.run([str(installer), "--dry-run"], check=True, capture_output=True)
