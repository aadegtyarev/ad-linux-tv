"""One public, immutable APK; no request-derived filesystem paths or control locks."""

import hashlib
import os
import socket
import stat
import time
from threading import BoundedSemaphore

from . import security

APK_NAME = "ad-linux-tv-remote-0.2.5-code6.apk"
APK_ROUTE = f"/download/{APK_NAME}"
APK_PATH = f"/usr/local/share/ad-linux-tv/android/{APK_NAME}"
APK_SIZE = 8_800_658
APK_SHA256 = "fe6e335f6b88a1500f1702c6a6bbb57ba0e5b91f849efc9e406a833ce563fa71"
CHUNK_SIZE = 64 * 1024
WRITE_TIMEOUT = 5.0
TOTAL_TIMEOUT = 60.0


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("download deadline")
    return remaining


def _trusted(info, directory=False):
    return (
        info.st_uid == 0
        and not info.st_mode & (0o022 if directory else 0o222)
        and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and (directory or info.st_nlink == 1)
    )


def _verified_file(deadline):
    """Walk pinned directory descriptors, then hash and rewind the SAME independent fd.

    Publisher must use immutable files and atomic rename, never in-place writes.
    O_NONBLOCK prevents a substituted FIFO from stalling before its fstat rejection.
    """
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    artifact = None
    try:
        if not _trusted(os.fstat(directory), directory=True):
            raise OSError("unsafe directory")
        parts = APK_PATH.split("/")[1:]
        for part in parts[:-1]:
            _remaining(deadline)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            if not _trusted(os.fstat(directory), directory=True):
                raise OSError("unsafe directory")
        artifact = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(artifact)
        if not _trusted(before) or before.st_size != APK_SIZE:
            raise OSError("unsafe artifact")
        digest = hashlib.sha256()
        count = 0
        while True:
            _remaining(deadline)
            data = os.read(artifact, min(CHUNK_SIZE, APK_SIZE + 1 - count))
            if not data:
                break
            count += len(data)
            if count > APK_SIZE:
                raise OSError("oversize artifact")
            digest.update(data)
        after = os.fstat(artifact)
        if (
            count != APK_SIZE
            or digest.hexdigest() != APK_SHA256
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or not _trusted(after)
        ):
            raise OSError("invalid artifact")
        os.lseek(artifact, 0, os.SEEK_SET)
        result, artifact = artifact, None
        return result
    finally:
        os.close(directory)
        if artifact is not None:
            os.close(artifact)


class ApkDownload:
    """Shared across this handler's listeners; two workers at most verify/stream.

    Nonblocking admission retains at least 30 of the standard 32 HTTP workers for
    other requests. No verification cache/lock, control lock, or shared file offset.
    All responses here close the connection (including overload and denial).
    """

    def __init__(self):
        self.slots = BoundedSemaphore(2)

    def serve(self, handler):
        deadline = time.monotonic() + TOTAL_TIMEOUT
        handler.close_connection = True
        acquired = False
        artifact = None

        def write(data):
            handler.connection.settimeout(min(WRITE_TIMEOUT, _remaining(deadline)))
            handler.connection.sendall(data)

        def response(status, length, kind="application/json", attachment=False):
            headers = [
                f"HTTP/1.1 {status}\r\n",
                f"Content-Type: {kind}\r\n",
                f"Content-Length: {length}\r\n",
                "Cache-Control: no-store\r\n",
                "X-Content-Type-Options: nosniff\r\n",
                "Connection: close\r\n",
            ]
            if attachment:
                headers.append(f'Content-Disposition: attachment; filename="{APK_NAME}"\r\n')
            write(("".join(headers) + "\r\n").encode("ascii"))

        try:
            if not (
                security.private_source(handler.client_address[0])
                and len(handler.headers.get_all("Host", [])) == 1
                and security.direct_host(
                    handler.headers.get("Host", ""),
                    handler.connection.getsockname()[0],
                    handler.server.server_port,
                )
            ):
                response("403 Forbidden", 2)
                write(b"{}")
                return
            acquired = self.slots.acquire(blocking=False)
            if not acquired:
                response("503 Service Unavailable", 2)
                write(b"{}")
                return
            try:
                artifact = _verified_file(deadline)
            except (OSError, ValueError):
                response("503 Service Unavailable", 2)
                write(b"{}")
                return
            response("200 OK", APK_SIZE, "application/vnd.android.package-archive", True)
            remaining = APK_SIZE
            while remaining:
                _remaining(deadline)
                data = os.read(artifact, min(CHUNK_SIZE, remaining))
                if not data:
                    break
                write(data)
                remaining -= len(data)
        except (OSError, ValueError):
            # No second response after a partial write; never disclose exception/path.
            pass
        finally:
            if artifact is not None:
                os.close(artifact)
            if acquired:
                self.slots.release()
            # No keepalive and no pending buffered body: close also fences pipelining.
            try:
                handler.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
