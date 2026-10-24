"""Ordered bridge queue delivery and retry policy tests."""

import pytest

from ad_linux_tv.control import FAILURE_TTL_SECONDS, CommandQueue, QueueFullError


def test_command_lease_retries_head_and_waits_for_ack():
    queue = CommandQueue()
    queue.push("home")
    queue.push("back")
    first = queue.poll(now=0)[0]
    assert queue.poll(now=1) == []
    assert queue.poll(now=16)[0]["id"] == first["id"]
    assert not queue.acknowledge("wrong-id")
    assert queue.acknowledge(first["id"])
    assert queue.poll(now=17)[0]["command"] == "back"


def test_queue_rejects_new_work_instead_of_dropping_old_commands():
    queue = CommandQueue()
    for _ in range(queue.items.maxlen):
        queue.push("home")
    with pytest.raises(QueueFullError):
        queue.push("back")
    assert queue.poll()[0]["command"] == "home"


@pytest.mark.parametrize(
    ("outcome", "reason"), [("failed", "operation"), ("uncertain", "interrupted")]
)
def test_failure_survives_completed_ack_and_expires_after_bounded_ttl(outcome, reason):
    queue = CommandQueue()
    queue.push("home")
    failed = queue.poll()[0]
    assert queue.acknowledge(failed["id"], outcome, reason)
    queue.push("back")
    completed = queue.poll()[0]
    assert queue.acknowledge(completed["id"])
    assert queue.status()["last_command_failure"] == {"outcome": outcome, "reason": reason}
    assert "recorded_at" not in queue.status()["last_command_failure"]
    queue.last_command_failure["recorded_at"] -= FAILURE_TTL_SECONDS + 1
    assert queue.status()["last_command_failure"] is None


def test_commands_are_ordered_and_allowlisted():
    queue = CommandQueue()
    commands = ("home", "back", "refresh", "up", "down", "left", "right", "ok")
    for command in commands:
        queue.push(command)
    queue.push("open", "youtube")
    delivered = []
    for _ in range(9):
        item = queue.poll()[0]
        delivered.append(item["command"])
        assert queue.acknowledge(item["id"])
    assert delivered == [*commands, "open"]
    for command, service in (("exec", "https://evil.test"), ("open", None), ("home", "vk")):
        with pytest.raises(ValueError):
            queue.push(command, service)
