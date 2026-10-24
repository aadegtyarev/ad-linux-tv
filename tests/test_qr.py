"""QR advertisement policy regression tests."""

from types import SimpleNamespace

from ad_linux_tv import pages
from ad_linux_tv.pages import get_response, remote_address


def test_qr_is_png_with_only_validated_remote_address():
    config = {"port": 8765, "bind": "192.168.1.2"}
    fake = SimpleNamespace(
        path="/api/qr",
        client_address=("127.0.0.1", 80),
        headers={"Host": "127.0.0.1:8765"},
    )
    assert remote_address(fake, config) == "http://192.168.1.2:8765/remote"
    status, image, kind = get_response(fake, config, None, ".")
    assert status == 200 and kind == "image/png" and image.startswith(b"\x89PNG")
    assert b"verifier" not in image and b"salt" not in image
    fake.headers = {"Host": "evil.example/path"}
    assert remote_address(fake, config) == "http://192.168.1.2:8765/remote"
    assert get_response(fake, config, None, ".")[0] == 200


def test_qr_advertisement_matches_listener_family_and_rejects_loopback():
    handler = SimpleNamespace(connection=SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8765)))
    for bind in ("127.0.0.1", "::1"):
        assert remote_address(handler, {"bind": bind, "port": 8765}) == ""
    handler.connection.getsockname = lambda: ("10.0.0.7", 8765)
    assert (
        remote_address(handler, {"bind": "0.0.0.0", "port": 8765}) == "http://10.0.0.7:8765/remote"
    )
    handler.connection.getsockname = lambda: ("127.0.0.1", 8765)
    families = []

    def route(family):
        families.append(family)
        return "fd12::10" if family == pages.socket.AF_INET6 else "192.168.1.8"

    original = pages._route_address
    try:
        pages._route_address = route
        assert (
            remote_address(handler, {"bind": "::", "port": 8765}) == "http://[fd12::10]:8765/remote"
        )
        assert families == [pages.socket.AF_INET6]
        assert (
            remote_address(handler, {"bind": "0.0.0.0", "port": 8765})
            == "http://192.168.1.8:8765/remote"
        )
        assert families[-1] == pages.socket.AF_INET
    finally:
        pages._route_address = original
