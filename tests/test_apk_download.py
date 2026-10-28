"""Source/ephemeral-loopback checks; no deploy, phone or real actuator evidence."""

import hashlib
import os
import shutil
import socket
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from http.client import HTTPConnection
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest
from conftest import login, make_config, request
from test_remote_socket import connect, receive_message, send_message

from ad_linux_tv import apk_download as apk
from ad_linux_tv.listener import make_server
from ad_linux_tv.server import make_handler


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """Translate only fixture owner/ancestor metadata, not safety predicates/hash/IO."""
    path = tmp_path / apk.APK_NAME
    source = os.path.join(os.getcwd(), ".cache/inputs", apk.APK_NAME)
    if os.path.exists(source):
        shutil.copyfile(source, path)
    else:
        # The curated APK is not in Git; CI serves same-size synthetic bytes under their own digest.
        data = hashlib.sha256(b"ad-linux-tv-apk-fixture").digest() * (apk.APK_SIZE // 32 + 1)
        path.write_bytes(data[: apk.APK_SIZE])
        monkeypatch.setattr(apk, "APK_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    path.chmod(0o444)
    real_fstat = os.fstat
    ancestors = {str(p) for p in path.parents}

    def fixture_stat(fd):
        info = real_fstat(fd)
        target = os.readlink(f"/proc/self/fd/{fd}")
        if target == str(path) or target in ancestors:
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields["st_uid"] = 0
            if target in ancestors:
                fields["st_mode"] &= ~0o022
            return SimpleNamespace(**fields)
        return info

    monkeypatch.setattr(apk.os, "fstat", fixture_stat)
    monkeypatch.setattr(apk, "APK_PATH", str(path))
    return path


def fetch(port, path=apk.APK_ROUTE, headers=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        return request(connection, "GET", path, headers=headers)
    finally:
        connection.close()


def test_exact_actual_bytes_headers_and_independent_parallel_offsets(endpoint, artifact):
    _, port = endpoint
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: fetch(port), range(2)))
    for response, data in results:
        assert response.status == 200
        assert len(data) == apk.APK_SIZE
        assert hashlib.sha256(data).hexdigest() == apk.APK_SHA256
        assert data == artifact.read_bytes()
        assert response.getheader("Content-Type") == "application/vnd.android.package-archive"
        assert response.getheader("Content-Length") == str(apk.APK_SIZE)
        assert response.getheader("Content-Disposition") == f'attachment; filename="{apk.APK_NAME}"'
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert response.getheader("Cache-Control") == "no-store"
        assert response.getheader("Connection") == "close"
        assert response.getheader("Access-Control-Allow-Origin") is None


@pytest.mark.parametrize(
    "path",
    [
        apk.APK_ROUTE + "?x=1",
        apk.APK_ROUTE + "?",
        apk.APK_ROUTE + "/x",
        "/download/../" + apk.APK_NAME,
        "/download/%61d-linux-tv-remote-0.2.5-code6.apk",
        "/download/other.apk",
        "/download/../../config.yaml",
    ],
)
def test_alternate_paths_never_open(endpoint, monkeypatch, path):
    monkeypatch.setattr(apk.os, "open", lambda *a, **kw: pytest.fail("unexpected artifact IO"))
    response, _ = fetch(endpoint[1], path)
    assert response.status == 404


@pytest.mark.parametrize("host", ["attacker.example", "127.0.0.2", "192.168.1.2", "localhost:1"])
def test_wrong_host_rejected_before_io(endpoint, monkeypatch, host):
    monkeypatch.setattr(apk.os, "open", lambda *a, **kw: pytest.fail("unexpected artifact IO"))
    response, body = fetch(endpoint[1], headers={"Host": host})
    assert response.status == 403 and body == b"{}"


@pytest.mark.parametrize(
    "source,hosts",
    [("8.8.8.8", ["127.0.0.1:1234"]), ("127.0.0.1", ["127.0.0.1:1234", "127.0.0.1:1234"])],
)
def test_source_and_duplicate_host_gate_before_io(monkeypatch, source, hosts):
    # A translated peer, not a replacement security predicate or public traffic.
    monkeypatch.setattr(apk.os, "open", lambda *a, **kw: pytest.fail("unexpected artifact IO"))
    headers = Message()
    for host in hosts:
        headers["Host"] = host
    left, right = socket.socketpair()
    handler = SimpleNamespace(
        client_address=(source, 123),
        headers=headers,
        server=SimpleNamespace(server_port=1234),
        connection=SimpleNamespace(
            getsockname=lambda: ("127.0.0.1", 1234),
            settimeout=left.settimeout,
            sendall=left.sendall,
            shutdown=left.shutdown,
        ),
    )
    try:
        apk.ApkDownload().serve(handler)
        assert right.recv(4096).startswith(b"HTTP/1.1 403 Forbidden")
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize(
    "source,accepted",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("192.168.1.2", True),
        ("10.1.2.3", True),
        ("fc00::1", True),
        ("8.8.8.8", False),
        ("169.254.1.1", False),
        ("2001:4860::1", False),
    ],
)
def test_actual_source_predicate(source, accepted):
    assert apk.security.private_source(source) is accepted


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "directory",
        "fifo",
        "symlink",
        "hardlink",
        "writable",
        "short",
        "oversize",
        "corrupt",
        "unreadable",
    ],
)
def test_unavailable_never_sends_bad_bytes(endpoint, artifact, monkeypatch, failure):
    if failure in ("missing", "directory", "fifo", "symlink"):
        artifact.unlink()
        if failure == "directory":
            artifact.mkdir()
        elif failure == "fifo":
            os.mkfifo(artifact)
        elif failure == "symlink":
            artifact.symlink_to("/does-not-exist")
    elif failure == "hardlink":
        os.link(artifact, artifact.with_suffix(".other"))
    elif failure == "writable":
        artifact.chmod(0o644)
    elif failure in ("short", "oversize", "corrupt"):
        artifact.chmod(0o644)
        with artifact.open("r+b") as stream:
            if failure == "short":
                stream.truncate(100)
            elif failure == "oversize":
                stream.truncate(apk.APK_SIZE + 1)
            else:
                stream.write(b"BAD!")
        artifact.chmod(0o444)
    elif failure == "unreadable":
        real_open = os.open

        def denied(path, *args, **kwargs):
            if path == apk.APK_NAME:
                raise PermissionError("private path should not leak")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(apk.os, "open", denied)
    response, body = fetch(endpoint[1])
    assert response.status == 503 and body == b"{}"
    assert response.getheader("Content-Disposition") is None
    assert response.getheader("Content-Length") == "2"


