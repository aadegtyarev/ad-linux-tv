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
        self.tasks = set()
        self.discovery_sessions = set()
        self.disconnects = 0

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
        self.disconnects += 1
        self.connected = False
        self.discovery_sessions.clear()
        for task in self.tasks:
            task.cancel()

    async def wait_for_disconnect(self):
        assert not self.connected

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
        if msg.member == "StartDiscovery":
            self.discovery_sessions.add(msg.path)
        if msg.member == "StopDiscovery":
            self.discovery_sessions.discard(msg.path)
        if msg.member == "RemoveMatch":
            self.removed.append(msg.body[0])
        return Message.new_method_return(msg)

    def send(self, msg):
        # Normal writes complete independently of the service method's reply.
        written = asyncio.get_running_loop().create_future()
        if not self.connected:
            raise ConnectionError("closed")
        written.set_result(None)
        self.deliver(msg)
        return written

    def deliver(self, msg):
        if msg.message_type == MessageType.METHOD_CALL:
            task = asyncio.create_task(self.respond(msg))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        else:
            self.sent.append(msg)

    async def respond(self, msg):
        reply = await self.call(msg)
        reply.sender = msg.destination
        if self.connected and self.handler:
            self.handler(reply)


class BackpressuredBus(FakeBus):
    """Like dbus-fast: send queues bytes immediately; cancelling its Future
    cannot retract them, and a writable socket could deliver them much later.
    """

    def __init__(self):
        super().__init__()
        self.block_members = set()
        self.block_replies = False
        self.buffered = []
        self.max_buffered = 0
        self.queued = []
        self.writes = []

    def send(self, msg):
        if not self.connected:
            raise ConnectionError("closed")
        if msg.member in self.block_members or (
            self.block_replies
            and msg.message_type in {MessageType.METHOD_RETURN, MessageType.ERROR}
        ):
            written = asyncio.get_running_loop().create_future()
            self.buffered.append((msg, written))
            self.writes.append(written)
            self.queued.append(msg)
            self.max_buffered = max(self.max_buffered, len(self.buffered))
            return written
        return super().send(msg)

    def drain(self):
        if not self.connected:
            return
        for msg, written in self.buffered:
            # Delivers serialized bytes even when the send Future was cancelled.
            self.deliver(msg)
            if not written.done():
                written.set_result(None)
        self.buffered.clear()

    def disconnect(self):
        super().disconnect()
        for _, written in self.buffered:
            if not written.done():
                written.cancel()
        self.buffered.clear()


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
        self.request_serial = 1000
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
            serial=self.request_serial,
        )
        self.request_serial += 1
        msg.sender = sender
        return self.message(msg)

    def message(self, msg):
        def dispatch():
            before = self.transport._agent_replies.qsize()
            result = self.bus.handler(msg)
            return result, self.transport._agent_replies.qsize() > before

        result, queued = self.invoke(dispatch)
        if queued:
            eventually(
                lambda: (
                    any(reply.reply_serial == msg.serial for reply in self.bus.sent)
                    or not self.bus.connected
                )
            )
            return next(
                (reply for reply in self.bus.sent if reply.reply_serial == msg.serial), result
            )
        return result

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
    eventually(lambda: not lane.bus.connected)
    assert not lane.transport.forget("op2", "stale", 150)


def test_forget_observed_removal_is_success(lane):
    lane.begin("forget")
    lane.accepted()
    lane.signal(_OM, "InterfacesRemoved", [DP, [_DEVICE]])
    assert any(e.kind == "forgotten" and e.operation_id == "op" for e in lane.events)
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
    assert len(lane.bus.sent) == 2


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
    if change not in {"power", "bad_state"}:
        eventually(lambda: not lane.bus.connected)
        assert not lane.transport.pair("replacement", "stale", 150)
    else:
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
    device = lane.transport.snapshot().devices[0]
    assert device.name.startswith("<b>") and device.bluez_name == device.name
    assert device.alias.startswith("<x>") and "\u202e" not in device.alias
    for name in (device.name, device.bluez_name, device.alias):
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
    response = lane.message(msg)
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
    lane.properties(Address="22:33:44:55:66:77")
    assert any(e.code == "invalidated" for e in lane.events)
    eventually(lambda: not lane.bus.connected)
    assert not lane.transport.snapshot().available
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


