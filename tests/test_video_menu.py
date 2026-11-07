import threading

import pytest

from ad_linux_tv.control import CommandQueue, QueueFullError
from ad_linux_tv.video_menu import OVERLAY_TIMEOUT, RESULT_TIMEOUT, VideoMenu


class Store:
    def __init__(self):
        self.media_id = "a" * 32
        self.capable = True

    def status(self):
        return {"media_id": self.media_id} if self.media_id else None

    def capabilities(self):
        return ["video_geometry_v1"] if self.capable else []


class Queue:
    def __init__(self):
        self.browser_media = Store()
        self.sent = []
        self.results = {}
        self.failure = None

    def push_geometry(self, media_id, mode, mirror):
        if self.failure:
            raise self.failure
        self.sent.append((media_id, mode, mirror))
        return f"command-{len(self.sent)}"

    def geometry_result(self, command_id):
        return self.results.get(command_id)


def choose(menu, mode, mirror):
    return menu.choose(mode, mirror, menu.snapshot()["revision"])


def apply(menu):
    return menu.apply(menu.snapshot()["revision"])


def test_overlay_heartbeat_expires_and_cannot_claim_visible():
    now = [10.0]
    menu = VideoMenu(Queue(), clock=lambda: now[0])
    assert not menu.overlay_online()
    menu.heartbeat()
    assert menu.overlay_online()
    assert not menu.snapshot()["visible"]
    now[0] += OVERLAY_TIMEOUT + 0.001
    assert not menu.overlay_online()
    now[0] = 9.0
    assert not menu.overlay_online()


def test_delayed_close_cannot_hide_a_new_open_request():
    menu = VideoMenu(Queue())
    stale = menu.open()["opening"]
    latest = menu.open()["opening"]
    assert latest != stale
    with pytest.raises(ValueError):
        menu.close(stale)
    assert menu.snapshot()["visible"]
    assert not menu.close(latest)["visible"]


def test_concurrent_duplicate_apply_admits_at_most_one_command():
    queue = Queue()
    menu = VideoMenu(queue)
    revision = menu.open()["revision"]
    barrier = threading.Barrier(3, timeout=3)
    results = []

    def apply_once():
        barrier.wait()
        try:
            menu.apply(revision)
            results.append("accepted")
        except ValueError:
            results.append("rejected")

    threads = [threading.Thread(target=apply_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    assert sorted(results) == ["accepted", "rejected"]
    assert queue.sent == [("a" * 32, "original", False)]


def test_concurrent_close_reopen_never_retargets_an_old_apply():
    for _ in range(25):
        queue = Queue()
        menu = VideoMenu(queue)
        revision = menu.open()["revision"]
        barrier = threading.Barrier(3, timeout=3)
        errors = []

        def old_apply():
            barrier.wait()
            try:
                menu.apply(revision)
            except ValueError:
                pass
            except Exception as exc:
                errors.append(exc)

        def reopen():
            barrier.wait()
            try:
                menu.close()
                queue.browser_media.media_id = "b" * 32
                menu.open()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=old_apply), threading.Thread(target=reopen)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive()
        assert not errors
        assert len(queue.sent) <= 1
        assert all(item[0] == "a" * 32 for item in queue.sent)


def test_delayed_close_racing_a_reopen_cannot_close_the_new_opening():
    for _ in range(25):
        menu = VideoMenu(Queue())
        first = menu.open()
        barrier = threading.Barrier(3, timeout=3)
        errors = []

        def delayed_close():
            barrier.wait()
            try:
                menu.close(first["opening"])
            except ValueError:
                pass
            except Exception as exc:
                errors.append(exc)

        def reopen():
            barrier.wait()
            try:
                menu.open()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=delayed_close), threading.Thread(target=reopen)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive()
        assert not errors
        assert menu.snapshot()["visible"]
        assert menu.snapshot()["opening"] != first["opening"]


def test_menu_requires_current_video_and_explicit_apply():
    queue = Queue()
    menu = VideoMenu(queue)
    state = menu.open()
    assert {k: v for k, v in state.items() if k not in {"revision", "instance", "opening"}} == {
        "visible": True,
        "available": True,
        "busy": False,
        "mode": "original",
        "mirror": False,
        "status": "choose",
    }
    assert choose(menu, "4:3", True)["status"] == "choose"
    assert queue.sent == []
    assert apply(menu)["status"] == "pending"
    assert queue.sent == [("a" * 32, "4:3", True)]
    with pytest.raises(ValueError):
        apply(menu)
    with pytest.raises(ValueError):
        choose(menu, "16:9", False)


def test_queue_receipt_is_not_completion_and_target_is_rechecked():
    queue = Queue()
    menu = VideoMenu(queue)
    menu.open()
    choose(menu, "16:9", False)
    apply(menu)
    assert menu.snapshot()["status"] == "pending"
    queue.results["command-1"] = {"id": "command-1", "outcome": "completed"}
    assert menu.snapshot()["status"] == "completed"