@pytest.mark.parametrize(
    "directory,field,value",
    [
        (False, "st_uid", 1000),
        (False, "st_nlink", 2),
        (False, "st_mode", stat.S_IFREG | 0o464),
        (True, "st_uid", 1000),
        (True, "st_mode", stat.S_IFDIR | 0o775),
        (True, "st_mode", stat.S_IFLNK | 0o755),
    ],
)
def test_real_safety_predicates(directory, field, value):
    info = SimpleNamespace(
        st_uid=0,
        st_mode=(stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o444),
        st_nlink=1,
    )
    assert apk._trusted(info, directory)
    setattr(info, field, value)
    assert not apk._trusted(info, directory)


def test_same_open_inode_survives_atomic_path_replacement(artifact):
    fd = apk._verified_file(time.monotonic() + 3)
    try:
        replacement = artifact.with_suffix(".new")
        replacement.write_bytes(b"wrong")
        replacement.replace(artifact)
        digest = hashlib.sha256()
        while data := os.read(fd, apk.CHUNK_SIZE):
            digest.update(data)
        assert digest.hexdigest() == apk.APK_SHA256
    finally:
        os.close(fd)
    with pytest.raises(OSError):
        apk._verified_file(time.monotonic() + 3)


def test_symlink_ancestor_and_untrusted_owner_fail_closed(endpoint, artifact, monkeypatch):
    link = artifact.parent / "alias"
    link.symlink_to(artifact.parent, target_is_directory=True)
    monkeypatch.setattr(apk, "APK_PATH", str(link / artifact.name))
    assert fetch(endpoint[1])[0].status == 503
    monkeypatch.setattr(apk, "APK_PATH", str(artifact))
    translated_stat = os.fstat

    def bad_owner(fd):
        info = translated_stat(fd)
        if stat.S_ISREG(info.st_mode):
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields["st_uid"] = 1234
            return SimpleNamespace(**fields)
        return info

    monkeypatch.setattr(apk.os, "fstat", bad_owner)
    assert fetch(endpoint[1])[0].status == 503


