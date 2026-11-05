"""A disposable panel child must exit when its owning session dies."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[1] / "ops/kiosk/video_panel_client.py"
pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not hasattr(os, "pidfd_open"), reason="Linux pidfds required"
)

PARENT = r'''
import os, subprocess, sys, time
child_script = """
import importlib.util, os, sys, time
spec=importlib.util.spec_from_file_location('panel_client',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
if not module.bind_parent(): sys.exit(2)
open(sys.argv[2],'w').write('ready')
time.sleep(30)
"""
env=dict(os.environ,AD_TV_VIDEO_PANEL_PARENT=str(os.getpid()))
child=subprocess.Popen([sys.executable,'-c',child_script,sys.argv[1],sys.argv[2]],env=env)
open(sys.argv[3],'w').write(str(child.pid))
child.wait()
'''


def await_file(path, parent):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        if path.exists():
            return
        if parent.poll() is not None:
            break
        time.sleep(0.02)
    raise AssertionError("synthetic panel did not start")


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGKILL])
def test_panel_exits_after_parent_death(tmp_path, stop_signal):
    ready, pid_file = tmp_path / "ready", tmp_path / "pid"
    parent = subprocess.Popen(
        [sys.executable, "-c", PARENT, str(CLIENT), str(ready), str(pid_file)]
    )
    child_pidfd = None
    try:
        await_file(pid_file, parent)
        pid = int(pid_file.read_text())
        child_pidfd = os.pidfd_open(pid)
        await_file(ready, parent)
        parent.send_signal(stop_signal)
        parent.wait(timeout=5)
        until = time.monotonic() + 5
        while time.monotonic() < until:
            stat = Path(f"/proc/{pid}/stat")
            if not stat.exists() or stat.read_text().split()[2] == "Z":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("synthetic panel survived parent death")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child_pidfd is not None:
            try:
                signal.pidfd_send_signal(child_pidfd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(child_pidfd)