def test_stale_selection_is_rejected_even_if_new_video_was_polled():
    queue = Queue()
    menu = VideoMenu(queue)
    revision = menu.open()["revision"]
    queue.browser_media.media_id = "b" * 32
    menu.snapshot()
    with pytest.raises(ValueError):
        menu.choose("4:3", True, revision)
    with pytest.raises(ValueError):
        menu.apply(revision)
    assert queue.sent == []
    assert (menu.snapshot()["mode"], menu.snapshot()["mirror"]) == ("original", False)


def test_stale_apply_is_rejected_after_proposal_changes():
    queue = Queue()
    menu = VideoMenu(queue)
    revision = menu.open()["revision"]
    menu.choose("4:3", True, revision)
    with pytest.raises(ValueError):
        menu.apply(revision)
    assert queue.sent == []


def test_delayed_apply_is_rejected_after_pending_resolution_resets_proposal():
    queue = Queue()
    menu = VideoMenu(queue)
    menu.open()
    choose(menu, "4:3", True)
    apply(menu)
    menu.close()
    revision = menu.open()["revision"]
    queue.results["command-1"] = {"id": "command-1", "outcome": "completed"}
    with pytest.raises(ValueError):
        menu.apply(revision)
    assert queue.sent == [("a" * 32, "4:3", True)]


@pytest.mark.parametrize("completed", [True, False])
def test_delayed_duplicate_apply_is_rejected_after_receipt_or_timeout(completed):
    queue = Queue()
    now = [10.0]
    menu = VideoMenu(queue, clock=lambda: now[0])
    revision = menu.open()["revision"]
    menu.apply(revision)
    if completed:
        queue.results["command-1"] = {"id": "command-1", "outcome": "completed"}
    else:
        now[0] += RESULT_TIMEOUT
    menu.snapshot()
    with pytest.raises(ValueError):
        menu.apply(revision)
    assert len(queue.sent) == 1


def test_new_video_resets_choices_but_keeps_pending_until_resolved():
    queue = Queue()
    menu = VideoMenu(queue)
    menu.open()
    choose(menu, "4:3", True)
    apply(menu)
    queue.browser_media.media_id = "b" * 32
    state = menu.snapshot()
    assert (state["mode"], state["mirror"], state["busy"], state["status"]) == (
        "original",
        False,
        True,
        "changed",
    )
    with pytest.raises(ValueError):
        apply(menu)
    assert queue.sent == [("a" * 32, "4:3", True)]


def test_freshness_loss_never_drops_pending_real_queue_command():
    queue = CommandQueue()
    queue.browser_media = Store()
    menu = VideoMenu(queue)
    menu.open()
    apply(menu)
    queue.browser_media.media_id = None
    assert menu.snapshot()["busy"]
    queue.browser_media.media_id = "a" * 32
    assert menu.snapshot()["busy"]
    with pytest.raises(ValueError):
        apply(menu)
    assert len(queue.items) == 1


def test_closed_menu_does_not_replay_and_reopening_resets_proposed_choices():
    queue = Queue()
    menu = VideoMenu(queue)
    old_revision = menu.open()["revision"]
    choose(menu, "4:3", True)
    menu.close()
    assert not queue.sent
    state = menu.open()
    assert (state["mode"], state["mirror"], state["status"]) == ("original", False, "choose")
    with pytest.raises(ValueError):
        menu.choose("4:3", True, old_revision)


def test_resolved_or_resolving_receipt_never_revives_choices_after_reopen():
    for resolves_before_open in (False, True):
        queue = Queue()
        menu = VideoMenu(queue)
        menu.open()
        choose(menu, "4:3", True)
        apply(menu)
        menu.close()
        if resolves_before_open:
            queue.results["command-1"] = {"id": "command-1", "outcome": "completed"}
        state = menu.open()
        if not resolves_before_open:
            assert state["busy"]
            queue.results["command-1"] = {"id": "command-1", "outcome": "completed"}
            state = menu.snapshot()
        assert (state["mode"], state["mirror"], state["status"]) == ("original", False, "choose")
        assert len(queue.sent) == 1


def test_pending_survives_close_and_unconfirmed_result_is_not_replayed():
    queue = Queue()
    now = [10.0]
    menu = VideoMenu(queue, clock=lambda: now[0])
    menu.open()
    apply(menu)
    menu.close()
    assert menu.open()["busy"]
    now[0] += RESULT_TIMEOUT
    assert menu.snapshot()["status"] == "unconfirmed"
    assert len(queue.sent) == 1


@pytest.mark.parametrize("failure", [ValueError(), QueueFullError()])
def test_failed_admission_does_not_claim_success(failure):
    queue = Queue()
    queue.failure = failure
    menu = VideoMenu(queue)
    menu.open()
    assert apply(menu)["status"] == "unavailable"
    assert queue.sent == []


@pytest.mark.parametrize("mode,mirror", [("wide", False), ([], False), ("4:3", 1)])
def test_invalid_selections_are_rejected(mode, mirror):
    menu = VideoMenu(Queue())
    menu.open()
    with pytest.raises(ValueError):
        choose(menu, mode, mirror)


