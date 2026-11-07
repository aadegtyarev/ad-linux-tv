"""No browser, multicast or real bus; bounded fallback/queue compatibility fixtures."""

import json
import time

import pytest
from conftest import login, request

from ad_linux_tv.browser_media import BrowserMedia, choose_media
from ad_linux_tv.control import CommandQueue, QueueFullError
from ad_linux_tv.remote_rpc import RemoteDispatcher
from ad_linux_tv.security import BRIDGE_HEADER, BRIDGE_VALUE


def report(media=None, sequence=None):
    return {
        "protocol": 1,
        "sequence": sequence or int(time.time() * 1000),
        "sent_at": int(time.time() * 1000),
        "capabilities": ["html_media_v1"],
        "media": media,
    }


def snapshot():
    return {
        "media_id": "a" * 32,
        "playing": True,
        "position": 12,
        "duration": 900,
        "can_seek": True,
    }


def test_snapshot_ttl_legacy_absence_and_sequence_fencing():
    store = BrowserMedia()
    assert store.status() is None
    data = report(snapshot())
    store.report(data)
    assert store.status()["source"] == "html"
    assert store.status()["can_next"] is False
    with pytest.raises(ValueError):
        store.report(data)
    assert store.status()["position"] == 12
    store.updated -= 4
    assert store.status() is None
    store.report(report(None, data["sequence"] + 1))
    assert store.status() is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("position", -1),
        ("position", 901),
        ("position", True),
        ("duration", 0),
        ("duration", 86401),
        ("duration", float("inf")),
        ("media_id", "A" * 32),
        ("playing", 1),
        ("can_seek", "true"),
        ("url", "https://private.invalid/"),
    ],
)
def test_invalid_or_private_metadata_rejected(key, value):
    data = snapshot()
    data[key] = value
    with pytest.raises(ValueError):
        BrowserMedia().report(report(data))


def test_stale_reports_and_unknown_protocol_are_not_capability_proof():
    for patch in ({"sent_at": 0}, {"protocol": 2}, {"capabilities": ["eval"]}, {"sequence": True}):
        data = report(snapshot()) | patch
        with pytest.raises(ValueError):
            BrowserMedia().report(data)


def test_prefers_adequate_mpris_and_only_falls_back_when_timing_missing():
    browser = BrowserMedia()
    browser.report(report(snapshot()))
    good = {"available": True, "duration": 800, "position": 3}
    assert choose_media(good, browser.status()) is good
    missing = {"available": True, "duration": None, "position": None}
    assert choose_media(missing, browser.status())["source"] == "html"
    assert choose_media(missing, None) is missing


def test_html_queue_requires_current_id_capability_and_bounded_deadline():
    queue = CommandQueue()
    with pytest.raises(ValueError):
        queue.push_media("seek", "a" * 32, 30)
    queue.browser_media.report(report(snapshot()))
    for action, identity, position in (
        ("toggle", "a" * 32, None),
        ([], "a" * 32, None),
        ("seek", "b" * 32, 30),
        ("seek", "a" * 32, True),
        ("seek", "a" * 32, 901),
        ("pause", "a" * 32, 1),
    ):
        with pytest.raises(ValueError):
            queue.push_media(action, identity, position)
    command_id = queue.push_media("seek", "a" * 32, 30)
    item = queue.poll()[0]
    assert item["media_id"] == "a" * 32 and item["position"] == 30
    assert 0 < item["deadline"] - time.time() * 1000 <= 5000
    assert queue.acknowledge(command_id)  # Existing ledger ACK format, not a playback receipt.
    assert queue.poll() == []
    for _ in range(128):
        queue.push("home")
    with pytest.raises(QueueFullError):
        queue.push_media("pause", "a" * 32)
    assert len(queue.items) == 128