def assert_retired_connection(lane):
    eventually(lambda: not lane.bus.connected)
    lane.close()
    assert lane.bus.handler is None and lane.bus.exported is None
    assert not lane.bus.discovery_sessions
    assert not lane.transport._thread.is_alive()
    assert not lane.transport._pending and not lane.transport._writes
    assert lane.transport._op is None and lane.transport._discovery is None
    assert lane.transport._cleanup_op is None
    assert lane.transport._agent_replies.empty()
    assert all(task.done() for task in lane.bus.tasks)
    if isinstance(lane.bus, BackpressuredBus):
        assert not lane.bus.buffered
        lane.bus.drain()  # A later writable socket must never replay on a new bus.
    count = len(lane.events)
    for i in range(20):
        assert not lane.transport.cancel(f"retired_{i}")
        assert not lane.transport.connect(f"retired_{i}", "stale", 150)
    assert len(lane.events) == count


@pytest.mark.parametrize(
    "change",
    [
        "powered_invalidated",
        "discovering_invalidated",
        "address_replaced",
        "zero_address",
        "invalid_address",
        "removed",
    ],
)
def test_discovery_logical_adapter_loss_releases_owned_session(change):
    lane = Lane()
    try:
        lane.begin("discover")
        lane.accepted()
        assert lane.bus.discovery_sessions == {AP}
        if change.endswith("invalidated"):
            prop = "Powered" if change == "powered_invalidated" else "Discovering"
            lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {}, [prop]], AP)
        elif change == "removed":
            lane.signal(_OM, "InterfacesRemoved", [AP, [_ADAPTER]])
        else:
            address = {
                "address_replaced": "AA:BB:CC:DD:EE:01",
                "zero_address": "00:00:00:00:00:00",
                "invalid_address": "invalid",
            }[change]
            lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Address": address}, []], AP)
        assert_retired_connection(lane)
        assert [m.member for m in lane.bus.calls].count("StartDiscovery") == 1
        assert not any(m.member == "StopDiscovery" for m in lane.bus.calls)
    finally:
        lane.close()


@pytest.mark.parametrize("kind", ["discover", "pair"])
@pytest.mark.parametrize("replacement", ["address", "opaque_id", "epoch", "missing"])
@pytest.mark.parametrize(
    "retirement",
    ["cancel", "expiry", "dispatch_failure", "listener", "agent_cancel", "agent_release"],
)
def test_deferred_cleanup_fences_original_adapter_instance(kind, replacement, retirement):
    lane = Lane()
    try:
        lane.begin(kind)
        lane.accepted()

        def retire_and_replace():
            transport = lane.transport
            op = transport._op
            original = transport._adapters[AP]
            assert op.adapter_id == original.id and op.adapter_epoch == original.epoch
            if retirement == "cancel":
                transport._command("cancel", "op", ())
            elif retirement in {"agent_cancel", "agent_release"}:
                transport._release_agent("Cancel" if retirement == "agent_cancel" else "Release")
            elif retirement == "listener":

                def broken(_):
                    raise ValueError("private listener detail")

                transport._listener = broken
                transport._emit("inventory")
            else:
                transport._retire("uncertain" if retirement == "expiry" else "failed")
            assert transport._cleanup_op is op  # cleanup cannot run within this loop turn
            if replacement == "address":
                transport._add(AP, _ADAPTER, {"Address": "AA:BB:CC:DD:EE:01", "Powered": True})
            elif replacement == "opaque_id":
                transport._adapters[AP] = dataclasses.replace(original, id="replacement")
            elif replacement == "epoch":
                transport._adapters[AP] = dataclasses.replace(original, epoch=original.epoch + 1)
            else:
                transport._adapters.pop(AP)

        lane.invoke(retire_and_replace)
        assert_retired_connection(lane)
        assert not any(m.member in {"StopDiscovery", "CancelPairing"} for m in lane.bus.calls)
    finally:
        lane.close()


