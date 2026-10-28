"""Public installed version and cached fingerprint of shipped code/assets only."""

import hashlib
import os
import re
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from threading import Lock

_UNKNOWN = "unknown"
_INFO_LOCK = Lock()
_ASSETS = {".js", ".html", ".css", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp", ".wav"}


def package_fingerprint(root):
    """Hash relative names and contents, never mtimes or installation paths.

    Only root Python modules and allowlisted public static assets are inputs.
    Symlinks (including directories) are not followed; any read failure makes
    the entire result unknown rather than advertising a partial build.
    """
    root = Path(root)
    try:
        if root.is_symlink() or not root.is_dir():
            return _UNKNOWN
        files = [
            p for p in root.iterdir() if not p.is_symlink() and p.is_file() and p.suffix == ".py"
        ]
        static = root / "static"
        if not static.is_symlink() and static.exists():

            def failed(error):
                raise error

            for directory, directories, names in os.walk(static, onerror=failed, followlinks=False):
                directories[:] = [
                    name
                    for name in directories
                    if not name.startswith(".")
                    and name != "__pycache__"
                    and not (Path(directory) / name).is_symlink()
                ]
                files.extend(
                    Path(directory) / name
                    for name in names
                    if not name.startswith(".")
                    and Path(name).suffix in _ASSETS
                    and not (Path(directory) / name).is_symlink()
                    and (Path(directory) / name).is_file()
                )
        if not files:
            return _UNKNOWN
        digest = hashlib.sha256()
        for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
            name = path.relative_to(root).as_posix().encode("utf-8")
            content = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big"))
            digest.update(name)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        return digest.hexdigest()[:16]
    except (OSError, UnicodeError):
        return _UNKNOWN


@lru_cache(maxsize=1)
def _installed_info():
    try:
        version = metadata.version("ad-linux-tv")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9.+!_-]{1,80}", version):
            version = _UNKNOWN
    except (metadata.PackageNotFoundError, OSError, ValueError):
        version = _UNKNOWN
    return version, package_fingerprint(Path(__file__).parent)


def server_info():
    """Return a fresh public DTO; cached process-wide data is immutable."""
    with _INFO_LOCK:
        version, build = _installed_info()
    return {"version": version, "build": build}
