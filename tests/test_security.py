"""Authentication state, network policy, and QR response tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from ad_linux_tv.auth_state import RateLimiter, Sessions
from ad_linux_tv.security import private_source, remote_url


def test_sessions_expire_and_rate_limiter_is_bounded():
    sessions = Sessions(lifetime=10)
    token, csrf = sessions.create(now=100)
    assert sessions.valid(token, now=109) and sessions.csrf_valid(token, csrf, now=109)
    assert not sessions.valid(token, now=110)
    assert not sessions.csrf_valid(token, csrf, now=110)
    limiter = RateLimiter(max_clients=2)
    assert limiter.reserve("a", now=0)
    limiter.complete("a", False, now=0)
    assert limiter.locked("a", now=1)
    assert limiter.reserve("b", now=0)
    limiter.complete("b", True, now=0)
    assert limiter.reserve("c", now=0)
    limiter.complete("c", True, now=0)
    assert len(limiter.clients) == 2


def test_rate_admission_is_atomic_under_parallel_requests():
    limiter = RateLimiter(max_per_client=1, max_inflight=8)
    barrier = Barrier(8)

    def reserve():
        barrier.wait()
        return limiter.reserve("192.168.1.4")

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(accepted) == 1
    limiter.complete("192.168.1.4", None)
    bounded = RateLimiter(max_per_client=4, max_inflight=2)
    assert bounded.reserve("one") and bounded.reserve("two")
    assert not bounded.reserve("three")
    bounded.complete("one", None)
    bounded.complete("two", None)


def test_private_source_and_ipv6_host_validation():
    assert private_source("127.0.0.1") and private_source("192.168.1.2")
    assert not private_source("8.8.8.8")
    assert not private_source("192.0.2.1")
    assert private_source("fc00::1")
    assert not private_source("::ffff:8.8.8.8")
    assert remote_url("[2001:db8::1]:8765", 8765) == "http://[2001:db8::1]:8765/remote"
    assert remote_url("bad.example/path", 8765) is None
    assert remote_url("bad..example", 8765) is None