@pytest.mark.parametrize("kind,member", [("discover", "StopDiscovery"), ("pair", "CancelPairing")])
def test_adapter_replacement_aborts_already_buffered_cleanup(kind, member):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        lane.begin(kind)
        lane.accepted()
        bus.block_members.add(member)
        lane.transport.cancel("op")
        eventually(lambda: len(bus.buffered) == 1)
        lane.signal(
            _PROPS, "PropertiesChanged", [_ADAPTER, {"Address": "AA:BB:CC:DD:EE:01"}, []], AP
        )
        assert_retired_connection(lane)
        assert bus.max_buffered == 1
        assert not any(m.member == member for m in bus.calls)
    finally:
        lane.close()


def test_device_replacement_before_pair_cleanup_disconnects_without_cancelling_replacement():
    lane = Lane()
    try:
        lane.begin()
        lane.accepted()

        def replace():
            lane.transport._retire("cancelled")
            lane.transport._add(
                DP, _DEVICE, {**objects()[DP][_DEVICE], "Address": "22:33:44:55:66:77"}
            )

        lane.invoke(replace)
        assert_retired_connection(lane)
        assert not any(m.member == "CancelPairing" for m in lane.bus.calls)
    finally:
        lane.close()


@pytest.mark.parametrize(
    "kind,member",
    [("connect", "Connect"), ("disconnect", "Disconnect"), ("forget", "RemoveDevice")],
)
@pytest.mark.parametrize(
    "retirement", ["cancel", "expire", "device_invalidated", "observed", "shutdown"]
)
def test_unconfirmed_command_write_retires_connection_without_growth_or_replay(
    kind, member, retirement
):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        bus.block_members.add(member)
        lane.begin(kind)
        eventually(lambda: len(bus.buffered) == 1)
        if retirement == "cancel":
            lane.transport.cancel("op")
        elif retirement == "expire":
            lane.clock.now = 1000
        elif retirement == "device_invalidated":
            lane.signal(_PROPS, "PropertiesChanged", [_DEVICE, {}, ["Address"]], DP)
        elif retirement == "observed":
            if kind == "forget":
                lane.signal(_OM, "InterfacesRemoved", [DP, [_DEVICE]])
            else:
                lane.properties(Connected=kind == "connect")
        else:
            lane.close()
        assert_retired_connection(lane)
        assert bus.max_buffered == 1
        assert len([m for m in bus.queued if m.member == member]) == 1
        assert not any(m.member == member for m in bus.calls)
        assert not any(e.kind == "accepted" for e in lane.events)
        if retirement != "shutdown":
            assert any(e.kind == "finished" and e.code == "uncertain" for e in lane.events)
            assert not any(e.kind == "finished" and e.code == "observed" for e in lane.events)
    finally:
        lane.close()


@pytest.mark.parametrize(
    "kind,member",
    [("connect", "Connect"), ("disconnect", "Disconnect"), ("forget", "RemoveDevice")],
)
def test_confirmed_write_retirement_does_not_confuse_pending_method_reply_with_buffer(kind, member):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        bus.block_members.add(member)
        bus.hold.add(member)
        lane.begin(kind)
        eventually(lambda: len(bus.buffered) == 1)

        def drain_then_cancel():
            bus.drain()
            assert lane.transport._op.write.done()
            lane.transport._command("cancel", "op", ())

        lane.invoke(drain_then_cancel)
        eventually(lambda: not lane.transport._pending and not lane.transport._writes)
        assert bus.connected and not bus.buffered
        assert any(e.code == "uncertain" for e in lane.events)
        assert sum(m.member == member for m in bus.calls) == 1
    finally:
        lane.close()


