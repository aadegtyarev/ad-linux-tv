"""Optional, existing CEC hardware only. No adapter configuration or power toggles."""

import os
import stat
import subprocess
from pathlib import Path

TOOL = Path("/usr/bin/cec-ctl")


def available_adapter():
    if not TOOL.is_file() or not os.access(TOOL, os.X_OK):
        return None
    # Fixed, bounded kernel-device names, never a client-supplied path.
    for number in range(4):
        device = Path(f"/dev/cec{number}")
        try:
            info = device.lstat()
            if stat.S_ISCHR(info.st_mode) and os.access(device, os.R_OK | os.W_OK):
                return str(device)
        except OSError:
            pass
    return None


def wake():
    device = available_adapter()
    if device is None:
        return "unavailable"
    try:
        result = subprocess.run(
            [str(TOOL), "--device", device, "--to", "0", "--image-view-on"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        # CLI acceptance is not a physical TV-state observation.
        return "requested" if result.returncode == 0 else "unavailable"
    except subprocess.TimeoutExpired:
        return "uncertain"
    except OSError:
        return "unavailable"
