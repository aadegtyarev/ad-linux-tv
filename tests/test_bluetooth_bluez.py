"""No host Bluetooth operations: fake bus plus an isolated private D-Bus smoke test."""

import asyncio
import builtins
import dataclasses
import inspect
import shutil
import subprocess
import time

import pytest
from dbus_fast import Message, MessageType, Variant

from ad_linux_tv.bluetooth_bluez import (
    _ADAPTER,
    _AGENT,
    _AGENT_PATH,
    _BLUEZ,
    _DBUS,
    _DEVICE,
    _HID,
    _MATCHES,
    _OM,
    _PROPS,
    BluezTransport,
)

AP = "/org/bluez/hci1"
DP = AP + "/dev_11_22_33_44_55_66"
OTHER = AP + "/dev_22_33_44_55_66_77"


def objects():
    return {
        "/org/bluez/hci0": {_ADAPTER: {"Address": "00:00:00:00:00:00", "Powered": False}},
        AP: {_ADAPTER: {"Address": "AA:BB:CC:DD:EE:FF", "Powered": True}},
        DP: {
            _DEVICE: {
                "Address": "11:22:33:44:55:66",
                "Adapter": AP,
                "AddressType": "public",
                "Name": "Remote",
                "Paired": False,
                "Connected": False,
            }
        },
    }