def incoming_agent(member="RequestPinCode", *, serial=5000):
    message = Message(
        destination=":1.2",
        path=_AGENT_PATH,
        interface=_AGENT,
        member=member,
        signature="o",
        body=[DP],
        serial=serial,
    )
    message.sender = ":1.7"
    return message


@pytest.mark.parametrize("retirement", ["cancel", "expire", "invalidate", "observed", "shutdown"])
def test_unconfirmed_secret_agent_reply_never_survives_retirement(retirement):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        lane.begin()
        bus.block_replies = True
        lane.agent("RequestPinCode", "o", [DP])
        challenge = lane.challenge()
        lane.transport.answer("op", challenge.id, {"pin": "privatePin"})
        eventually(lambda: len(bus.buffered) == 1)
        assert bus.buffered[0][0].body == ["privatePin"]
        if retirement == "cancel":
            lane.transport.cancel("op")
        elif retirement == "expire":
            lane.clock.now = 1000
        elif retirement == "invalidate":
            lane.signal(_OM, "InterfacesRemoved", [DP, [_DEVICE]])
        elif retirement == "observed":
            lane.properties(Paired=True)
        else:
            lane.close()
        assert_retired_connection(lane)
        assert bus.max_buffered == 1
        assert not any(msg.body == ["privatePin"] for msg in bus.sent)
        assert "privatePin" not in repr(lane.events)
        if retirement != "shutdown":
            assert any(e.kind == "finished" and e.code == "uncertain" for e in lane.events)
    finally:
        lane.close()


@pytest.mark.parametrize("mode", ["timeout", "overflow"])
def test_unsolicited_agent_reply_writer_is_bounded_and_fails_closed(mode):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        bus.block_replies = True
        lane.invoke(lambda: bus.handler(incoming_agent()))  # rejected; no active pair
        eventually(lambda: len(bus.buffered) == 1)
        if mode == "overflow":

            def flood():
                for i in range(20):
                    if bus.connected:
                        bus.handler(incoming_agent(serial=5001 + i))

            lane.invoke(flood)
        assert_retired_connection(lane)
        assert bus.max_buffered == 1
        assert not bus.sent
        assert not any(e.kind == "challenge" for e in lane.events)
    finally:
        lane.close()


def test_backpressured_fixture_keeps_serialized_bytes_after_future_cancel():
    async def scenario():
        bus = BackpressuredBus()
        bus.block_members.add("Connect")
        message = Message(
            destination=":1.7", path=DP, interface=_DEVICE, member="Connect", serial=1
        )
        write = bus.send(message)
        write.cancel()
        assert len(bus.buffered) == 1
        bus.drain()
        await asyncio.sleep(0)
        assert [msg.member for msg in bus.calls] == ["Connect"]
        bus.disconnect()

    asyncio.run(scenario())


def test_service_owner_replacement_cannot_abandon_discovery_on_surviving_old_service():
    lane = Lane()
    try:
        lane.begin("discover")
        lane.accepted()
        assert lane.bus.discovery_sessions == {AP}
        lane.signal(_DBUS, "NameOwnerChanged", [_BLUEZ, ":1.7", ":1.8"], sender=_DBUS)
        assert_retired_connection(lane)
        assert [msg.member for msg in lane.bus.calls].count("RegisterAgent") == 1
        assert not any(msg.member == "StopDiscovery" for msg in lane.bus.calls)
    finally:
        lane.close()


def test_shutdown_discards_agent_reply_queued_before_writer_starts(lane):
    lane.begin()
    lane.accepted()

    def queue_then_close():
        reply = Message(
            message_type=MessageType.METHOD_RETURN,
            reply_serial=9000,
            destination=":1.7",
            signature="s",
            body=["privatePin"],
        )
        lane.transport._queue_agent_reply(reply, op=lane.transport._op)
        assert lane.transport._agent_replies.qsize() == 1
        lane.transport._closed.set()
        lane.transport._request_close()

    lane.invoke(queue_then_close)
    lane.close()
    assert lane.transport._agent_replies.empty()
    assert not any(msg.body == ["privatePin"] for msg in lane.bus.sent)
    assert not lane.transport._writes and not lane.transport._pending


