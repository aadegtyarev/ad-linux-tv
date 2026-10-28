"""No browser, multicast or real bus; bounded fallback/queue compatibility fixtures."""

import json
import time

import pytest
from conftest import request

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
