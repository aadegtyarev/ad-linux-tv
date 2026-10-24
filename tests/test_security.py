"""Authentication state, network policy, and QR response tests."""

from types import SimpleNamespace

from ad_linux_tv.auth_state import RateLimiter, Sessions
from ad_linux_tv.pages import get_response, remote_address
from ad_linux_tv.security import private_source, remote_url


def test_sessions_expire_and_rate_limiter_is_bounded():
    sessions = Sessions(lifetime=10)
    token, csrf = sessions.create(now=100)
    assert sessions.valid(token, now=109) and sessions.csrf_valid(token, csrf, now=109)
    assert not sessions.valid(token, now=110)
    assert not sessions.csrf_valid(token, csrf, now=110)
    limiter = RateLimiter(max_clients=2)
    limiter.fail("a", now=0)
    assert limiter.locked("a", now=1)
    limiter.fail("b", now=0)
    limiter.fail("c", now=0)
    assert len(limiter.clients) == 2


def test_private_source_and_ipv6_host_validation():
    assert private_source("127.0.0.1") and private_source("192.168.1.2")
    assert not private_source("8.8.8.8")
    assert not private_source("192.0.2.1")
    assert private_source("fc00::1")
    assert not private_source("::ffff:8.8.8.8")
    assert remote_url("[2001:db8::1]:8765", 8765) == "http://[2001:db8::1]:8765/remote"
    assert remote_url("bad.example/path", 8765) is None
    assert remote_url("bad..example", 8765) is None


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
    assert get_response(fake, config, None, ".")[0] == 400
