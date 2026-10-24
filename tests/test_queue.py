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


def test_player_volume_results_are_correlated_and_bounded():
    from ad_linux_tv.control import MAX_RESULTS, RESULT_TTL_SECONDS

    queue = CommandQueue()
    for invalid in (-1, 101, True, "50", None):
        with pytest.raises(ValueError):
            queue.push("player_set", volume=invalid)
    with pytest.raises(ValueError):
        queue.push("home", volume=50)
    read_id = queue.push("player_get")
    assert queue.poll()[0]["id"] == read_id
    assert not queue.acknowledge(read_id)
    assert queue.acknowledge(read_id, volume=35)
    assert queue.result(read_id) == {
        "id": read_id,
        "outcome": "completed",
        "reason": None,
        "volume": 35,
    }
    for value in range(MAX_RESULTS + 1):
        command_id = queue.push("player_set", volume=value % 101)
        item = queue.poll()[0]
        assert item["id"] == command_id and item["volume"] == value % 101
        assert queue.acknowledge(command_id, volume=value % 101)
    assert queue.result(read_id) is None
    assert len(queue.results) == MAX_RESULTS
    latest_id = command_id
    queue.results[latest_id]["recorded_at"] -= RESULT_TTL_SECONDS + 1
    assert queue.result(latest_id) is None
