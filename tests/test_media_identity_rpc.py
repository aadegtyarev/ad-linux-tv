"""Additive media preconditions do not relax the authenticated socket boundary."""

from ad_linux_tv.remote_rpc import RemoteDispatcher


class Media:
    def __init__(self):
        self.calls = []

    def command(self, action, position=None, media_id=None):
        self.calls.append((action, position, media_id))
        if media_id is not None and media_id != "a" * 32:
            raise ValueError("target changed")
        return {"available": True, "playing": False}


def dispatcher(monkeypatch):
    media = Media()
    monkeypatch.setattr("ad_linux_tv.remote_rpc.get_media_monitor", lambda: media)
    instance = RemoteDispatcher(None, {}, None, None, None, None, None, "test-csrf")
    return instance, media


def test_media_rpc_identity_precondition_and_legacy_compatibility(monkeypatch):
    rpc, media = dispatcher(monkeypatch)
    assert rpc.dispatch("POST", "/api/media", {"action": "pause", "media_id": "a" * 32})[0] == 200
    assert media.calls[-1] == ("pause", None, "a" * 32)
    assert rpc.dispatch("POST", "/api/media", {"action": "pause", "media_id": "b" * 32})[0] == 409
    assert rpc.dispatch("POST", "/api/media", {"action": "pause"})[0] == 200
    assert media.calls[-1] == ("pause", None, None)


def test_media_rpc_rejects_malformed_identity_without_dispatch(monkeypatch):
    rpc, media = dispatcher(monkeypatch)
    for identity in (None, True, 7, "", "A" * 32, "a" * 33):
        assert (
            rpc.dispatch("POST", "/api/media", {"action": "pause", "media_id": identity})[0] == 400
        )
    assert rpc.dispatch("POST", "/api/media", {"action": "pause", "extra": True})[0] == 400
    assert media.calls == []
