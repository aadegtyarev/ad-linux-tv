"""Adapter policy tests use fake inventory and never touch the system bus."""

from dataclasses import replace

import pytest
from test_bluetooth_manager import A0, A1, OTHER, Adapter, Rig

from ad_linux_tv.bluetooth_schema import validate_bluetooth


@pytest.fixture
def rig():
    instance = Rig()
    instance.start()
    instance.acquire()
    yield instance
    instance.manager.close()


def test_explicit_preference_survives_loss_return_and_preserves_remote(rig):
    rig.settings.saved_remote()
    rig.transport.state = replace(
        rig.transport.state, adapters=(Adapter(id="first", address=A0), Adapter())
    )
    state = rig.state()
    assert state["adapter"]["id"] == "hci1"  # legacy saved remote
    status, reply = rig.request("select_adapter", adapter_id="first", revision=state["revision"])
    assert status == 200
    assert rig.settings.section["adapter"] == A0
    assert rig.settings.section["remote"]["identity"]["adapter"] == A1
    assert reply["state"]["adapter"]["id"] == "first"
    assert reply["state"]["remote"]["device_id"] is None
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(),))
    assert rig.state()["adapter"] is None
    rig.transport.state = replace(
        rig.transport.state, adapters=(Adapter(id="new", address=A0), Adapter())
    )
    assert rig.state()["adapter"]["id"] == "new"
    status, _ = rig.request("adapter_auto", revision=rig.state()["revision"])
    assert status == 200 and "adapter" not in rig.settings.section
    assert rig.state()["adapter"]["id"] == "hci1"


def test_recreated_manager_restores_preference_and_does_not_guess_duplicates():
    rig = Rig()
    rig.settings.section = {"remote": None, "adapter": A0}
    rig.transport.state = replace(
        rig.transport.state, adapters=(Adapter(id="new", address=A0), Adapter())
    )
    rig.start()
    rig.acquire()
    try:
        assert rig.state()["adapter"]["id"] == "new"
        rig.transport.state = replace(
            rig.transport.state,
            adapters=(Adapter(id="one", address=A0), Adapter(id="two", address=A0)),
        )
        state = rig.state()
        assert state["adapter"] is None
        assert all(not a["selectable"] for a in state["adapters"])
        assert rig.request("select_adapter", adapter_id="one", revision=state["revision"])[0] == 409
    finally:
        rig.manager.close()


def test_selection_is_leased_revision_fenced_and_busy(rig):
    state = rig.state()
    assert (
        rig.manager.request(
            OTHER,
            {
                "op": "select_adapter",
                "lease": rig.lease,
                "adapter_id": "hci1",
                "revision": state["revision"],
            },
        )[0]
        == 403
    )
    assert (
        rig.request("select_adapter", adapter_id="hci1", revision=state["revision"] + 1)[0] == 409
    )
    rig.begin("discover")
    assert (
        rig.request("select_adapter", adapter_id="hci1", revision=rig.state()["revision"])[0] == 409
    )
    assert not rig.settings.saves


def test_power_requires_explicit_selection_and_observed_property(rig):
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(powered=False),))
    assert rig.request("power_on", adapter_id="invalid")[0] == 409
    status, response = rig.request("power_on", adapter_id="hci1")
    assert status == 202
    operation = response["state"]["operation"]["id"]
    assert rig.transport.calls[-1][0] == "power_on"
    rig.emit("requested", operation, device_id=None, device_epoch=0)
    rig.emit("accepted", operation, device_id=None, device_epoch=0)
    assert not rig.state()["adapter"]["powered"]
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(powered=True),))
    rig.emit("powered", operation, device_id=None, device_epoch=0)
    rig.manager.tick()
    assert rig.state()["adapter"]["powered"]
    assert rig.state()["operation"]["phase"] == "observed"


@pytest.mark.parametrize("op", ["select_adapter", "adapter_auto", "power_on"])
def test_external_discovery_blocks_adapter_changes_until_it_stops(rig, op):
    rig.transport.state = replace(
        rig.transport.state,
        adapters=(Adapter(powered=False), Adapter(id="other", address=A0, discovering=True)),
    )
    fields = {
        "select_adapter": {"adapter_id": "hci1", "revision": rig.state()["revision"]},
        "adapter_auto": {"revision": rig.state()["revision"]},
        "power_on": {"adapter_id": "hci1"},
    }[op]
    assert rig.request(op, **fields)[0] == 409
    assert not rig.transport.calls and not rig.settings.saves
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(powered=False),))
    assert rig.request(op, **fields)[0] in (200, 202)


def test_legacy_saved_remote_is_not_guessed_with_duplicate_adapters(rig):
    rig.settings.saved_remote()
    rig.transport.state = replace(
        rig.transport.state, adapters=(Adapter(id="one"), Adapter(id="two"))
    )
    assert rig.state()["adapter"] is None
    assert rig.state()["remote"]["device_id"] is None
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(),))
    assert rig.state()["adapter"]["id"] == "hci1"


@pytest.mark.parametrize("adapter", [None, "bad", "00:00:00:00:00:00", "aa:bb:cc:dd:ee:ff"])
def test_invalid_adapter_config_rejected(adapter):
    with pytest.raises(ValueError):
        validate_bluetooth({"remote": None, "adapter": adapter})