class FakeBus:
    def __init__(self):
        self.connected = True
        self.calls = []
        self.sent = []
        self.handler = None
        self.exported = None
        self.inventory = objects()
        self.owner = ":1.7"
        self.fail = None
        self.hold = set()
        self.removed = []
        self.unexported = False
        self.serial = 0

    async def factory(self):
        return self

    def add_message_handler(self, handler):
        if self.fail == "handler":
            raise RuntimeError("secret private path")
        self.handler = handler

    def remove_message_handler(self, handler):
        assert handler == self.handler
        self.handler = None

    def export(self, path, service):
        if self.fail == "export":
            raise RuntimeError("secret private path")
        self.exported = service

    def unexport(self, path, service):
        self.unexported = True
        self.exported = None

    def disconnect(self):
        self.connected = False

    def next_serial(self):
        self.serial += 1
        return self.serial

    async def call(self, msg):
        self.calls.append(msg)
        if msg.member in self.hold:
            await asyncio.Future()
        if self.fail == msg.member:
            return Message.new_error(msg, "org.bluez.Error.NotAuthorized", "secret private path")
        if msg.member == "GetNameOwner":
            if self.owner is None:
                return Message.new_error(msg, "org.freedesktop.DBus.Error.NameHasNoOwner", "secret")
            return Message.new_method_return(msg, "s", [self.owner])
        if msg.member == "GetManagedObjects":
            # Fake response permits plain property values; real smoke uses Variants.
            result = Message.new_method_return(msg)
            result.body = [self.inventory]
            return result
        if msg.member == "RemoveMatch":
            self.removed.append(msg.body[0])
        return Message.new_method_return(msg)

    async def send(self, msg):
        if msg.message_type == MessageType.METHOD_CALL:
            reply = await self.call(msg)
            reply.sender = msg.destination
            self.handler(reply)
        else:
            self.sent.append(msg)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def eventually(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


class Lane:
    def __init__(self, bus=None, listener=None):
        self.bus = bus or FakeBus()
        self.clock = Clock()
        self.events = []
        self.transport = BluezTransport(bus_factory=self.bus.factory, clock=self.clock)
        self.transport.start(listener or self.events.append)
        eventually(lambda: self.transport.snapshot().reason != "not_started")

    def invoke(self, fn):
        async def run():
            return fn()

        return asyncio.run_coroutine_threadsafe(run(), self.transport._loop).result(3)

    def signal(self, interface, member, body, path="/", sender=":1.7", signature=""):
        msg = Message.new_signal(path, interface, member, signature, [])
        msg.body = body
        msg.sender = sender
        return self.invoke(lambda: self.bus.handler(msg))

    def properties(self, path=DP, **props):
        self.signal(_PROPS, "PropertiesChanged", [_DEVICE, props, []], path)

    def agent(self, member, signature="", body=None, sender=":1.7"):
        msg = Message(
            destination=":1.2",
            path=_AGENT_PATH,
            interface=_AGENT,
            member=member,
            signature=signature,
            body=body or [],
            serial=1000,
        )
        msg.sender = sender
        return self.invoke(lambda: self.bus.handler(msg))

    def begin(self, kind="pair", op_id="op", deadline=None):
        snapshot = self.transport.snapshot()
        target = snapshot.adapters[0].id if kind == "discover" else snapshot.devices[0].id
        assert getattr(self.transport, kind)(op_id, target, deadline or self.clock() + 60)
        eventually(
            lambda: any(e.kind == "requested" and e.operation_id == op_id for e in self.events)
        )
        return target

    def accepted(self):
        eventually(lambda: any(e.kind == "accepted" for e in self.events))

    def challenge(self):
        eventually(lambda: any(e.kind == "challenge" for e in self.events))
        return [e.challenge for e in self.events if e.kind == "challenge"][-1]

    def close(self):
        self.transport.close()


@pytest.fixture
def lane():
    result = Lane()
    yield result
    result.close()


def test_explicit_start_immutable_dto_and_clean_close():
    bus = FakeBus()
    transport = BluezTransport(bus_factory=bus.factory)
    assert not bus.calls
    assert not transport.pair("x", "x", 1)
    assert transport.snapshot().reason == "not_started"
    events = []
    transport.start(events.append)
    eventually(lambda: transport.snapshot().available)
    snap = transport.snapshot()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.available = False
    assert len(snap.adapters) == 1
    assert snap.adapters[0].address == "AA:BB:CC:DD:EE:FF"
    transport.close()
    count = len(events)
    assert not transport.cancel("x")
    transport.close()
    assert len(events) == count
    assert not bus.connected and bus.handler is None and bus.unexported
    assert set(bus.removed) == set(_MATCHES)
    assert [m.member for m in bus.calls].count("RegisterAgent") == 1
    assert [m.member for m in bus.calls].count("UnregisterAgent") == 1
    assert transport.snapshot().reason == "closed"


def test_pair_accepted_is_not_observed_and_connect_events_are_separate(lane):
    lane.begin()
    lane.accepted()
    assert not lane.transport.snapshot().devices[0].paired
    assert not any(e.kind in {"paired", "connected", "finished"} for e in lane.events)
    lane.properties(Paired=True)
    assert lane.transport.snapshot().devices[0].paired
    assert any(e.kind == "finished" and e.code == "observed" for e in lane.events)
    lane.properties(Connected=True)
    event = [e for e in lane.events if e.kind == "connected"][-1]
    assert event.operation_id is None
    assert event.device_id == lane.transport.snapshot().devices[0].id
    assert not any(m.member in {"Set", "RequestDefaultAgent"} for m in lane.bus.calls)


def test_observed_pair_before_method_reply_is_success_not_acceptance(lane):
    lane.bus.hold.add("Pair")
    lane.begin()
    lane.properties(Paired=True)
    assert any(e.kind == "paired" and e.operation_id == "op" for e in lane.events)
    assert any(e.kind == "finished" and e.code == "observed" for e in lane.events)
    assert not any(e.kind == "accepted" for e in lane.events)
    lane.invoke(lambda: None)
    assert not lane.transport._pending
    assert not any(m.member == "CancelPairing" for m in lane.bus.calls)


@pytest.mark.parametrize(
    "kind,prop,value,event",
    [
        ("connect", "Connected", True, "connected"),
        ("disconnect", "Connected", False, "disconnected"),
    ],
)
def test_connection_observation_correlates_operation(lane, kind, prop, value, event):
    lane.begin(kind)
    lane.accepted()
    lane.properties(**{prop: value})
    observed = [e for e in lane.events if e.kind == event][-1]
    assert observed.operation_id == "op"
    assert observed.controller_epoch == lane.transport.snapshot().controller_epoch
    assert observed.device_epoch == lane.transport.snapshot().devices[0].device_epoch


def test_forget_only_object_removal_is_success(lane):
    lane.begin("forget")
    lane.accepted()
    lane.signal(_PROPS, "PropertiesChanged", [_DEVICE, {}, ["Connected"]], DP)
    assert not any(e.kind == "forgotten" for e in lane.events)
    assert any(e.code == "invalidated" for e in lane.events)
    lane.signal(_OM, "InterfacesAdded", [DP, objects()[DP]])
    lane.begin("forget", "op2")
    lane.accepted()
    lane.signal(_OM, "InterfacesRemoved", [DP, [_DEVICE]])
    assert any(e.kind == "forgotten" and e.operation_id == "op2" for e in lane.events)
    assert not lane.transport.snapshot().devices


@pytest.mark.parametrize(
    "member,signature,body",
    [
        ("RequestPinCode", "o", [DP]),
        ("RequestPasskey", "o", [DP]),
        ("RequestConfirmation", "ou", [DP, 123456]),
        ("RequestAuthorization", "o", [DP]),
        ("DisplayPinCode", "os", [DP, "1234"]),
        ("DisplayPasskey", "ouq", [DP, 123456, 2]),
        ("AuthorizeService", "os", [DP, next(iter(_HID))]),
    ],
)
def test_unsolicited_agent_methods_rejected(lane, member, signature, body):
    result = lane.agent(member, signature, body)
    assert result.message_type == MessageType.ERROR
    assert not any(e.kind == "challenge" for e in lane.events)


@pytest.mark.parametrize(
    "member,signature,body",
    [
        ("RequestPinCode", "o", [OTHER]),
        ("RequestPasskey", "o", [OTHER]),
        ("RequestAuthorization", "o", [OTHER]),
        ("RequestConfirmation", "ou", [OTHER, 123456]),
        ("DisplayPinCode", "os", [OTHER, "secret"]),
        ("DisplayPasskey", "ouq", [OTHER, 123456, 0]),
        ("AuthorizeService", "os", [OTHER, next(iter(_HID))]),
        ("NoSuchMethod", "o", [DP]),
        ("RequestPinCode", "s", [DP]),
    ],
)
def test_unrelated_or_malformed_agent_methods_rejected(lane, member, signature, body):
    lane.begin()
    result = lane.agent(member, signature, body)
    assert result.message_type == MessageType.ERROR
    assert not any(e.kind == "challenge" for e in lane.events)


@pytest.mark.parametrize(
    "member,signature,body,key,value,result",
    [
        ("RequestPinCode", "o", [DP], "pin", "A123", "A123"),
        ("RequestPasskey", "o", [DP], "passkey", "001234", 1234),
        ("RequestConfirmation", "ou", [DP, 123456], "confirm", True, None),
        ("RequestAuthorization", "o", [DP], "confirm", True, None),
    ],
)
def test_agent_answers_exact_challenge(lane, member, signature, body, key, value, result):
    lane.begin()
    assert lane.agent(member, signature, body) is True
    challenge = lane.challenge()
    assert challenge.deadline == 160
    assert lane.transport.answer("op", challenge.id, {key: value})
    eventually(lambda: lane.bus.sent)
    reply = lane.bus.sent[-1]
    assert reply.message_type == MessageType.METHOD_RETURN
    assert reply.body == ([] if result is None else [result])
    assert "A123" not in repr(lane.events)


def test_negative_confirmation_and_stale_answers(lane):
    lane.begin()
    lane.agent("RequestConfirmation", "ou", [DP, 123456])
    challenge = lane.challenge()
    lane.transport.answer("wrong", challenge.id, {"confirm": True})
    lane.transport.answer("op", "wrong", {"confirm": True})
    lane.transport.answer("op", challenge.id, {"pin": "1234"})
    lane.invoke(lambda: None)
    assert not lane.bus.sent
    # A second outstanding callback is rejected rather than retaining another future.
    assert lane.agent("RequestPinCode", "o", [DP]).message_type == MessageType.ERROR
    assert lane.transport.answer("op", challenge.id, {"confirm": False})
    eventually(lambda: lane.bus.sent)
    assert lane.bus.sent[-1].message_type == MessageType.ERROR
    assert lane.transport.cancel("op")
    eventually(lambda: any(e.code == "cancelled" for e in lane.events))
    lane.begin(op_id="replacement")
    lane.agent("RequestPinCode", "o", [DP])
    eventually(lambda: len([e for e in lane.events if e.kind == "challenge"]) == 2)
    lane.transport.answer("op", challenge.id, {"confirm": True})
    lane.invoke(lambda: None)
    assert len(lane.bus.sent) == 1


@pytest.mark.parametrize(
    "member,signature,body,kind,value,entered",
    [
        ("DisplayPinCode", "os", [DP, "1234"], "display_pin", "1234", 0),
        ("DisplayPasskey", "ouq", [DP, 12, 2], "display_passkey", "000012", 2),
    ],
)
def test_display_challenges_are_bounded_and_private(
    lane, member, signature, body, kind, value, entered
):
    lane.begin()
    lane.agent(member, signature, body)
    challenge = lane.challenge()
    eventually(lambda: lane.bus.sent)
    assert (challenge.kind, challenge.value, challenge.entered) == (kind, value, entered)
    assert value not in repr(challenge)
    assert value not in repr(lane.events)
    assert not hasattr(lane.transport.snapshot(), "challenge")


@pytest.mark.parametrize(
    "member,signature,body",
    [
        ("DisplayPinCode", "os", [DP, "x" * 17]),
        ("DisplayPinCode", "os", [DP, "\n"]),
        ("DisplayPasskey", "ouq", [DP, 1000000, 0]),
        ("DisplayPasskey", "ouq", [DP, 1, 7]),
        ("RequestConfirmation", "ou", [DP, 1000000]),
        ("AuthorizeService", "os", [DP, "0000110b-0000-1000-8000-00805f9b34fb"]),
    ],
)
def test_malicious_display_and_non_hid_service_rejected(lane, member, signature, body):
    lane.begin()
    lane.agent(member, signature, body)
    eventually(lambda: lane.bus.sent)
    assert lane.bus.sent[-1].message_type == MessageType.ERROR
    assert not any(e.kind == "challenge" for e in lane.events)


def test_hid_service_requires_exact_owner_and_pair(lane):
    lane.begin()
    assert (
        lane.agent("AuthorizeService", "os", [DP, next(iter(_HID))], sender=":1.99").message_type
        == MessageType.ERROR
    )
    for service in _HID:
        count = len(lane.bus.sent)
        assert lane.agent("AuthorizeService", "os", [DP, service]) is True
        eventually(lambda: len(lane.bus.sent) > count)
        assert lane.bus.sent[-1].message_type == MessageType.METHOD_RETURN


@pytest.mark.parametrize("cancel", ["Cancel", "Release"])
def test_bluez_cancellation_retires_challenge(lane, cancel):
    lane.begin()
    lane.agent("RequestPinCode", "o", [DP])
    challenge = lane.challenge()
    assert lane.agent(cancel).message_type == MessageType.METHOD_RETURN
    lane.transport.answer("op", challenge.id, {"pin": "1234"})
    eventually(lambda: lane.bus.sent)
    assert lane.bus.sent[-1].message_type == MessageType.ERROR
    assert any(e.code == "cancelled" for e in lane.events)
    if cancel == "Release":
        assert not lane.transport.snapshot().available


def test_deadline_cancel_cleanup_no_retry(lane):
    lane.bus.hold.add("Pair")
    lane.begin(deadline=110)
    lane.agent("RequestPasskey", "o", [DP])
    challenge = lane.challenge()
    lane.clock.now = 111
    eventually(lambda: any(e.code == "uncertain" for e in lane.events))
    assert lane.transport.answer("op", challenge.id, {"passkey": "123456"})
    eventually(lambda: any(m.member == "CancelPairing" for m in lane.bus.calls))
    assert [m.member for m in lane.bus.calls].count("Pair") == 1
    assert lane.bus.sent[-1].message_type == MessageType.ERROR


def test_service_epoch_replacement_rejects_stale_owner_answers_and_device_handles(lane):
    old = lane.transport.snapshot()
    lane.begin()
    lane.agent("RequestPinCode", "o", [DP])
    challenge = lane.challenge()
    lane.signal(_DBUS, "NameOwnerChanged", [_BLUEZ, ":1.7", ":1.8"], sender=_DBUS)
    eventually(lambda: lane.transport.snapshot().available)
    new = lane.transport.snapshot()
    assert new.controller_epoch > old.controller_epoch
    assert new.devices[0].id != old.devices[0].id
    assert new.devices[0].device_epoch > old.devices[0].device_epoch
    assert lane.agent("RequestPinCode", "o", [DP]).message_type == MessageType.ERROR
    assert lane.transport.answer("op", challenge.id, {"pin": "1234"})
    assert lane.transport.pair("stale", old.devices[0].id, 150)
    eventually(
        lambda: any(e.operation_id == "stale" and e.code == "invalidated" for e in lane.events)
    )
    assert [m.member for m in lane.bus.calls].count("RegisterAgent") == 2
    assert not any(m.member == "CancelPairing" for m in lane.bus.calls)


@pytest.mark.parametrize(
    "change", ["device", "adapter", "invalid_address", "power", "unknown_adapter", "bad_state"]
)
def test_target_invalidation_retires_agent(lane, change):
    lane.begin()
    lane.agent("RequestPinCode", "o", [DP])
    lane.challenge()
    if change == "device":
        lane.signal(_OM, "InterfacesRemoved", [DP, [_DEVICE]])
    elif change == "adapter":
        lane.signal(_OM, "InterfacesRemoved", [AP, [_ADAPTER]])
    elif change == "invalid_address":
        lane.properties(Address="00:00:00:00:00:00")
    elif change == "unknown_adapter":
        lane.properties(Adapter="/unknown")
    elif change == "bad_state":
        lane.properties(Connected="untrusted" * 10000)
        assert not any(e.kind == "disconnected" for e in lane.events)
    else:
        lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": False}, []], AP)
    assert any(e.code == "invalidated" for e in lane.events)
    assert lane.agent("RequestPinCode", "o", [DP]).message_type == MessageType.ERROR
    eventually(lambda: lane.bus.sent)
    assert lane.bus.sent[-1].message_type == MessageType.ERROR


def test_inventory_names_identity_bounds_and_multiple_adapter_pinning(lane):
    # Explicit off adapter is retained, not silently replaced by working hci1.
    lane.signal(
        _OM,
        "InterfacesAdded",
        ["/org/bluez/hci2", {_ADAPTER: {"Address": "AA:BB:CC:DD:EE:01", "Powered": False}}],
    )
    off = lane.transport.snapshot().adapters[1]
    assert lane.transport.discover("off", off.id, 120)
    eventually(lambda: any(e.code == "adapter_off" for e in lane.events))
    lane.properties(Name="<b>\x00\n" + "🙂" * 1000, Alias="<x>\u202e" + "🙂" * 1000)
    name = lane.transport.snapshot().devices[0].name
    assert name.startswith("<x>") and "\u202e" not in name
    assert len(name) <= 80 and len(name.encode()) <= 160
    assert len(lane.invoke(lambda: lane.transport._devices[DP].props["Alias"]).encode()) <= 160
    for i in range(140):
        lane.signal(
            _OM,
            "InterfacesAdded",
            [
                f"{AP}/dev_{i}",
                {
                    _DEVICE: {
                        "Address": f"22:33:44:55:{i // 256:02X}:{i % 256:02X}",
                        "Adapter": AP,
                        "Name": "x",
                        "Paired": i == 139,
                    }
                },
            ],
        )
    assert len(lane.transport.snapshot().devices) == 64
    assert lane.transport.snapshot().devices[0].paired
    assert lane.invoke(lambda: len(lane.transport._devices)) == 120
    for i in range(12):
        lane.signal(
            _OM,
            "InterfacesAdded",
            [
                f"/org/bluez/hci{i + 3}",
                {_ADAPTER: {"Address": f"AA:BB:CC:DD:EF:{i:02X}", "Powered": True}},
            ],
        )
    assert len(lane.transport.snapshot().adapters) == 8


def test_discovery_cleanup_only_own_session_and_duration_cap(lane):
    lane.begin("discover", deadline=10000)
    lane.accepted()
    assert lane.invoke(lambda: lane.transport._op.deadline) == 130
    assert lane.transport.stop_discovery("unrelated")
    lane.invoke(lambda: None)
    assert not any(m.member == "StopDiscovery" for m in lane.bus.calls)
    assert lane.transport.stop_discovery("op")
    eventually(lambda: any(m.member == "StopDiscovery" for m in lane.bus.calls))
    stop = [m for m in lane.bus.calls if m.member == "StopDiscovery"]
    start = [m for m in lane.bus.calls if m.member == "StartDiscovery"]
    assert len(stop) == len(start) == 1 and stop[0].path == start[0].path == AP


@pytest.mark.parametrize("failure", ["handler", "export", "AddMatch", "RegisterAgent"])
def test_partial_start_failure_redacted_and_cleanup(failure):
    bus = FakeBus()
    bus.fail = failure
    lane = Lane(bus)
    try:
        assert not lane.transport.snapshot().available
        assert "secret" not in repr(lane.events) + repr(lane.transport.snapshot())
    finally:
        lane.close()
    assert not bus.connected and bus.handler is None


def test_service_absent_then_appears_and_bus_loss():
    bus = FakeBus()
    bus.owner = None
    lane = Lane(bus)
    try:
        assert lane.transport.snapshot().reason == "service_unavailable"
        lane.signal(_DBUS, "NameOwnerChanged", [_BLUEZ, "", ":1.8"], sender=_DBUS)
        eventually(lambda: lane.transport.snapshot().available)
        bus.connected = False
        eventually(lambda: lane.transport.snapshot().reason == "bus_unavailable")
        assert not lane.transport.snapshot().devices
    finally:
        lane.close()


def test_unavailable_dependency_is_lazy_and_redacted(monkeypatch):
    transport = BluezTransport()
    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name.startswith("dbus_fast"):
            raise ImportError("private dependency path")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    events = []
    transport.start(events.append)
    eventually(lambda: transport.snapshot().reason == "dependency_unavailable")
    transport.close()
    assert "private" not in repr(events)


def test_command_validation_queue_bound_and_listener_failure():
    bus = FakeBus()
    bus.hold.add("GetNameOwner")
    lane = BluezTransport(bus_factory=bus.factory)
    lane.start(lambda event: None)
    eventually(lambda: lane._loop is not None)
    assert not lane.pair("/path", "x", 110)
    assert not lane.pair("op", "x", float("inf"))
    assert not lane.pair("op", "x", True)
    for answer in (
        {"pin": "\n"},
        {"passkey": 123456},
        {"confirm": 1},
        {"pin": "x", "confirm": True},
        {"pin": ""},
    ):
        assert not lane.answer("op", "challenge", answer)
    assert all(lane.cancel("op") for _ in range(32))
    assert not lane.cancel("op")
    lane.close()
    assert lane._queue.empty() and not lane._thread.is_alive()

    bus = FakeBus()
    events = []

    def listener(event):
        events.append(event)
        if event.kind == "requested":
            raise ValueError("private listener exception")

    other = Lane(bus, listener)
    try:
        target = other.transport.snapshot().devices[0].id
        other.transport.pair("op", target, 150)
        eventually(lambda: any(e.kind == "requested" for e in events))
        assert not any(m.member == "Pair" for m in bus.calls)
        assert other.transport._listener is None
    finally:
        other.close()


def test_close_pending_challenge_suppresses_callbacks(lane):
    lane.begin()
    lane.agent("RequestPinCode", "o", [DP])
    lane.challenge()
    lane.close()
    count = len(lane.events)
    time.sleep(0.06)
    assert len(lane.events) == count
    assert not lane.transport._thread.is_alive()
    assert lane.transport._op is None and lane.transport._agent_task.done()


@pytest.mark.parametrize("interface", [None, "org.bluez.NotAgent1", _PROPS])
def test_agent_interface_cannot_bypass_sender_guard(lane, interface):
    lane.begin()
    msg = Message(
        destination=":1.2",
        path=_AGENT_PATH,
        interface=interface,
        member="RequestPinCode",
        signature="o",
        body=[DP],
        serial=1001,
    )
    msg.sender = ":1.99"
    response = lane.invoke(lambda: lane.bus.handler(msg))
    assert response.message_type == MessageType.ERROR
    assert not any(e.kind == "challenge" for e in lane.events)


@pytest.mark.parametrize("kind", ["connect", "disconnect", "forget"])
def test_cancelling_dispatched_effect_is_uncertain_without_replay(lane, kind):
    lane.bus.hold.add(
        {"connect": "Connect", "disconnect": "Disconnect", "forget": "RemoveDevice"}[kind]
    )
    lane.begin(kind)
    assert lane.transport.cancel("op")
    eventually(lambda: any(e.kind == "finished" and e.code == "uncertain" for e in lane.events))
    assert lane.invoke(lambda: len(lane.transport._pending)) == 0
    assert sum(m.member in {"Connect", "Disconnect", "RemoveDevice"} for m in lane.bus.calls) == 1


def test_same_path_replacement_never_cancels_new_device(lane):
    lane.begin()
    old = lane.transport.snapshot().devices[0]
    lane.properties(Address="22:33:44:55:66:77")
    replacement = lane.transport.snapshot().devices[0]
    assert replacement.id != old.id and replacement.device_epoch > old.device_epoch
    assert any(e.code == "invalidated" for e in lane.events)
    lane.invoke(lambda: None)
    assert not any(m.member == "CancelPairing" for m in lane.bus.calls)


def test_stop_failure_releases_bus_instead_of_leaving_discovery(lane):
    lane.begin("discover")
    lane.accepted()
    lane.bus.fail = "StopDiscovery"
    lane.transport.stop_discovery("op")
    eventually(lambda: not lane.bus.connected)
    eventually(lambda: not lane.transport._thread.is_alive())
    assert any(e.code == "cleanup_failed" for e in lane.events)
    assert not lane.transport.snapshot().available
    assert [m.member for m in lane.bus.calls].count("StartDiscovery") == 1
    assert [m.member for m in lane.bus.calls].count("StopDiscovery") == 1


def test_denied_method_is_fixed_code_and_does_not_reveal_remote_error(lane):
    lane.bus.fail = "Connect"
    lane.begin("connect")
    eventually(lambda: any(e.code == "denied" for e in lane.events))
    assert "secret" not in repr(lane.events)
    assert not any(e.kind == "accepted" for e in lane.events)


def test_irrelevant_property_invalidation_preserves_identity_and_pair(lane):
    lane.begin()
    old = lane.transport.snapshot().devices[0]
    lane.signal(_PROPS, "PropertiesChanged", [_DEVICE, {}, ["RSSI", "TxPower", "Name"]], DP)
    new = lane.transport.snapshot().devices[0]
    assert new.id == old.id and new.name == ""
    assert not any(e.kind == "finished" for e in lane.events)


def test_owner_change_during_initial_query_does_not_restore_old_owner():
    class ReplacingBus(FakeBus):
        async def call(self, msg):
            response = await super().call(msg)
            if msg.member == "GetNameOwner":
                signal = Message.new_signal(
                    "/org/freedesktop/DBus",
                    _DBUS,
                    "NameOwnerChanged",
                    "sss",
                    [_BLUEZ, ":1.7", ":1.8"],
                )
                signal.sender = _DBUS
                self.handler(signal)
            return response

    lane = Lane(ReplacingBus())
    try:
        eventually(lambda: lane.transport.snapshot().available)
        registrations = [m for m in lane.bus.calls if m.member == "RegisterAgent"]
        assert len(registrations) == 1 and registrations[0].destination == ":1.8"
        assert lane.transport._owner == ":1.8"
    finally:
        lane.close()


def test_inventory_during_agent_registration_is_not_lost():
    bus = FakeBus()
    bus.hold.add("RegisterAgent")
    transport = BluezTransport(bus_factory=bus.factory)
    events = []
    transport.start(events.append)
    eventually(lambda: any(m.member == "RegisterAgent" for m in bus.calls))

    async def change():
        msg = Message.new_signal(DP, _PROPS, "PropertiesChanged")
        msg.body = [_DEVICE, {"Connected": True}, []]
        msg.sender = ":1.7"
        bus.handler(msg)
        assert transport._devices[DP].props["Connected"] is True

    try:
        asyncio.run_coroutine_threadsafe(change(), transport._loop).result(3)
    finally:
        transport.close()


@pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="private session daemon unavailable")
def test_real_dbus_fast_private_bus_agent_roundtrip():
    """Real async bus/export/message handling; never connects to the system bus."""
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface

    daemon = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    address = daemon.stdout.readline().strip()
    assert address.startswith("unix:")

    async def scenario():
        service = await MessageBus(bus_address=address).connect()
        outsider = await MessageBus(bus_address=address).connect()
        await service.request_name(_BLUEZ)
        transport = None
        events = []
        registered = asyncio.Event()
        agent_destination = None

        def handle(msg):
            nonlocal agent_destination
            if msg.message_type != MessageType.METHOD_CALL:
                return None
            if msg.member == "GetManagedObjects":
                values = {}
                for path, interfaces in objects().items():
                    values[path] = {
                        interface: {
                            k: Variant(
                                "b" if type(v) is bool else "o" if k == "Adapter" else "s", v
                            )
                            for k, v in props.items()
                        }
                        for interface, props in interfaces.items()
                    }
                return Message.new_method_return(msg, "a{oa{sa{sv}}}", [values])
            if msg.member == "RegisterAgent":
                assert msg.body == [_AGENT_PATH, "KeyboardDisplay"]
                agent_destination = msg.sender
                registered.set()
            return Message.new_method_return(msg)

        service.add_message_handler(handle)

        async def factory():
            return await MessageBus(bus_address=address).connect()

        try:
            transport = BluezTransport(bus_factory=factory)
            transport.start(events.append)
            await asyncio.wait_for(registered.wait(), 3)
            for _ in range(300):
                if transport.snapshot().available:
                    break
                await asyncio.sleep(0.005)
            assert transport.snapshot().available
            # The actually exported methods carry coroutine functions and valid signatures.
            assert all(
                inspect.iscoroutinefunction(m.fn)
                for m in ServiceInterface._get_methods(transport._service)
            )
            target = transport.snapshot().devices[0].id
            transport.pair("op", target, time.monotonic() + 10)
            for _ in range(300):
                if any(e.kind == "accepted" for e in events):
                    break
                await asyncio.sleep(0.005)

            def msg():
                return Message(
                    destination=agent_destination,
                    path=_AGENT_PATH,
                    interface=_AGENT,
                    member="RequestPasskey",
                    signature="o",
                    body=[DP],
                )

            rejected = await outsider.call(msg())
            assert rejected.message_type == MessageType.ERROR
            missing_interface = msg()
            missing_interface.interface = None
            rejected = await outsider.call(missing_interface)
            assert rejected.message_type == MessageType.ERROR
            pending = asyncio.create_task(service.call(msg()))
            for _ in range(300):
                if any(e.kind == "challenge" for e in events):
                    break
                await asyncio.sleep(0.005)
            challenge = [e.challenge for e in events if e.kind == "challenge"][-1]
            assert transport.answer("op", challenge.id, {"passkey": "001234"})
            result = await asyncio.wait_for(pending, 3)
            assert result.message_type == MessageType.METHOD_RETURN and result.body == [1234]
        finally:
            if transport:
                await asyncio.to_thread(transport.close)
            service.disconnect()
            outsider.disconnect()

    try:
        asyncio.run(scenario())
    finally:
        daemon.terminate()
        daemon.wait(timeout=3)
        daemon.stdout.close()