def test_geometry_queue_requires_fresh_capability_and_current_media():
    queue = CommandQueue()
    with pytest.raises(ValueError):
        queue.push_geometry("a" * 32, "4:3", True)
    data = report(snapshot())
    queue.browser_media.report(data)
    with pytest.raises(ValueError):  # An old extension must not receive new commands.
        queue.push_geometry("a" * 32, "4:3", True)
    data = report(snapshot(), data["sequence"] + 1)
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    for identity, mode, mirror in (
        ("b" * 32, "4:3", False),
        ("a" * 32, "stretch-everything", False),
        ("a" * 32, [], False),
        ("a" * 32, "4:3", 1),
    ):
        with pytest.raises(ValueError):
            queue.push_geometry(identity, mode, mirror)
    command_id = queue.push_geometry("a" * 32, "16:9", True)
    item = queue.poll()[0]
    assert item == {
        "id": command_id,
        "command": "video_geometry",
        "service_id": None,
        "media_id": "a" * 32,
        "mode": "16:9",
        "mirror": True,
        "deadline": item["deadline"],
    }
    assert 0 < item["deadline"] - time.time() * 1000 <= 5000
    assert queue.result(command_id) is None  # Enqueue is not proof of application.
    assert queue.acknowledge(command_id, "failed", "no_media")
    assert queue.result(command_id)["outcome"] == "failed"
    assert queue.geometry_notice()
    queue.geometry_notice_until -= 6
    assert not queue.geometry_notice()
    queue.browser_media.updated -= 4
    with pytest.raises(ValueError):
        queue.push_geometry("a" * 32, "original", False)


def test_geometry_queue_is_bounded_and_stores_successful_bridge_receipt():
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    command_id = queue.push_geometry("a" * 32, "original", False)
    assert queue.acknowledge(command_id)
    assert queue.result(command_id) == {
        "id": command_id,
        "outcome": "completed",
        "reason": None,
        "volume": None,
    }
    assert not queue.geometry_notice()
    other = queue.push("home")
    assert queue.acknowledge(other, "failed", "unavailable")
    assert not queue.geometry_notice()
    for _ in range(128):
        queue.push("home")
    with pytest.raises(QueueFullError):
        queue.push_geometry("a" * 32, "4:3", False)


@pytest.mark.parametrize("changed", [False, True])
def test_completed_geometry_receipt_waits_for_new_observation(changed):
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    command_id = queue.push_geometry("a" * 32, "4:3", True)
    assert queue.acknowledge(command_id)
    assert queue.geometry_result(command_id) is None  # Pre-ack snapshot is not confirmation.
    data["sequence"] += 1
    data["sent_at"] = int(time.time() * 1000)
    if changed:
        data["media"] = None
    queue.browser_media.report(data)
    result = queue.geometry_result(command_id)
    assert result["outcome"] == ("failed" if changed else "completed")
    assert result["reason"] == ("no_media" if changed else None)
    assert queue.geometry_notice() is changed


def test_geometry_rpc_exposes_only_bounded_geometry_receipts(monkeypatch):
    class Media:
        def status(self):
            return {"available": False}

    monkeypatch.setattr("ad_linux_tv.remote_rpc.get_media_monitor", Media)
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    rpc = RemoteDispatcher(None, {}, queue, None, None, None, None, "test")
    payload = {"action": "apply", "media_id": "a" * 32, "mode": "4:3", "mirror": False}
    for invalid in (
        payload | {"script": "alert(1)"},
        payload | {"mirror": 1},
        payload | {"mode": "scale(2)"},
        {"action": "result", "id": "../etc/passwd"},
    ):
        assert rpc.dispatch("POST", "/api/video-geometry", invalid)[0] in (400, 409)
    assert rpc.dispatch("GET", "/api/video-geometry", None) == (
        200,
        {"available": True, "media_id": "a" * 32},
    )
    status, body = rpc.dispatch("POST", "/api/video-geometry", payload)
    assert status == 202
    command_id = body["id"]
    assert rpc.dispatch("POST", "/api/video-geometry", {"action": "result", "id": command_id}) == (
        202,
        {},
    )
    assert queue.acknowledge(command_id, "failed", "no_media")
    status, result = rpc.dispatch(
        "POST", "/api/video-geometry", {"action": "result", "id": command_id}
    )
    assert status == 200 and result["outcome"] == "failed"
    other = queue.push("player_get")
    assert queue.acknowledge(other, "completed", None, 50)
    assert rpc.dispatch("POST", "/api/video-geometry", {"action": "result", "id": other}) == (
        202,
        {},
    )


def test_video_notice_is_loopback_only_and_has_no_arbitrary_text(endpoint, monkeypatch):
    connection, port = endpoint
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    monkeypatch.setattr(CommandQueue, "geometry_notice", lambda _self: True)
    response, body = request(
        connection, "GET", "/api/display-timer", headers={"Host": f"127.0.0.1:{port}"}
    )
    assert response.status == 200 and json.loads(body)["video_notice"] is True
    response, _, cookie = login(connection, port)
    assert response.status == 200
    response, body = request(
        connection,
        "GET",
        "/api/display-timer",
        headers={"Host": f"192.168.1.2:{port}", "Cookie": cookie},
    )
    assert response.status == 200 and "video_notice" not in json.loads(body)