def test_qualified_dbus_fast_writer_retains_bytes_when_send_future_is_cancelled():
    """Dependency-level no-IO proof of the behavior modeled by BackpressuredBus."""
    from dbus_fast.aio.message_bus import _MessageWriter

    class Socket:
        writable = False
        bytes_written = 0

        def send(self, data):
            if not self.writable:
                return 0  # partial write: callback must await future writability
            self.bytes_written += len(data)
            return len(data)

    class Loop:
        def add_writer(self, *args):
            pass

        def remove_writer(self, *args):
            pass

    class Bus:
        _negotiate_unix_fd = False
        _sock = Socket()
        _fd = 17
        _loop = Loop()
        unique_name = ":1.7"
        _user_disconnect = False

        def _finalize(self, error):
            raise AssertionError("unexpected writer failure") from error

    async def scenario():
        bus = Bus()
        writer = _MessageWriter(bus)
        written = asyncio.get_running_loop().create_future()
        msg = Message(destination=":1.7", path=DP, interface=_DEVICE, member="Connect", serial=1)
        writer.schedule_write(msg, written)
        assert not written.done() and writer.buf is not None
        written.cancel()
        assert writer.buf is not None
        bus._sock.writable = True
        writer.write_callback()
        assert bus._sock.bytes_written > 0  # cancellation did not retract the frame
        assert written.cancelled()
        assert writer.buf is None and not writer.messages

    asyncio.run(scenario())


def test_uncertain_retirement_rejects_reentrant_listener_commands_before_notification():
    bus = BackpressuredBus()
    lane = Lane(bus)
    admissions = []
    try:
        target = lane.transport.snapshot().devices[0].id

        def listener(event):
            lane.events.append(event)
            if event.kind in {"finished", "unavailable"}:
                admissions.append(lane.transport.connect("from_listener", target, 150))

        lane.invoke(lambda: setattr(lane.transport, "_listener", listener))
        bus.block_members.add("Connect")
        lane.begin("connect")
        eventually(lambda: len(bus.buffered) == 1)
        lane.transport.cancel("op")
        assert_retired_connection(lane)
        assert admissions and not any(admissions)
        assert bus.max_buffered == 1
        assert not any(msg.member == "Connect" for msg in bus.calls)
    finally:
        lane.close()


@pytest.mark.parametrize("kind,member", [("discover", "StartDiscovery"), ("pair", "Pair")])
@pytest.mark.parametrize("retirement", ["cancel", "expire", "adapter_invalidated"])
def test_unconfirmed_pair_or_discovery_write_also_fails_closed(kind, member, retirement):
    bus = BackpressuredBus()
    lane = Lane(bus)
    try:
        bus.block_members.add(member)
        lane.begin(kind)
        eventually(lambda: len(bus.buffered) == 1)
        if retirement == "cancel":
            lane.transport.cancel("op")
        elif retirement == "expire":
            lane.clock.now = 1000
        else:
            lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {}, ["Address"]], AP)
        assert_retired_connection(lane)
        assert bus.max_buffered == 1
        assert any(e.kind == "finished" and e.code == "uncertain" for e in lane.events)
        assert not any(
            msg.member in {member, "CancelPairing", "StopDiscovery"} for msg in bus.calls
        )
    finally:
        lane.close()