def test_missing_capability_or_media_disables_apply():
    queue = Queue()
    queue.browser_media.capable = False
    menu = VideoMenu(queue)
    assert menu.open()["status"] == "unavailable"
    with pytest.raises(ValueError):
        apply(menu)
    queue.browser_media.capable = True
    queue.browser_media.media_id = None
    assert not menu.snapshot()["available"]


def test_home_ack_only_closes_its_visible_opening():
    queue = CommandQueue()
    menu = VideoMenu(queue)
    menu.open()
    first = menu.push_home()
    second = menu.push_home()
    assert not menu.acknowledge(second, "completed", None, None)
    assert not menu.acknowledge("unknown", "completed", None, None)
    assert menu.snapshot()["visible"]
    assert menu.acknowledge(first, "failed", "operation", None)
    assert menu.snapshot()["visible"]
    menu.open()
    assert menu.acknowledge(second, "completed", None, None)
    assert menu.snapshot()["visible"]
    assert not menu.acknowledge(second, "completed", None, None)
    third = menu.push_home()
    assert menu.acknowledge(third, "completed", None, None)
    assert not menu.snapshot()["visible"]
    menu.open()
    assert not menu.acknowledge(third, "completed", None, None)
    assert menu.snapshot()["visible"]


def test_home_admission_overflow_and_uncertain_do_not_close_or_retry():
    queue = CommandQueue()
    menu = VideoMenu(queue)
    menu.open()
    home = menu.push_home()
    for _ in range(127):
        queue.push("back")
    with pytest.raises(QueueFullError):
        menu.push_home()
    assert len(menu._home_openings) == 1
    assert menu.acknowledge(home, "uncertain", "interrupted", None)
    assert menu.snapshot()["visible"]
    assert len(queue.items) == 127
    assert not menu._home_openings


def test_home_admission_and_ack_serialize_with_reopen(monkeypatch):
    queue = CommandQueue()
    menu = VideoMenu(queue)
    menu.open()
    entered, release = threading.Event(), threading.Event()
    original = queue.push

    def blocked_push(*args):
        entered.set()
        assert release.wait(2)
        return original(*args)

    monkeypatch.setattr(queue, "push", blocked_push)
    ids = []
    admission = threading.Thread(target=lambda: ids.append(menu.push_home()))
    admission.start()
    assert entered.wait(2)
    reopen = threading.Thread(target=menu.open)
    reopen.start()
    release.set()
    admission.join(2)
    reopen.join(2)
    assert not admission.is_alive() and not reopen.is_alive()
    assert menu.acknowledge(ids[0], "completed", None, None)
    assert menu.snapshot()["visible"]


def test_home_ack_and_reopen_are_serialized(monkeypatch):
    queue = CommandQueue()
    menu = VideoMenu(queue)
    menu.open()
    home = menu.push_home()
    entered, release = threading.Event(), threading.Event()
    original = queue.acknowledge

    def blocked_ack(*args):
        entered.set()
        assert release.wait(2)
        return original(*args)

    monkeypatch.setattr(queue, "acknowledge", blocked_ack)
    ack = threading.Thread(target=lambda: menu.acknowledge(home, "completed", None, None))
    ack.start()
    assert entered.wait(2)
    reopen = threading.Thread(target=menu.open)
    reopen.start()
    release.set()
    ack.join(2)
    reopen.join(2)
    assert not ack.is_alive() and not reopen.is_alive()
    assert menu.snapshot()["visible"]


def test_non_home_and_home_admitted_while_hidden_do_not_close_opening():
    queue = CommandQueue()
    menu = VideoMenu(queue)
    home = menu.push_home()
    back = queue.push("back")
    menu.open()
    assert menu.acknowledge(home, "completed", None, None)
    assert menu.acknowledge(back, "completed", None, None)
    assert menu.snapshot()["visible"]


def test_transition_busy_status_is_matching_and_never_replays():
    for result, expected in (
        ({"id": "command-1", "outcome": "failed", "reason": "transition_busy"}, "transition_busy"),
        ({"id": "old-command", "outcome": "failed", "reason": "transition_busy"}, "unavailable"),
        ({"id": "command-1", "outcome": "uncertain", "reason": "transition_busy"}, "unavailable"),
    ):
        queue = Queue()
        menu = VideoMenu(queue)
        menu.open()
        apply(menu)
        queue.results["command-1"] = result
        assert menu.snapshot()["status"] == expected
        assert len(queue.sent) == 1


def test_transition_busy_does_not_override_changed_target():
    queue = Queue()
    menu = VideoMenu(queue)
    menu.open()
    apply(menu)
    queue.browser_media.media_id = "b" * 32
    queue.results["command-1"] = {
        "id": "command-1",
        "outcome": "failed",
        "reason": "transition_busy",
    }
    assert menu.snapshot()["status"] == "changed"
    assert len(queue.sent) == 1
