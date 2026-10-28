"""Deterministic frame-budget policy, not throughput/phone delivery evidence."""

from ad_linux_tv.remote_socket import FrameBudget


def test_budget_bounds_flood_and_replenishes_without_accumulating_unbounded_credit():
    now = [100.0]
    budget = FrameBudget(clock=lambda: now[0])
    assert all(budget.allow() for _ in range(256))
    assert not budget.allow()
    now[0] += 1
    assert all(budget.allow() for _ in range(200))
    assert not budget.allow()
    now[0] += 1000
    assert all(budget.allow() for _ in range(256))
    assert not budget.allow()


def test_budget_allows_normal_ordered_pointer_and_poll_load():
    now = [0.0]
    budget = FrameBudget(clock=lambda: now[0])
    for _ in range(1000):
        now[0] += 0.016
        assert all(budget.allow() for _ in range(3))