def test_rpc_queued_html_action_does_not_claim_observed_playback(monkeypatch):
    class Media:
        def status(self):
            return {"available": False}

        def command(self, *_):
            raise AssertionError("HTML action must not control unrelated MPRIS")

    monkeypatch.setattr("ad_linux_tv.remote_rpc.get_media_monitor", Media)
    queue = CommandQueue()
    queue.browser_media.report(report(snapshot()))
    rpc = RemoteDispatcher(None, {}, queue, None, None, None, None, "test")
    assert rpc.dispatch("GET", "/api/media", None)[1]["source"] == "html"
    assert rpc.dispatch("POST", "/api/media", {"action": "pause"})[0] == 409
    status, observed = rpc.dispatch("POST", "/api/media", {"action": "pause", "media_id": "a" * 32})
    assert status == 202 and observed["playing"] is True
    assert len(queue.items) == 1


def test_report_endpoint_is_loopback_bridge_only_and_rejects_replay(endpoint):
    connection, port = endpoint
    body = json.dumps(report(snapshot()))
    path = "/extension/media"
    assert request(connection, "POST", path, body)[0].status == 403
    bridge = {
        "Host": f"127.0.0.1:{port}",
        BRIDGE_HEADER: BRIDGE_VALUE,
        "Content-Type": "application/json",
    }
    assert request(connection, "POST", path, body, bridge)[0].status == 200
    assert request(connection, "POST", path, body, bridge)[0].status == 400
    assert (
        request(connection, "POST", path, body, dict(bridge, Host="attacker.invalid"))[0].status
        == 403
    )


def test_geometry_busy_receipt_is_exposed_without_private_data():
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    command_id = queue.push_geometry("a" * 32, "4:3", True)
    assert queue.acknowledge(command_id, "failed", "transition_busy")
    assert queue.geometry_result(command_id) == {
        "id": command_id,
        "outcome": "failed",
        "reason": "transition_busy",
    }


def test_geometry_diagnostic_receipt_is_bounded_and_matching():
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)
    command_id = queue.push_geometry("a" * 32, "16:9", False)
    assert not queue.acknowledge("foreign", "failed", "geometry_viewport")
    assert not queue.acknowledge(command_id, "uncertain", "geometry_viewport")
    assert not queue.acknowledge(command_id, "failed", "geometry_unknown")
    assert queue.acknowledge(command_id, "failed", "geometry_viewport")
    assert queue.status()["last_command_failure"] == {
        "outcome": "failed",
        "reason": "unsupported",
    }
    assert queue.geometry_result(command_id)["reason"] == "geometry_viewport"
    assert queue.geometry_failure_reason() == "geometry_viewport"
    assert not queue.acknowledge(command_id, "failed", "geometry_viewport")


def test_latest_geometry_diagnostic_is_fenced_by_admission_and_acknowledgement():
    queue = CommandQueue()
    data = report(snapshot())
    data["capabilities"].append("video_geometry_v1")
    queue.browser_media.report(data)

    first = queue.push_geometry("a" * 32, "16:9", False)
    assert queue.acknowledge(first, "failed", "geometry_viewport")
    assert queue.geometry_failure_reason() == "geometry_viewport"
    second = queue.push_geometry("a" * 32, "4:3", False)
    assert queue.geometry_failure_reason() is None
    assert not queue.acknowledge(first, "failed", "geometry_transition")
    assert queue.geometry_failure_reason() is None
    assert queue.acknowledge(second)
    assert queue.geometry_failure_reason() is None
    assert queue.status()["last_command_failure"]["reason"] == "unsupported"

    older = queue.push_geometry("a" * 32, "16:9", False)
    latest = queue.push_geometry("a" * 32, "4:3", False)
    assert not queue.acknowledge(latest, "failed", "geometry_transition")
    assert queue.acknowledge(older, "failed", "geometry_viewport")
    assert queue.geometry_failure_reason() is None
    assert queue.acknowledge(latest, "failed", "geometry_post_write_exception")
    assert queue.geometry_failure_reason() == "geometry_post_write_exception"
    last = queue.push_geometry("a" * 32, "16:9", False)
    assert queue.geometry_failure_reason() is None
    assert queue.acknowledge(last, "failed", "unsupported")
    assert queue.geometry_failure_reason() is None