@pytest.fixture
def before_reply_writer(monkeypatch):
    """Schedule a callback before the newly queued reply writer's first step.

    _reply_agent still reaches its await on that Task before this callback runs,
    so retiring the operation propagates cancellation to a never-started writer.
    No sleep, fake bus backpressure, or post-write window is used here.
    """

    def install(lane, before_write, *, generic="rejection"):
        transport = lane.transport
        original_queue = transport._queue_agent_reply
        original_writer = transport._send_agent_replies
        state = {"started": set(), "armed": False, "completed": False, "error": None}

        async def writer():
            state["started"].add(asyncio.current_task())
            await original_writer()

        def probe():
            try:
                task = state["writer"] = transport._agent_reply_task
                assert task not in state["started"]
                assert transport._agent_reply_write is None
                entry = state["entry"] = transport._agent_replies.get_nowait()
                transport._agent_replies.put_nowait(entry)
                op = state["operation"] = transport._op
                assert entry.operation is op
                assert (
                    entry.operation_id,
                    entry.controller_epoch,
                    entry.device_id,
                    entry.device_epoch,
                    entry.deadline,
                ) == (op.id, op.epoch, op.device_id, op.device_epoch, op.deadline)
                before_write(transport, state)
                assert task not in state["started"]
                if generic == "rejection":
                    msg = incoming_agent(serial=7777)
                    msg.sender = ":1.99"
                else:
                    msg = Message(
                        destination=":1.2",
                        path=_AGENT_PATH,
                        interface=_AGENT
                        if generic == "Cancel"
                        else "org.freedesktop.DBus.Introspectable",
                        member=generic,
                        serial=7777,
                    )
                    msg.sender = ":1.7"
                assert transport._on_message(msg) is True
                assert transport._agent_replies.qsize() <= 2
            except BaseException as exc:
                state["error"] = exc
            finally:
                state["completed"] = True

        def queue(reply, *, op=None):
            if op is not None and not state["armed"]:
                state["armed"] = True
                # Queue this BEFORE create_task() schedules its first step.
                asyncio.get_running_loop().call_soon(probe)
            return original_queue(reply, op=op)

        monkeypatch.setattr(transport, "_send_agent_replies", writer)
        monkeypatch.setattr(transport, "_queue_agent_reply", queue)
        return state

    return install


_POSITIVE_AGENT_REPLIES = [
    pytest.param("RequestPinCode", "o", [DP], {"pin": "queuedPin"}, id="pin"),
    pytest.param("RequestPasskey", "o", [DP], {"passkey": "654321"}, id="passkey"),
    pytest.param("RequestConfirmation", "ou", [DP, 654321], {"confirm": True}, id="confirmation"),
    pytest.param("RequestAuthorization", "o", [DP], {"confirm": True}, id="just-works"),
    pytest.param(
        "AuthorizeService",
        "os",
        [DP, "00001124-0000-1000-8000-00805f9b34fb"],
        None,
        id="classic-hid",
    ),
    pytest.param(
        "AuthorizeService", "os", [DP, "00001812-0000-1000-8000-00805f9b34fb"], None, id="le-hid"
    ),
    pytest.param("DisplayPinCode", "os", [DP, "displayPin"], None, id="display-pin-ack"),
    pytest.param("DisplayPasskey", "ouq", [DP, 654321, 2], None, id="display-passkey-ack"),
]


def retire_before_reply_writer(transport, state, retirement):
    op = state["operation"]
    if retirement == "cancel":
        transport._command("cancel", op.id, ())
    elif retirement == "expire":
        transport._clock.now = op.deadline + 1
        transport._retire("uncertain")
    elif retirement == "observed":
        msg = Message.new_signal(DP, _PROPS, "PropertiesChanged")
        msg.body = [_DEVICE, {"Paired": True}, []]
        msg.sender = ":1.7"
        transport._on_message(msg)
    elif retirement == "listener":

        def broken(_):
            raise ValueError("fixed listener failure")

        transport._listener = broken
        transport._emit("inventory")
    else:
        msg = Message(
            destination=":1.2", path=_AGENT_PATH, interface=_AGENT, member=retirement, serial=6666
        )
        msg.sender = ":1.7"
        transport._on_message(msg)
    assert transport._op is None
    assert transport._target_matches(op)  # This is retirement, not identity loss.
    assert state["writer"].cancelling()
    assert transport._agent_replies.qsize() <= 1  # only a generic Cancel/Release return