@pytest.fixture
def slow_server(monkeypatch):
    monkeypatch.setattr(
        "ad_linux_tv.remote_rpc.get_media_monitor",
        lambda: SimpleNamespace(status=lambda: {"available": False}),
    )
    handler = make_handler(make_config())
    original_setup = handler.setup

    def setup(self):
        original_setup(self)
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)

    handler.setup = setup
    server = make_server("127.0.0.1", 0, handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(2)


def slow_client(port):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.settimeout(2)
    sock.connect(("127.0.0.1", port))
    sock.sendall((f"GET {apk.APK_ROUTE} HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n").encode())
    header = bytearray()
    while not header.endswith(b"\r\n\r\n"):
        header.extend(sock.recv(1))
    assert b"200 OK" in header
    return sock


def test_saturation_fast_failure_and_ordered_ws_control_headroom(
    slow_server, artifact, monkeypatch
):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr("ad_linux_tv.post_routes.firefox_active", lambda: True)
    actions = []

    def run(command, **kw):
        actions.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr("ad_linux_tv.post_routes.subprocess.run", run)
    port = slow_server.server_port
    clients = [slow_client(port), slow_client(port)]
    control = HTTPConnection("127.0.0.1", port, timeout=2)
    ws = stream = None
    try:
        start = time.monotonic()
        response, body = fetch(port)
        assert response.status == 503 and body == b"{}"
        assert time.monotonic() - start < 1
        _, result, cookie = login(control, port)
        ws, stream, status = connect(port, cookie, result["csrf"])
        assert " 101 " in status
        for number in range(3):
            send_message(
                ws,
                {
                    "id": number,
                    "method": "POST",
                    "path": "/api/pointer",
                    "body": {"dx": number + 1, "dy": 1},
                },
            )
        replies = [receive_message(stream) for _ in range(3)]
        assert [item["id"] for item in replies] == [0, 1, 2]
        assert [item["status"] for item in replies] == [200] * 3
        assert len(actions) == 3
        assert time.monotonic() - start < 2
    finally:
        for client in clients:
            client.close()
        if stream:
            stream.close()
        if ws:
            ws.close()
        control.close()
    # Disconnects release both slots/fds promptly, not only on the five-second timeout.
    deadline = time.monotonic() + 2
    while True:
        response, data = fetch(port)
        if response.status == 200:
            assert hashlib.sha256(data).hexdigest() == apk.APK_SHA256
            break
        assert time.monotonic() < deadline
        time.sleep(0.02)


@pytest.mark.parametrize("write_timeout,total_timeout", [(0.15, 2), (2, 0.15)])
def test_real_blocked_socket_write_and_total_deadline_cleanup(
    slow_server, artifact, monkeypatch, write_timeout, total_timeout
):
    monkeypatch.setattr(apk, "WRITE_TIMEOUT", write_timeout)
    monkeypatch.setattr(apk, "TOTAL_TIMEOUT", total_timeout)
    port = slow_server.server_port
    clients = [slow_client(port), slow_client(port)]
    try:
        time.sleep(0.4)
        # An admitted transfer (not overload) proves slot cleanup while peers stay open.
        sock = slow_client(port)
        sock.close()
    finally:
        for client in clients:
            client.close()


def test_expired_verification_deadline_closes_fd(artifact):
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(TimeoutError):
        apk._verified_file(time.monotonic() - 1)
    assert len(os.listdir("/proc/self/fd")) == before


@pytest.mark.parametrize("error", ["denied", "overload", "unavailable"])
def test_error_responses_also_have_bounded_socket_writes(artifact, monkeypatch, error):
    monkeypatch.setattr(apk, "WRITE_TIMEOUT", 0.1)
    service = apk.ApkDownload()
    if error == "overload":
        assert service.slots.acquire(False)
        assert service.slots.acquire(False)
    if error == "unavailable":
        artifact.unlink()
    headers = Message()
    headers["Host"] = "127.0.0.1:1234"
    left, right = socket.socketpair()
    left.setblocking(False)
    try:
        while True:
            left.send(b"x" * 4096)
    except BlockingIOError:
        pass
    left.setblocking(True)
    handler = SimpleNamespace(
        client_address=("8.8.8.8" if error == "denied" else "127.0.0.1", 123),
        headers=headers,
        server=SimpleNamespace(server_port=1234),
        connection=SimpleNamespace(
            getsockname=lambda: ("127.0.0.1", 1234),
            settimeout=left.settimeout,
            sendall=left.sendall,
            shutdown=left.shutdown,
        ),
    )
    start = time.monotonic()
    try:
        service.serve(handler)
        assert 0.07 <= time.monotonic() - start < 0.5
        assert handler.close_connection
        if error != "overload":
            assert service.slots.acquire(False)
            assert service.slots.acquire(False)
        assert not service.slots.acquire(False)
    finally:
        left.close()
        right.close()


def test_corrupt_repeated_verification_releases_file_and_directory_fds(artifact):
    artifact.chmod(0o644)
    with artifact.open("r+b") as stream:
        stream.write(b"BAD")
    artifact.chmod(0o444)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(5):
        with pytest.raises(OSError):
            apk._verified_file(time.monotonic() + 3)
    assert len(os.listdir("/proc/self/fd")) == before
