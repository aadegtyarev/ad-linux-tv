"""Adapter power uses the fake BlueZ bus, never a host controller."""

import pytest
from dbus_fast import Message, MessageType
from test_bluetooth_bluez import (
    _ADAPTER,
    _AGENT,
    _AGENT_PATH,
    _HID,
    _PROPS,
    AP,
    DP,
    Lane,
    eventually,
)


@pytest.fixture
def lane():
    instance = Lane()
    yield instance
    instance.close()


def test_power_on_is_scoped_and_requires_observed_property(lane):
    lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": False, "Alias": "USB"}, []], AP)
    adapter = lane.transport.snapshot().adapters[0]
    assert not adapter.powered and adapter.name == "USB"
    assert lane.transport.power_on("power", adapter.id, lane.clock() + 15)
    eventually(lambda: any(e.kind == "accepted" and e.operation_id == "power" for e in lane.events))
    calls = [m for m in lane.bus.calls if m.member == "Set"]
    assert len(calls) == 1 and calls[0].path == AP
    assert calls[0].interface == _PROPS and calls[0].signature == "ssv"
    assert calls[0].body[0:2] == [_ADAPTER, "Powered"]
    assert calls[0].body[2].value is True
    assert not any(e.kind == "powered" for e in lane.events)
    lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": True}, []], AP)
    assert lane.transport.snapshot().adapters[0].powered
    assert any(e.kind == "powered" and e.operation_id == "power" for e in lane.events)
    assert any(e.kind == "finished" and e.code == "observed" for e in lane.events)


@pytest.mark.parametrize(
    "kind", ["power_on", "discover", "pair", "connect", "disconnect", "forget"]
)
def test_duplicate_appearing_before_write_is_rejected(lane, monkeypatch, kind):
    if kind == "power_on":
        lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": False}, []], AP)
    snapshot = lane.transport.snapshot()
    target = snapshot.adapters[0].id if kind in {"power_on", "discover"} else snapshot.devices[0].id
    original = lane.transport._send

    async def add_duplicate_before_send(msg, *, op=None, agent_reply=None):
        if op:
            lane.transport._add(
                "/org/bluez/hci99",
                _ADAPTER,
                {
                    "Address": snapshot.adapters[0].address,
                    "Powered": True,
                },
            )
        return await original(msg, op=op, agent_reply=agent_reply)

    monkeypatch.setattr(lane.transport, "_send", add_duplicate_before_send)
    assert getattr(lane.transport, kind)("ambiguous", target, lane.clock() + 15)
    eventually(
        lambda: any(e.kind == "finished" and e.operation_id == "ambiguous" for e in lane.events)
    )
    assert any(e.code == "invalidated" for e in lane.events if e.operation_id == "ambiguous")
    assert not any(
        m.member in {"Set", "StartDiscovery", "Pair", "Connect", "Disconnect", "RemoveDevice"}
        for m in lane.bus.calls
    )


@pytest.mark.parametrize(
    "kind", ["pin", "passkey", "confirmation", "service", "display_pin", "display_passkey"]
)
def test_pairing_agent_positive_reply_fenced_when_duplicate_appears(lane, monkeypatch, kind):
    lane.begin()
    lane.accepted()
    original = lane.transport._send
    address = lane.transport.snapshot().adapters[0].address

    async def duplicate_before_reply(msg, *, op=None, agent_reply=None):
        if agent_reply and agent_reply.operation:
            lane.transport._add("/org/bluez/hci99", _ADAPTER, {"Address": address, "Powered": True})
        return await original(msg, op=op, agent_reply=agent_reply)

    monkeypatch.setattr(lane.transport, "_send", duplicate_before_reply)
    member, signature, args = {
        "pin": ("RequestPinCode", "o", [DP]),
        "passkey": ("RequestPasskey", "o", [DP]),
        "confirmation": ("RequestConfirmation", "ou", [DP, 123456]),
        "service": ("AuthorizeService", "os", [DP, next(iter(_HID))]),
        "display_pin": ("DisplayPinCode", "os", [DP, "1234"]),
        "display_passkey": ("DisplayPasskey", "ouq", [DP, 123456, 0]),
    }[kind]
    msg = Message(
        destination=":1.2",
        path=_AGENT_PATH,
        interface=_AGENT,
        member=member,
        signature=signature,
        body=args,
        serial=lane.request_serial,
    )
    msg.sender = ":1.7"
    lane.invoke(lambda: lane.bus.handler(msg))
    if kind in {"pin", "passkey", "confirmation"}:
        challenge = lane.challenge()
        answer = {
            "pin": {"pin": "1234"},
            "passkey": {"passkey": "123456"},
            "confirmation": {"confirm": True},
        }[kind]
        assert lane.transport.answer("op", challenge.id, answer)
    eventually(lambda: any(e.kind == "finished" and e.operation_id == "op" for e in lane.events))
    assert any(e.code == "invalidated" for e in lane.events if e.operation_id == "op")
    assert not any(
        m.reply_serial == msg.serial and m.message_type == MessageType.METHOD_RETURN
        for m in lane.bus.sent
    )


def test_external_discovery_starting_before_power_write_is_rejected(lane, monkeypatch):
    lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": False}, []], AP)
    adapter = lane.transport.snapshot().adapters[0]
    original = lane.transport._send

    async def discovery_before_send(msg, *, op=None, agent_reply=None):
        if op:
            lane.transport._adapters[AP].props["Discovering"] = True
        return await original(msg, op=op, agent_reply=agent_reply)

    monkeypatch.setattr(lane.transport, "_send", discovery_before_send)
    assert lane.transport.power_on("power", adapter.id, lane.clock() + 15)
    eventually(lambda: any(e.kind == "finished" and e.operation_id == "power" for e in lane.events))
    assert any(e.code == "invalidated" for e in lane.events if e.operation_id == "power")
    assert not any(m.member == "Set" for m in lane.bus.calls)


def test_denied_power_does_not_report_success(lane):
    lane.signal(_PROPS, "PropertiesChanged", [_ADAPTER, {"Powered": False}, []], AP)
    lane.bus.fail = "Set"
    adapter = lane.transport.snapshot().adapters[0]
    assert lane.transport.power_on("power", adapter.id, lane.clock() + 15)
    eventually(lambda: any(e.kind == "finished" and e.operation_id == "power" for e in lane.events))
    assert any(e.code == "denied" for e in lane.events if e.kind == "finished")
    assert not lane.transport.snapshot().adapters[0].powered