def assert_prewrite_reply_not_sent(lane, state):
    eventually(lambda: state["completed"])
    if state["error"]:
        raise state["error"]
    eventually(lambda: any(reply.reply_serial == 7777 for reply in lane.bus.sent))
    eventually(
        lambda: (
            lane.transport._agent_reply_task is None
            and lane.transport._agent_replies.empty()
            and not lane.transport._pending
            and not lane.transport._writes
        )
    )
    original = state["entry"].message
    assert not any(
        reply.reply_serial == original.reply_serial
        and reply.message_type == MessageType.METHOD_RETURN
        for reply in lane.bus.sent
    )
    assert lane.bus.connected
    assert lane.transport._agent_reply_write is None
    assert sum(msg.member == "Pair" for msg in lane.bus.calls) == 1
    assert sum(msg.member == "RegisterAgent" for msg in lane.bus.calls) == 1
    assert "queuedPin" not in repr(lane.events) + repr(state["entry"])
    return next(reply for reply in lane.bus.sent if reply.reply_serial == 7777)


@pytest.mark.parametrize("member,signature,body,answer", _POSITIVE_AGENT_REPLIES)
@pytest.mark.parametrize(
    "retirement", ["cancel", "expire", "observed", "listener", "Cancel", "Release"]
)
def test_positive_agent_reply_loses_authority_before_writer_first_step(
    lane, before_reply_writer, member, signature, body, answer, retirement
):
    lane.begin()
    lane.accepted()  # confirmed Pair write; no backpressure/connection failure masks this race
    state = before_reply_writer(
        lane, lambda transport, state: retire_before_reply_writer(transport, state, retirement)
    )
    assert lane.agent(member, signature, body) is True
    if answer:
        challenge = lane.challenge()
        assert lane.transport.answer("op", challenge.id, answer)
    generic = assert_prewrite_reply_not_sent(lane, state)
    assert generic.message_type == MessageType.ERROR and generic.body == ["Rejected"]
    assert state["writer"].cancelled()
    assert state["writer"] not in state["started"]  # no writer try/finally ever executed


@pytest.mark.parametrize("generic", ["Cancel", "Introspect"])
def test_prestart_cancelled_reply_writer_resumes_bounded_generic_responses(
    lane, before_reply_writer, generic
):
    lane.begin()
    lane.accepted()
    state = before_reply_writer(
        lane,
        lambda transport, state: retire_before_reply_writer(transport, state, "cancel"),
        generic=generic,
    )
    lane.agent("RequestPinCode", "o", [DP])
    lane.transport.answer("op", lane.challenge().id, {"pin": "queuedPin"})
    response = assert_prewrite_reply_not_sent(lane, state)
    assert response.message_type == MessageType.METHOD_RETURN
    if generic == "Introspect":
        assert _AGENT in response.body[0] and "queuedPin" not in response.body[0]
    else:
        assert response.body == []
    assert state["writer"].cancelled() and state["writer"] not in state["started"]


@pytest.mark.parametrize(
    "changed", ["operation_id", "controller_epoch", "device_id", "device_epoch", "deadline"]
)
def test_agent_reply_frozen_ownership_is_rechecked_at_bus_send(lane, before_reply_writer, changed):
    lane.begin()
    lane.accepted()

    def stale_metadata(transport, state):
        entry = transport._agent_replies.get_nowait()
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.deadline = 999
        values = {
            "operation_id": "wrong",
            "controller_epoch": transport._epoch + 1,
            "device_id": "wrong",
            "device_epoch": entry.device_epoch + 1,
            "deadline": lane.clock() - 1,
        }
        transport._agent_replies.put_nowait(
            dataclasses.replace(entry, **{changed: values[changed]})
        )
        assert transport._op is state["operation"]  # no retirement removed this entry

    state = before_reply_writer(lane, stale_metadata)
    lane.agent("RequestPinCode", "o", [DP])
    lane.transport.answer("op", lane.challenge().id, {"pin": "queuedPin"})
    generic = assert_prewrite_reply_not_sent(lane, state)
    assert generic.message_type == MessageType.ERROR
    assert lane.transport._op is state["operation"]
    assert state["writer"] in state["started"] and not state["writer"].cancelled()
