"""Coordinator-only tests: frozen ducktyped BlueZ DTOs, fake clock, no bus/devices."""

import copy
import json
import threading
import time
from dataclasses import dataclass, field, replace

import pytest

from ad_linux_tv.bluetooth_manager import BluetoothManager, Principal
from ad_linux_tv.bluetooth_schema import ACTIONS, BUTTON_CODES

TV = Principal("tv", "launcher", "local")
PHONE = Principal("phone", "session-secret", "socket-secret")
OTHER = Principal("phone", "other", "other-socket")
A0 = "11:22:33:44:55:60"
A1 = "11:22:33:44:55:61"
PEER = "22:33:44:55:66:77"


@dataclass(frozen=True)
class Adapter:
    id: str = "hci1"
    address: str = A1
    powered: bool = True
    discovering: bool = False
    name: str = ""


@dataclass(frozen=True)
class Device:
    id: str = "device"
    adapter_id: str = "hci1"
    address: str = PEER
    address_type: str = "public"
    name: str = "Пульт"
    paired: bool = False
    connected: bool = False
    device_epoch: int = 2
    bluez_name: str = ""
    alias: str = ""


@dataclass(frozen=True)
class AdapterSnapshot:
    available: bool = True
    reason: str = ""
    controller_epoch: int = 3
    adapters: tuple = (Adapter(),)
    devices: tuple = (Device(),)


@dataclass(frozen=True)
class Challenge:
    id: str = "challenge"
    kind: str = "pin"
    deadline: float = 160
    value: str = field(default="", repr=False)
    entered: int = 0


@dataclass(frozen=True)
class BluezEvent:
    kind: str
    operation_id: str | None
    controller_epoch: int = 3
    device_id: str | None = "device"
    device_epoch: int = 2
    code: str = ""
    challenge: Challenge | None = field(default=None, repr=False)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Transport:
    def __init__(self):
        self.state = AdapterSnapshot()
        self.calls = []
        self.on_event = None
        self.fail = set()
        self.start_count = 0
        self.close_count = 0
        self.close_thread = None
        self.closed = threading.Event()

    def start(self, listener):
        self.start_count += 1
        self.on_event = listener
        if "start" in self.fail:
            raise RuntimeError("secret bus address")

    def snapshot(self):
        if "snapshot" in self.fail:
            raise RuntimeError("secret bus address")
        return self.state

    def close(self):
        self.close_count += 1
        self.close_thread = threading.current_thread()
        self.closed.set()
        if "close" in self.fail:
            raise RuntimeError("secret bus address")

    def _command(self, name, *args):
        self.calls.append((name, *args))
        if "raise_" + name in self.fail:
            raise RuntimeError("secret method address")
        return name not in self.fail

    def discover(self, *args):
        return self._command("discover", *args)

    def stop_discovery(self, *args):
        return self._command("stop_discovery", *args)

    def power_on(self, *args):
        return self._command("power_on", *args)

    def pair(self, *args):
        return self._command("pair", *args)

    def connect(self, *args):
        return self._command("connect", *args)

    def disconnect(self, *args):
        return self._command("disconnect", *args)

    def forget(self, *args):
        return self._command("forget", *args)

    def answer(self, *args):
        return self._command("answer", *args)

    def cancel(self, *args):
        return self._command("cancel", *args)

    def emit(self, kind, operation_id, **kwargs):
        self.on_event(BluezEvent(kind, operation_id, **kwargs))

    def device(self, **changes):
        self.state = replace(self.state, devices=(replace(self.state.devices[0], **changes),))


class Settings:
    def __init__(self):
        self.section = {"remote": None}
        self.saves = []
        self.threads = []
        self.fail_get = False
        self.fail_save = False

    def get(self):
        self.threads.append(threading.current_thread())
        if self.fail_get:
            raise ValueError("secret YAML")
        return copy.deepcopy(self.section)

    def save(self, section):
        self.threads.append(threading.current_thread())
        if self.fail_save:
            raise OSError("secret filename")
        self.saves.append(copy.deepcopy(section))
        self.section = copy.deepcopy(section)

    def saved_remote(self, **identity):
        self.section = {
            "remote": {
                "identity": {"adapter": A1, "address": PEER, "address_type": "public", **identity},
                "bindings": {"KEY_UP": "up", "KEY_ENTER": "ok"},
            }
        }


class Rig:
    def __init__(self, *, enabled=True):
        self.clock = Clock()
        self.transport = Transport()
        self.settings = Settings()
        self.manager = BluetoothManager(
            transport=self.transport,
            get_config=self.settings.get,
            save_config=self.settings.save,
            enabled=enabled,
            clock=self.clock,
        )
        self.lease = None
        self.principal = PHONE

    def start(self):
        self.manager.start()
        self.manager.tick()

    def acquire(self, principal=PHONE):
        self.principal = principal
        status, response = self.manager.request(principal, {"op": "acquire"})
        assert status == 200
        self.lease = response["lease"]
        return response

    def request(self, op, **fields):
        return self.manager.request(self.principal, {"op": op, "lease": self.lease, **fields})

    def begin(self, op="pair"):
        fields = {} if op == "discover" else {"device_id": "device"}
        status, response = self.request(op, **fields)
        assert status == (200 if op == "forget_prepare" else 202)
        return response["state"]["operation"]["id"], response

    def emit(self, kind, operation_id, **fields):
        self.transport.emit(kind, operation_id, **fields)
        self.manager.tick()

    def state(self):
        return self.manager.snapshot(self.principal)

    def poll(self):
        status, reply = self.request("poll")
        assert status == 200
        return reply

    def advance(self, seconds, *, poll=False):
        self.clock.advance(seconds)
        self.manager.tick()
        if poll:
            self.poll()


@pytest.fixture
def rig():
    rig = Rig()
    rig.start()
    rig.acquire()
    yield rig
    rig.manager.close()
    assert not rig.manager._thread.is_alive()


def wait_until(predicate):
    end = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < end
        time.sleep(0.005)


def test_construction_disabled_and_explicit_idempotent_lifecycle():
    rig = Rig(enabled=False)
    assert rig.transport.start_count == 0
    assert rig.settings.threads == []
    rig.manager.start()
    assert not rig.state()["available"]
    assert rig.manager.request(TV, {"op": "acquire"})[0] == 503
    rig.manager.close()
    assert rig.transport.close_count == 0
    assert rig.settings.threads == []
    rig = Rig()
    assert rig.manager.request(TV, {"op": "acquire"})[0] == 503
    rig.start()
    rig.manager.start()
    rig.manager.close()
    rig.manager.close()
    rig.manager.start()
    assert rig.transport.start_count == rig.transport.close_count == 1
    assert not rig.manager._thread.is_alive()


def test_principal_is_internal_immutable_connection_bound_and_redacted(rig):
    assert "session-secret" not in repr(PHONE)
    assert "socket-secret" not in repr(PHONE)
    assert hash(PHONE)
    with pytest.raises(AttributeError):
        PHONE.owner = "spoof"
    with pytest.raises(ValueError, match="invalid principal"):
        Principal("json", "x")
    assert rig.manager.request({"kind": "phone"}, {"op": "acquire"})[0] == 403
    with pytest.raises(ValueError, match="invalid principal"):
        rig.manager.snapshot(None)
    for other in (OTHER, Principal("phone", PHONE.owner, "different"), TV):
        assert rig.manager.request(other, {"op": "poll", "lease": rig.lease})[0] == 403
        rig.manager.retire(other)
    assert rig.poll()


def test_lease_is_not_reissued_or_renewed_by_get_mutation_or_failed_poll(rig):
    assert rig.manager.request(PHONE, {"op": "acquire"})[0] == 409
    rig.advance(10)
    rig.state()
    assert rig.request("poll", lease="0" * 32)[0] == 409
    rig.begin("discover")
    rig.advance(5)
    assert rig.request("poll")[0] == 409
    assert rig.transport.calls[-1][0] == "cancel"
    assert rig.state()["operation"]["error"] == "uncertain"
    old_lease = rig.lease
    response = rig.acquire(OTHER)
    assert response["lease"] != old_lease
    assert set(response) == {"state", "lease"}


def test_only_valid_owner_poll_renews_lease_and_does_not_extend_operation(rig):
    operation_id, response = rig.begin("discover")
    assert response["state"]["operation"]["remaining_ms"] == 30000
    for _ in range(5):
        rig.advance(5, poll=True)
    assert rig.state()["operation"]["remaining_ms"] == 5000
    rig.advance(5)
    assert rig.state()["operation"]["error"] == "uncertain"
    assert rig.transport.calls.count(("cancel", operation_id)) == 1
    rig.poll()


@pytest.mark.parametrize("how", ["release", "retire", "retire_phones"])
def test_owner_retirement_cancels_and_clears_private_state(rig, how):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge(value=""))
    assert "challenge" in rig.poll()
    if how == "release":
        assert rig.request("release")[0] == 200
    elif how == "retire":
        rig.manager.retire(PHONE)
    else:
        rig.manager.retire_phones()
    assert rig.request("poll")[0] == 409
    assert rig.transport.calls[-1] == ("cancel", operation_id)
    assert rig.manager._operation.challenge is None
    rig.emit("challenge", operation_id, challenge=Challenge())
    assert rig.manager._operation.challenge is None


def test_retire_phones_preserves_tv_and_exact_connection_hook(rig):
    rig.request("release")
    rig.acquire(TV)
    operation_id, _ = rig.begin()
    rig.manager.retire_phones()
    rig.manager.retire(PHONE)
    assert rig.poll()["state"]["operation"]["id"] == operation_id
    assert not any(call[0] == "cancel" for call in rig.transport.calls)
    rig.manager.retire(TV)
    assert rig.transport.calls[-1] == ("cancel", operation_id)


@pytest.mark.parametrize(
    "dto",
    [
        None,
        [],
        {},
        {"op": []},
        {"op": "unknown"},
        {"op": "acquire", "owner": "spoof"},
        {"op": "poll"},
        {"op": "poll", "lease": "a" * 33},
        {"op": "poll", "lease": "A" * 32},
        {"op": "poll", "lease": True},
        {"op": "pair", "lease": "a" * 32, "device_id": "/org/bluez/hci1/dev"},
        {"op": "pair", "lease": "a" * 32, "device_id": "d" * 65},
        {"op": "pair", "lease": "a" * 32, "device_id": []},
        {"op": "learn", "lease": "a" * 32, "action": "shutdown"},
        {"op": "learn", "lease": "a" * 32, "action": {}},
        {"op": "unmap", "lease": "a" * 32, "revision": 0, "key": "KEY_A"},
        {"op": "unmap", "lease": "a" * 32, "revision": 0, "key": []},
        *[
            {"op": "reset", "lease": "a" * 32, "revision": n}
            for n in (True, -1, 0.0, 2**53, "0", None)
        ],
        *[
            {
                "op": "answer",
                "lease": "a" * 32,
                "operation_id": "x",
                "challenge_id": "c",
                "answer": a,
            }
            for a in (
                None,
                [],
                {},
                {"pin": ""},
                {"pin": "x" * 17},
                {"pin": "а"},
                {"pin": "a b"},
                {"pin": "x\n"},
                {"passkey": "１２３４５６"},
                {"passkey": 123456},
                {"passkey": "12345"},
                {"confirm": 1},
                {"confirm": True, "pin": "x"},
                {"shell": "rm"},
            )
        ],
    ],
)
def test_malformed_dtos_fail_before_ownership_and_do_not_call_transport(rig, dto):
    before = list(rig.transport.calls)
    status, reply = rig.manager.request(OTHER, dto)
    assert status == 400
    assert set(reply) == {"state", "error"}
    assert rig.transport.calls == before


@pytest.mark.parametrize(
    "op",
    [
        "acquire",
        "poll",
        "release",
        "discover",
        "cancel",
        "pair",
        "connect",
        "disconnect",
        "select_remote",
        "answer",
        "forget_prepare",
        "forget_confirm",
        "learn",
        "bind",
        "test",
        "unmap",
        "reset",
    ],
)
def test_every_variant_rejects_extra_fields(rig, op):
    from ad_linux_tv.bluetooth_manager import _FIELDS

    values = {
        "lease": rig.lease,
        "device_id": "device",
        "operation_id": "o",
        "challenge_id": "c",
        "confirmation_id": "c",
        "observation_id": "o",
        "answer": {"pin": "1234"},
        "action": "up",
        "key": "KEY_UP",
        "revision": 0,
    }
    dto = {"op": op, **{key: values[key] for key in _FIELDS[op]}, "extra": {"owner": PHONE.owner}}
    assert rig.manager.request(PHONE, dto)[0] == 400


@pytest.mark.parametrize(
    "op,observed,changes",
    [
        ("pair", "paired", {"paired": True}),
        ("connect", "connected", {"connected": True}),
        ("disconnect", "disconnected", {"connected": False}),
    ],
)
@pytest.mark.parametrize("early", [True, False])
def test_observation_does_not_hide_later_dispatch_uncertainty(rig, op, observed, changes, early):
    if op == "disconnect":
        rig.transport.device(connected=True)
    operation_id, _ = rig.begin(op)
    assert rig.state()["operation"]["phase"] == "queued"
    rig.emit("requested", operation_id)
    assert rig.state()["operation"]["phase"] == "requested"
    if not early:
        rig.emit("accepted", operation_id)
        assert rig.state()["operation"]["phase"] == "accepted"
    rig.transport.device(**changes)
    rig.emit(observed, operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    rig.emit("accepted", operation_id)
    rig.emit("finished", operation_id, code="uncertain")
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.state()["operation"]["error"] == "uncertain"


def test_property_event_without_matching_property_is_not_success(rig):
    operation_id, _ = rig.begin()
    rig.emit("paired", operation_id)
    assert rig.state()["operation"]["phase"] == "queued"
    rig.emit("finished", operation_id, code="observed")
    assert rig.state()["operation"]["phase"] != "observed"
    rig.advance(15)
    assert rig.state()["operation"]["error"] == "uncertain"


@pytest.mark.parametrize(
    "fields",
    [
        {"operation_id": "old"},
        {"controller_epoch": 2},
        {"device_id": "other"},
        {"device_epoch": 1},
    ],
)
def test_stale_events_cannot_deliver_challenges_or_change_operations(rig, fields):
    operation_id, _ = rig.begin()
    event = {"operation_id": operation_id, **fields}
    rig.emit("challenge", challenge=Challenge(), **event)
    assert "challenge" not in rig.poll()
    rig.emit("accepted", **event)
    assert rig.state()["operation"]["phase"] == "queued"


@pytest.mark.parametrize(
    "kind,value,answer",
    [
        ("pin", "", {"pin": "a!9"}),
        ("passkey", "", {"passkey": "000123"}),
        ("confirmation", "012345", {"confirm": True}),
        ("confirmation", "012345", {"confirm": False}),
        ("display_pin", "s3cret", None),
        ("display_passkey", "012345", None),
    ],
)
def test_challenge_forms_private_delivery_and_exact_answers(rig, kind, value, answer):
    operation_id, _ = rig.begin()
    challenge = Challenge(kind=kind, value=value, entered=2)
    rig.emit("challenge", operation_id, challenge=challenge)
    poll = rig.poll()
    assert poll["challenge"]["kind"] == kind
    assert set(rig.state()) == {
        "available",
        "reason",
        "revision",
        "adapter",
        "adapter_preference",
        "adapters",
        "devices",
        "remote",
        "operation",
    }
    encoded = json.dumps(rig.state())
    for private in (rig.lease, "challenge", "confirmation_id", PHONE.owner, PHONE.connection):
        assert private not in encoded
    status, other = rig.manager.request(OTHER, {"op": "poll", "lease": rig.lease})
    assert status == 403 and "challenge" not in other
    if answer is None:
        assert (
            rig.request(
                "answer", operation_id=operation_id, challenge_id="challenge", answer={"pin": "x"}
            )[0]
            == 400
        )
        assert not any(call[0] == "answer" for call in rig.transport.calls)
    else:
        assert (
            rig.request("answer", operation_id=operation_id, challenge_id="wrong", answer=answer)[0]
            == 409
        )
        assert (
            rig.request(
                "answer", operation_id=operation_id, challenge_id="challenge", answer=answer
            )[0]
            == 202
        )
        assert "challenge" not in rig.poll()
        assert (
            rig.request(
                "answer", operation_id=operation_id, challenge_id="challenge", answer=answer
            )[0]
            == 409
        )
        rig.emit("challenge", operation_id, challenge=challenge)
        assert "challenge" not in rig.poll()  # No event replay resurrects an answered secret.
        assert sum(call[0] == "answer" for call in rig.transport.calls) == 1


def test_mismatched_answer_does_not_consume_challenge(rig):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge())
    assert (
        rig.request(
            "answer", operation_id=operation_id, challenge_id="challenge", answer={"confirm": True}
        )[0]
        == 400
    )
    assert "challenge" in rig.poll()


@pytest.mark.parametrize(
    "challenge",
    [
        Challenge(kind="shell"),
        Challenge(id="/path"),
        Challenge(deadline=float("inf")),
        Challenge(deadline=float("nan")),
        Challenge(deadline=True),
        Challenge(deadline=100),
        Challenge(value="leaked-secret"),
        Challenge(kind="display_pin", value="a b"),
        Challenge(kind="confirmation", value="123"),
        Challenge(entered=True),
        Challenge(entered=7),
    ],
)
def test_invalid_challenge_cancels_without_exposing_data(rig, challenge):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=challenge)
    assert "challenge" not in rig.poll()
    assert rig.state()["operation"]["error"] == "uncertain"


def test_challenge_updates_cannot_extend_deadline_or_replace_id(rig):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge(deadline=110))
    rig.advance(5)
    rig.emit("challenge", operation_id, challenge=Challenge(deadline=150))
    assert rig.poll()["challenge"]["remaining_ms"] == 5000
    rig.advance(5)
    assert "challenge" not in rig.poll()
    assert rig.state()["operation"]["error"] == "uncertain"
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge())
    rig.emit("challenge", operation_id, challenge=Challenge(id="new"))
    assert rig.state()["operation"]["error"] == "uncertain"


def test_original_pair_deadline_and_bounded_challenge_replay_ledger(rig):
    operation_id, _ = rig.begin()
    for i in range(9):
        rig.emit("challenge", operation_id, challenge=Challenge(id=f"c{i}", deadline=999))
        assert rig.poll()["challenge"]["remaining_ms"] == 60000
        status, _ = rig.request(
            "answer", operation_id=operation_id, challenge_id=f"c{i}", answer={"pin": "x"}
        )
        assert status == (202 if i < 8 else 409)
    assert rig.state()["operation"]["error"] == "uncertain"


@pytest.mark.parametrize(
    "mutation",
    ["controller", "device_epoch", "address", "adapter_address", "loss", "off", "service"],
)
def test_target_epochs_identity_and_loss_invalidate_without_retargeting(rig, mutation):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge())
    if mutation == "controller":
        rig.transport.state = replace(rig.transport.state, controller_epoch=4)
    elif mutation == "device_epoch":
        rig.transport.device(device_epoch=3)
    elif mutation == "address":
        rig.transport.device(address="33:44:55:66:77:88")
    elif mutation == "adapter_address":
        rig.transport.state = replace(rig.transport.state, adapters=(Adapter(address=A0),))
    elif mutation == "loss":
        rig.transport.state = replace(rig.transport.state, devices=())
    elif mutation == "off":
        rig.transport.state = replace(rig.transport.state, adapters=(Adapter(powered=False),))
    else:
        rig.transport.state = replace(rig.transport.state, available=False)
    assert rig.state()["operation"]["error"] == "uncertain"
    assert (
        rig.request(
            "answer", operation_id=operation_id, challenge_id="challenge", answer={"pin": "x"}
        )[0]
        == 409
    )
    assert rig.transport.calls[-1] == ("cancel", operation_id)


def test_adapter_preference_powered_valid_then_deterministic_off_and_saved_priority(rig):
    rig.transport.state = replace(
        rig.transport.state,
        adapters=(
            Adapter(id="hci0", address=A0, powered=False),
            Adapter(),
            Adapter(id="broken", address="00:00:00:00:00:00"),
        ),
    )
    assert rig.state()["adapter"]["id"] == "hci1"
    operation_id, _ = rig.begin("discover")
    assert rig.transport.calls[-1][2] == "hci1"
    rig.transport.state = replace(
        rig.transport.state,
        adapters=(
            Adapter(id="hci0", address=A0, powered=True),
            Adapter(),
        ),
    )
    assert rig.state()["operation"]["id"] == operation_id
    assert rig.state()["adapter"]["id"] == "hci1"
    assert rig.transport.calls == [("discover", operation_id, "hci1", 130.0)]
    rig.request("cancel", operation_id=operation_id)
    rig.settings.saved_remote(adapter=A1)
    assert rig.state()["adapter"]["id"] == "hci1"
    rig.transport.state = replace(rig.transport.state, adapters=(Adapter(id="hci0", address=A0),))
    assert rig.state()["adapter"] is None  # Never migrate a saved identity.
    assert rig.request("discover")[0] == 503
    rig.settings.section = {"remote": None}
    rig.transport.state = replace(
        rig.transport.state,
        adapters=(Adapter(powered=False), Adapter(id="hci0", address=A0, powered=False)),
    )
    assert rig.state()["adapter"]["id"] == "hci0"
    assert rig.state()["reason"] == "adapter_off"
    assert rig.request("discover")[0] == 503


def test_inventory_bounded_sanitized_deduplicated_with_selected_and_paired_priority(rig):
    rig.settings.saved_remote()
    devices = [Device(id=f"d{i}", address=f"22:33:44:55:66:{i:02X}") for i in range(100)]
    devices += [
        Device(id="selected", paired=True, connected=True, name="<img>\n\u202e" + "я" * 100),
        Device(id="bonded", address="44:55:66:77:88:99", paired=True),
        devices[0],
    ]
    rig.transport.state = replace(rig.transport.state, devices=tuple(devices))
    state = rig.state()
    assert len(state["devices"]) == 64
    assert len({d["id"] for d in state["devices"]}) == 64
    assert state["devices"][0]["id"] == "selected"
    assert state["devices"][1]["id"] == "bonded"
    name = state["devices"][0]["name"]
    assert name.startswith("<img>") and "\n" not in name and "\u202e" not in name
    assert len(name) <= 80 and len(name.encode()) <= 160
    assert state["remote"]["device_id"] == "selected"
    assert not any(d["input_available"] for d in state["devices"])
    assert "address" not in json.dumps(state)


def test_remote_absent_and_duplicate_identity_never_guess_attached_selection(rig):
    rig.settings.saved_remote()
    rig.transport.state = replace(rig.transport.state, devices=())
    assert rig.state()["remote"]["device_id"] is None
    assert rig.state()["remote"]["bindings"] == rig.settings.section["remote"]["bindings"]
    rig.transport.state = replace(rig.transport.state, devices=(Device(), Device(id="duplicate")))
    assert rig.state()["remote"]["device_id"] is None
    assert not any(d["selected"] for d in rig.state()["devices"])


@pytest.mark.parametrize(
    "op",
    [
        "pair",
        "connect",
        "disconnect",
        "discover",
        "forget_prepare",
        "learn",
        "select_remote",
        "reset",
        "unmap",
    ],
)
def test_exclusive_operation_busy_for_all_new_requests(rig, op):
    rig.begin()
    fields = (
        {"device_id": "device"}
        if op in ("pair", "connect", "disconnect", "forget_prepare", "select_remote")
        else {}
    )
    if op == "learn":
        fields["action"] = "up"
    if op in ("reset", "unmap"):
        fields["revision"] = 0
    if op == "unmap":
        fields["key"] = "KEY_UP"
    assert rig.request(op, **fields)[0] == 409
    assert len(rig.transport.calls) == 1


def confirm_forget(rig):
    operation_id, response = rig.begin("forget_prepare")
    assert (
        rig.request(
            "forget_confirm", operation_id=operation_id, confirmation_id=response["confirmation_id"]
        )[0]
        == 202
    )
    return operation_id


def test_forget_prepare_private_bound_once_and_no_effect_on_acceptance(rig):
    rig.settings.saved_remote()
    original = copy.deepcopy(rig.settings.section)
    operation_id, response = rig.begin("forget_prepare")
    assert rig.transport.calls == []
    confirmation = response["confirmation_id"]
    assert rig.poll()["confirmation_id"] == confirmation
    assert "confirmation_id" not in json.dumps(rig.state())
    assert (
        rig.request("forget_confirm", operation_id=operation_id, confirmation_id="wrong")[0] == 409
    )
    assert (
        rig.request("forget_confirm", operation_id="wrong", confirmation_id=confirmation)[0] == 409
    )
    assert (
        rig.request("forget_confirm", operation_id=operation_id, confirmation_id=confirmation)[0]
        == 202
    )
    assert rig.transport.calls == [("forget", operation_id, "device", 115.0)]
    assert (
        rig.request("forget_confirm", operation_id=operation_id, confirmation_id=confirmation)[0]
        == 409
    )
    rig.emit("accepted", operation_id)
    assert rig.settings.section == original
    assert "confirmation_id" not in rig.poll()
    assert rig.state()["operation"]["phase"] == "accepted"


@pytest.mark.parametrize("early", [True, False])
@pytest.mark.parametrize("missing_first", [True, False])
def test_exact_observed_forget_clears_saved_identity_even_removal_before_event(
    rig, early, missing_first
):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    revision = rig.state()["revision"]
    if not early:
        rig.emit("accepted", operation_id)
    rig.transport.state = replace(rig.transport.state, devices=())
    if missing_first:
        rig.manager.tick()
        assert rig.state()["operation"]["phase"] in ("queued", "accepted")
        assert rig.settings.section["remote"] is not None
    rig.emit("forgotten", operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.state()["operation"]["error"] == ""
    assert rig.settings.section == {"remote": None}
    assert rig.state()["revision"] == revision + 1
    rig.emit("accepted", operation_id)
    rig.emit("forgotten", operation_id)
    assert rig.settings.saves == [{"remote": None}]


def test_forgotten_requires_actual_removal_and_does_not_clear_other_saved_device(rig):
    rig.settings.saved_remote(address="33:44:55:66:77:88")
    operation_id = confirm_forget(rig)
    rig.emit("forgotten", operation_id)
    assert rig.state()["operation"]["phase"] == "queued"
    rig.transport.state = replace(rig.transport.state, devices=())
    rig.emit("forgotten", operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    assert not rig.settings.saves
    assert rig.settings.section["remote"] is not None


@pytest.mark.parametrize(
    "change", ["controller", "device", "config", "cancel", "lease", "retire", "timeout"]
)
def test_forget_stale_observation_cannot_mutate_config_after_invalidation(rig, change):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    rig.emit("requested", operation_id)
    if change == "controller":
        rig.transport.state = replace(rig.transport.state, controller_epoch=4)
    elif change == "device":
        rig.transport.device(device_epoch=3)
    elif change == "config":
        rig.settings.saved_remote(address="33:44:55:66:77:88")
    elif change == "cancel":
        rig.request("cancel", operation_id=operation_id)
    elif change == "lease":
        rig.advance(15)
    elif change == "retire":
        rig.manager.retire(PHONE)
    else:
        rig.advance(10, poll=True)
        rig.advance(5)
    rig.manager.tick()
    rig.transport.state = replace(rig.transport.state, devices=())
    rig.emit("forgotten", operation_id)
    assert rig.settings.section["remote"] is not None
    assert not rig.settings.saves
    assert rig.state()["operation"]["phase"] == "finished"
    assert rig.state()["operation"]["error"] == "uncertain"


def test_forget_confirmation_expires_at_twenty_seconds_without_dispatch(rig):
    operation_id, response = rig.begin("forget_prepare")
    rig.advance(10, poll=True)
    rig.advance(10, poll=True)
    assert (
        rig.request(
            "forget_confirm", operation_id=operation_id, confirmation_id=response["confirmation_id"]
        )[0]
        == 409
    )
    assert rig.state()["operation"]["error"] == "expired"
    assert rig.transport.calls == []


def test_forget_save_failure_keeps_physical_truth_without_rollback_or_retry(rig):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    rig.settings.fail_save = True
    rig.transport.state = replace(rig.transport.state, devices=())
    rig.emit("forgotten", operation_id)
    state = rig.state()
    assert state["operation"]["phase"] == "observed"
    assert state["operation"]["error"] == "save_failed"
    assert state["remote"]["device_id"] is None
    assert rig.settings.section["remote"] is not None
    rig.settings.fail_save = False
    rig.emit("forgotten", operation_id)
    assert not rig.settings.saves
    assert len(rig.transport.calls) == 1


@pytest.mark.parametrize("op", ["discover", "pair", "connect", "disconnect"])
@pytest.mark.parametrize("dispatched", [True, False])
def test_cancel_once_reports_irreversible_uncertainty_and_never_replays(rig, op, dispatched):
    operation_id, _ = rig.begin(op)
    fields = {"device_id": None, "device_epoch": 0} if op == "discover" else {}
    if dispatched:
        rig.emit("requested", operation_id, **fields)
    assert rig.request("cancel", operation_id=operation_id)[0] == 200
    expected = "uncertain"  # Admission cannot exclude dispatch before notification.
    assert rig.state()["operation"]["error"] == expected
    assert rig.request("cancel", operation_id=operation_id)[0] == 409
    rig.emit("accepted", operation_id, **fields)
    assert rig.state()["operation"]["error"] == expected
    assert rig.transport.calls.count(("cancel", operation_id)) == 1
    new_id, _ = rig.begin(op)
    assert new_id != operation_id


def test_config_revision_latest_reads_detached_snapshots_and_persisted_map_edits(rig):
    rig.settings.saved_remote()
    first = rig.state()
    revision = first["revision"]
    first["remote"]["bindings"].clear()
    assert rig.state()["remote"]["bindings"]
    assert rig.request("unmap", key="KEY_UP", revision=revision)[0] == 200
    revision += 1
    assert rig.state()["revision"] == revision
    assert rig.settings.section["remote"]["bindings"] == {"KEY_ENTER": "ok"}
    assert rig.request("reset", revision=revision - 1)[0] == 409
    assert rig.request("unmap", key="KEY_UP", revision=revision)[0] == 200
    assert rig.state()["revision"] == revision  # No-op does not rewrite/revise.
    rig.settings.section["remote"]["bindings"]["KEY_DOWN"] = "down"
    assert rig.request("reset", revision=revision)[0] == 409
    revision += 1
    assert rig.state()["revision"] == revision
    assert rig.request("reset", revision=revision)[0] == 200
    assert rig.settings.section["remote"]["bindings"] == {}
    assert rig.settings.section["remote"]["identity"]["address"] == PEER
    assert rig.state()["revision"] == revision + 1


@pytest.mark.parametrize("op", ["reset", "unmap"])
def test_map_saving_failure_preserves_current_source_and_snapshot(rig, op):
    rig.settings.saved_remote()
    state = rig.state()
    original = copy.deepcopy(rig.settings.section)
    rig.settings.fail_save = True
    fields = {"revision": state["revision"], **({"key": "KEY_UP"} if op == "unmap" else {})}
    status, result = rig.request(op, **fields)
    assert status == 503 and result["error"] == "save_failed"
    assert rig.settings.section == original
    assert result["state"]["revision"] == state["revision"]
    assert result["state"]["remote"]["bindings"] == original["remote"]["bindings"]
    assert "secret" not in json.dumps(result)


def test_latest_config_recheck_immediately_before_save_fences_revision(rig):
    rig.settings.saved_remote()
    revision = rig.state()["revision"]
    original_get = rig.settings.get
    count = 0

    def changing_get():
        nonlocal count
        count += 1
        if count == 3:  # request tick, edit precheck, then immediately-before-save
            rig.settings.section["remote"]["bindings"]["KEY_DOWN"] = "down"
        return original_get()

    with rig.manager._lock:
        rig.manager._get_config = changing_get
        status, result = rig.request("reset", revision=revision)
    assert status == 409 and result["error"] == "stale"
    assert result["state"]["revision"] == revision + 1
    assert not rig.settings.saves
    assert rig.settings.section["remote"]["bindings"]["KEY_DOWN"] == "down"


def test_config_change_cancels_pending_pair_challenge_and_forget_prepare(rig):
    operation_id, _ = rig.begin()
    rig.emit("challenge", operation_id, challenge=Challenge())
    rig.settings.saved_remote()
    assert rig.state()["operation"]["error"] == "uncertain"
    assert "challenge" not in rig.poll()
    operation_id, response = rig.begin("forget_prepare")
    rig.settings.section["remote"]["bindings"].clear()
    assert (
        rig.request(
            "forget_confirm", operation_id=operation_id, confirmation_id=response["confirmation_id"]
        )[0]
        == 409
    )
    assert not any(call[0] == "forget" for call in rig.transport.calls)


def test_invalid_or_unreadable_config_fails_closed_without_unvalidated_save(rig):
    rig.settings.section = {"remote": {"malformed": "secret"}}
    assert rig.state()["reason"] == "save_failed"
    assert rig.request("discover")[0] == 503
    assert rig.request("reset", revision=0)[0] == 503
    assert not rig.settings.saves
    rig.settings.fail_get = True
    assert rig.request("reset", revision=0)[0] == 503


@pytest.mark.parametrize("action", ACTIONS)
def test_learning_reports_absent_helper_only_for_valid_live_selected_remote(rig, action):
    assert rig.request("learn", action=action)[0] == 409
    rig.settings.saved_remote()
    assert rig.request("learn", action=action)[0] == 409
    rig.transport.device(paired=True, connected=True)
    before = copy.deepcopy(rig.settings.section)
    status, reply = rig.request("learn", action=action)
    assert status == 503 and reply["error"] == "helper_unavailable"
    assert rig.settings.section == before
    assert not rig.settings.saves and not rig.transport.calls
    assert "observation" not in reply


def test_select_candidate_eligibility_is_not_guessed_input_availability(rig):
    rig.settings.saved_remote(address="33:44:55:66:77:88")
    before = copy.deepcopy(rig.settings.section)
    for changes in ({"paired": False, "connected": False}, {"paired": True, "connected": False}):
        rig.transport.device(**changes)
        assert rig.request("select_remote", device_id="device")[0] == 409
    rig.transport.device(paired=True, connected=True)
    assert not rig.state()["devices"][0]["input_available"]
    status, reply = rig.request("select_remote", device_id="device")
    assert status == 503 and reply["error"] == "helper_unavailable"
    assert rig.settings.section == before
    assert not rig.settings.saves and not rig.transport.calls
    assert reply["state"]["operation"] is None
    assert rig.request("select_remote", device_id="missing")[0] == 409


@pytest.mark.parametrize("op", ["bind", "test"])
def test_input_observation_requests_validate_then_stale_never_fabricate_success(rig, op):
    assert rig.request(op, operation_id="nonexistent", observation_id="nonexistent")[0] == 409
    operation_id, _ = rig.begin()
    status, result = rig.request(op, operation_id=operation_id, observation_id="nonexistent")
    assert status == 409 and result["error"] == "stale"
    assert "observation" not in result
    assert not rig.settings.saves
    assert len(rig.transport.calls) == 1


@pytest.mark.parametrize("key", BUTTON_CODES)
def test_every_fixed_key_can_be_unmapped_without_input_helper(rig, key):
    rig.settings.saved_remote()
    rig.settings.section["remote"]["bindings"] = {key: "up"}
    revision = rig.state()["revision"]
    assert rig.request("unmap", key=key, revision=revision)[0] == 200
    assert rig.settings.section["remote"]["bindings"] == {}


def test_saved_map_edits_supported_without_live_adapter_or_transport_availability(rig):
    rig.settings.saved_remote()
    rig.transport.state = replace(rig.transport.state, available=False, adapters=(), devices=())
    revision = rig.state()["revision"]
    assert not rig.state()["available"]
    assert rig.request("reset", revision=revision)[0] == 200
    assert rig.settings.section["remote"]["bindings"] == {}


@pytest.mark.parametrize(
    "method", ["discover", "pair", "connect", "disconnect", "forget", "answer", "cancel"]
)
@pytest.mark.parametrize("raises", [False, True])
def test_queue_or_cancellation_failure_fails_closed_cleanup_off_callback(rig, method, raises):
    if method in ("answer", "cancel"):
        operation_id, _ = rig.begin()
        if method == "answer":
            rig.emit("challenge", operation_id, challenge=Challenge())
    elif method == "forget":
        operation_id, response = rig.begin("forget_prepare")
    rig.transport.fail.add(("raise_" if raises else "") + method)
    if method == "answer":
        status, result = rig.request(
            "answer", operation_id=operation_id, challenge_id="challenge", answer={"pin": "x"}
        )
    elif method == "cancel":
        status, result = rig.request("cancel", operation_id=operation_id)
    elif method == "forget":
        status, result = rig.request(
            "forget_confirm", operation_id=operation_id, confirmation_id=response["confirmation_id"]
        )
    else:
        fields = {} if method == "discover" else {"device_id": "device"}
        status, result = rig.request(method, **fields)
    assert status == 503 and result["error"] == "unavailable"
    wait_until(lambda: rig.transport.closed.is_set())
    assert rig.transport.close_thread is rig.manager._thread
    assert not rig.state()["available"]
    assert rig.request("poll")[0] == 503
    assert "secret" not in json.dumps(result)
    assert not rig.settings.saves


def test_callback_mailbox_overload_never_blocks_and_retires_possible_discovery(rig):
    operation_id, _ = rig.begin("discover")
    callback_thread = None
    elapsed = None

    def producer():
        nonlocal callback_thread, elapsed
        callback_thread = threading.current_thread()
        begin = time.monotonic()
        for _ in range(1000):
            rig.transport.emit("inventory", None, device_id=None, device_epoch=0)
        elapsed = time.monotonic() - begin

    # Block worker, not callback: callback must never acquire coordinator/settings locks.
    with rig.manager._lock:
        producer_thread = threading.Thread(target=producer)
        producer_thread.start()
        producer_thread.join(1)
        assert not producer_thread.is_alive()
        assert elapsed < 1
        assert rig.manager._events.qsize() == 64
    wait_until(lambda: rig.transport.closed.is_set())
    assert rig.transport.close_thread is not callback_thread
    assert callback_thread not in rig.settings.threads
    assert not rig.state()["available"]
    assert rig.state()["operation"]["id"] == operation_id
    assert rig.state()["operation"]["error"] == "uncertain"
    assert rig.manager._owner is None


def test_timer_expiry_is_independent_of_http_and_event_traffic(rig):
    operation_id, _ = rig.begin("discover")
    rig.clock.advance(15)
    wait_until(lambda: ("cancel", operation_id) in rig.transport.calls)
    assert rig.manager._owner is None
    assert rig.manager._operation.error == "uncertain"


def test_event_batch_cannot_starve_lease_expiry(rig):
    operation_id, _ = rig.begin("discover")
    with rig.manager._lock:
        for _ in range(64):
            rig.transport.emit("inventory", None, device_id=None, device_epoch=0)
        rig.clock.advance(15)
        rig.manager.tick()
    assert rig.manager._owner is None
    assert rig.transport.calls[-1] == ("cancel", operation_id)
    assert rig.manager._events.qsize() == 0


@pytest.mark.parametrize("failure", ["start", "snapshot", "close", "malformed_event"])
def test_lifecycle_listener_failure_is_redacted_and_cleanup_has_no_thread_leak(failure):
    rig = Rig()
    if failure != "malformed_event":
        rig.transport.fail.add(failure)
    rig.start()
    if failure == "malformed_event":
        rig.acquire()
        rig.begin()
        rig.transport.on_event(object())
        rig.manager.tick()
    if failure == "close":
        with pytest.raises(RuntimeError, match="^Bluetooth shutdown failed$"):
            rig.manager.close()
    else:
        wait_until(lambda: rig.transport.closed.is_set())
        rig.manager.close()
    assert not rig.manager._thread.is_alive()
    assert rig.transport.close_count == 1
    assert not rig.state()["available"]
    assert "secret" not in json.dumps(rig.state())


def test_close_cancels_discovery_once_clears_secrets_and_ignores_late_callbacks(rig):
    operation_id, _ = rig.begin("discover")
    rig.manager.close()
    rig.transport.emit("challenge", operation_id, challenge=Challenge())
    assert rig.transport.calls.count(("cancel", operation_id)) == 1
    assert rig.transport.close_count == 1
    assert rig.manager._events.qsize() == 0
    assert rig.manager._owner is None


def test_unknown_transport_error_is_fixed_not_raw_exception_text(rig):
    operation_id, _ = rig.begin()
    rig.emit("finished", operation_id, code="D-Bus /private secret pin=1234")
    assert rig.state()["operation"]["error"] == "uncertain"
    assert "private" not in json.dumps(rig.state())


@pytest.mark.parametrize(
    "op,duration", [("discover", 30), ("pair", 60), ("connect", 60), ("disconnect", 15)]
)
def test_each_original_command_deadline_expires_independent_of_poll_and_acceptance(
    rig, op, duration
):
    operation_id, _ = rig.begin(op)
    event_fields = {"device_id": None, "device_epoch": 0} if op == "discover" else {}
    rig.emit("requested", operation_id, **event_fields)
    for _ in range(duration // 5 - 1):
        rig.advance(5, poll=True)
    rig.emit("accepted", operation_id, **event_fields)
    assert rig.state()["operation"]["remaining_ms"] == 5000
    rig.advance(5)
    error = "uncertain"  # Pair/discovery writes are not confirmed by local expiry either.
    assert rig.state()["operation"]["error"] == error
    assert rig.transport.calls.count(("cancel", operation_id)) == 1


@pytest.mark.parametrize("change", [{"kind": "passkey"}, {"value": "654321"}])
def test_same_challenge_id_cannot_change_kind_or_secret(rig, change):
    operation_id, _ = rig.begin()
    challenge = Challenge(kind="confirmation", value="123456")
    rig.emit("challenge", operation_id, challenge=challenge)
    rig.emit("challenge", operation_id, challenge=replace(challenge, **change))
    assert "challenge" not in rig.poll()
    assert rig.state()["operation"]["error"] == "uncertain"


def test_display_progress_update_is_bounded_and_does_not_regress_waiting_phase(rig):
    operation_id, _ = rig.begin()
    rig.emit(
        "challenge",
        operation_id,
        challenge=Challenge(kind="display_passkey", value="123456", deadline=120),
    )
    rig.advance(5)
    rig.emit("accepted", operation_id)
    rig.emit("requested", operation_id)
    rig.emit(
        "challenge",
        operation_id,
        challenge=Challenge(kind="display_passkey", value="123456", entered=4, deadline=150),
    )
    reply = rig.poll()
    assert reply["state"]["operation"]["phase"] == "waiting"
    assert reply["challenge"]["entered"] == 4
    assert reply["challenge"]["remaining_ms"] == 15000


@pytest.mark.parametrize("why", ["expiry", "device_loss", "controller_loss", "close"])
def test_failed_cleanup_cannot_abandon_possible_owned_discovery(rig, why):
    operation_id, _ = rig.begin("discover")
    rig.transport.fail.add("cancel")
    if why == "expiry":
        rig.clock.advance(15)
    elif why == "device_loss":
        # Discovery pins the adapter, not an individual discovered device.
        rig.transport.state = replace(rig.transport.state, adapters=(), devices=())
    elif why == "controller_loss":
        rig.transport.state = replace(rig.transport.state, controller_epoch=4)
    if why == "close":
        rig.manager.close()
    else:
        rig.manager.tick()
        wait_until(lambda: rig.transport.closed.is_set())
    assert ("cancel", operation_id) in rig.transport.calls
    assert rig.manager._owner is None
    assert rig.transport.close_count == 1
    assert rig.state()["operation"]["error"] == "uncertain"


def test_unrelated_device_loss_does_not_cancel_discovery_or_move_adapter(rig):
    operation_id, _ = rig.begin("discover")
    rig.transport.state = replace(rig.transport.state, devices=())
    assert rig.state()["operation"]["id"] == operation_id
    assert rig.state()["operation"]["phase"] == "queued"
    assert len(rig.transport.calls) == 1


def test_pair_new_operation_rejects_late_old_observations_and_answers(rig):
    old_id, _ = rig.begin()
    rig.emit("challenge", old_id, challenge=Challenge())
    rig.request("cancel", operation_id=old_id)
    new_id, _ = rig.begin()
    rig.emit("challenge", old_id, challenge=Challenge(value=""))
    rig.transport.device(paired=True)
    rig.emit("paired", old_id)
    rig.emit("accepted", old_id)
    assert rig.state()["operation"]["id"] == new_id
    assert rig.state()["operation"]["phase"] == "queued"
    assert "challenge" not in rig.poll()
    assert (
        rig.request("answer", operation_id=old_id, challenge_id="challenge", answer={"pin": "x"})[0]
        == 409
    )


def test_forget_latest_revision_recheck_preserves_changed_settings_and_physical_truth(rig):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    getter = rig.settings.get
    count = 0

    def change_during_finalization():
        nonlocal count
        count += 1
        if count == 3:
            rig.settings.section["remote"]["bindings"]["KEY_DOWN"] = "down"
        return getter()

    with rig.manager._lock:
        rig.manager._get_config = change_during_finalization
        rig.transport.state = replace(rig.transport.state, devices=())
        rig.transport.emit("forgotten", operation_id)
        rig.manager.tick()
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.state()["operation"]["error"] == "save_failed"
    assert not rig.settings.saves
    assert rig.settings.section["remote"]["bindings"]["KEY_DOWN"] == "down"


@pytest.mark.parametrize("effect", ["pair", "answer", "forget_confirm"])
@pytest.mark.parametrize("race", ["lease", "epoch", "identity", "challenge_deadline"])
def test_dispatch_rechecks_current_lease_epoch_identity_and_deadline(rig, effect, race):
    if effect == "answer":
        operation_id, _ = rig.begin()
        rig.emit("challenge", operation_id, challenge=Challenge(deadline=105))
        fields = {"operation_id": operation_id, "challenge_id": "challenge", "answer": {"pin": "x"}}
    elif effect == "forget_confirm":
        operation_id, response = rig.begin("forget_prepare")
        fields = {"operation_id": operation_id, "confirmation_id": response["confirmation_id"]}
    else:
        fields = {"device_id": "device"}
    snapshot = rig.transport.snapshot
    count = 0

    def change_just_before_dispatch():
        nonlocal count
        count += 1
        if count == 2:  # tick is not sufficient: state changes after validation starts.
            if race == "lease":
                rig.clock.advance(15)
            elif race == "epoch":
                rig.transport.state = replace(rig.transport.state, controller_epoch=4)
            elif race == "identity":
                rig.transport.device(device_epoch=3)
            elif effect == "answer":
                rig.clock.advance(5)
            else:
                rig.clock.advance(60)
        return snapshot()

    with rig.manager._lock:
        rig.transport.snapshot = change_just_before_dispatch
        before = len(rig.transport.calls)
        assert rig.request(effect, **fields)[0] == 409
    commands = rig.transport.calls[before:]
    assert not any(call[0] in ("pair", "answer", "forget") for call in commands)
    assert rig.manager._operation.challenge is None
    assert rig.manager._operation.confirmation is None


def test_forget_dispatch_and_terminal_events_remain_honest_after_early_removal(rig):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    rig.transport.state = replace(rig.transport.state, devices=())
    rig.manager.tick()
    rig.emit("requested", operation_id)
    rig.emit("accepted", operation_id)
    assert rig.state()["operation"]["phase"] == "accepted"
    rig.emit("finished", operation_id, code="uncertain")
    assert rig.state()["operation"]["phase"] == "finished"
    assert rig.state()["operation"]["error"] == "uncertain"
    assert not rig.settings.saves
    assert rig.settings.section["remote"] is not None


def test_release_cancellation_failure_reports_unavailable_not_cleanup_success(rig):
    rig.begin("discover")
    rig.transport.fail.add("cancel")
    status, response = rig.request("release")
    assert status == 503 and response["error"] == "unavailable"
    wait_until(lambda: rig.transport.closed.is_set())
    assert rig.manager._owner is None


@pytest.mark.parametrize("op", ["unmap", "reset"])
def test_mapping_save_rechecks_lease_after_latest_config_read(rig, op):
    rig.settings.saved_remote()
    revision = rig.state()["revision"]
    getter = rig.settings.get
    count = 0

    def expire_before_write():
        nonlocal count
        count += 1
        if count == 3:
            rig.clock.advance(15)
        return getter()

    with rig.manager._lock:
        rig.manager._get_config = expire_before_write
        fields = {"key": "KEY_UP"} if op == "unmap" else {}
        status, response = rig.request(op, revision=revision, **fields)
    assert status == 409 and response["error"] == "expired"
    assert rig.manager._owner is None
    assert not rig.settings.saves
    assert rig.settings.section["remote"]["bindings"]["KEY_UP"] == "up"


def test_settings_manager_atomic_writer_preserves_other_settings_and_secrets(tmp_path):
    from test_settings import manager as settings_manager

    settings, sessions, path, _ = settings_manager(tmp_path)
    token, _ = sessions.create()
    rig = Rig()
    rig.settings.saved_remote()
    settings.set_bluetooth(rig.settings.section)
    before_auth = copy.deepcopy(settings.config["auth"])
    rig.manager = BluetoothManager(
        transport=rig.transport,
        get_config=settings.bluetooth_config,
        save_config=settings.set_bluetooth,
        enabled=True,
        clock=rig.clock,
    )
    try:
        rig.start()
        rig.acquire()
        revision = rig.state()["revision"]
        settings.set_audio_level("browser", 37)
        assert rig.request("unmap", revision=revision, key="KEY_UP")[0] == 200
        from ad_linux_tv.config import load_config

        persisted = load_config(path)
        assert persisted["bluetooth"]["remote"]["bindings"] == {"KEY_ENTER": "ok"}
        assert persisted["audio"]["browser"] == 37
        assert persisted["auth"] == before_auth
        assert sessions.valid(token)
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        rig.manager.close()


_PHYSICAL = {
    "pair": ("paired", {"paired": True}),
    "connect": ("connected", {"connected": True}),
    "disconnect": ("disconnected", {"connected": False}),
    "forget": ("forgotten", None),
}


def begin_command(rig, kind):
    if kind == "forget":
        return confirm_forget(rig)
    return rig.begin(kind)[0]


def event_target(kind):
    return {"device_id": None, "device_epoch": 0} if kind == "discover" else {}


def physical_change(rig, kind):
    event_kind, changes = _PHYSICAL[kind]
    if changes is None:
        rig.transport.state = replace(rig.transport.state, devices=())
    else:
        rig.transport.device(**changes)
    return event_kind


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("terminal", ["observed", "uncertain"])
def test_snapshot_before_mailbox_retains_exact_pending_physical_proof(rig, kind, terminal):
    rig.settings.saved_remote()
    if kind == "disconnect":
        rig.transport.device(connected=True)
    operation_id = begin_command(rig, kind)
    original_deadline = rig.manager._operation.deadline
    snapshot = rig.transport.snapshot
    fired = False

    def publish_after_sampling_old_dto():
        nonlocal fired
        old = snapshot()
        if not fired:
            fired = True
            event_kind = physical_change(rig, kind)
            rig.transport.emit(event_kind, operation_id)
            rig.transport.emit("finished", operation_id, code=terminal)
        return old

    with rig.manager._lock:
        rig.transport.snapshot = publish_after_sampling_old_dto
        rig.manager.tick()
        operation = rig.manager._operation
        assert operation.pending_observation == _PHYSICAL[kind][0]
        assert not operation.observed
        assert not rig.settings.saves
        assert operation.deadline == original_deadline
        rig.manager.tick()  # Newer authoritative sample, not an inferred property.
        assert operation.pending_observation is None
        assert operation.observed
        assert operation.phase == "observed"
        assert operation.error == ("" if terminal == "observed" else "uncertain")
        assert operation.deadline == original_deadline
    expected = [{"remote": None}] if kind == "forget" else []
    assert rig.settings.saves == expected
    rig.emit(_PHYSICAL[kind][0], operation_id)
    rig.emit("finished", operation_id, code="observed")
    assert rig.settings.saves == expected
    assert rig.state()["operation"]["error"] == ("" if terminal == "observed" else "uncertain")


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("invalidate", ["deadline", "lease", "controller", "identity", "config"])
def test_pending_observation_keeps_original_fences(rig, kind, invalidate):
    rig.settings.saved_remote()
    operation_id = begin_command(rig, kind)
    with rig.manager._lock:
        # First sample cannot yet confirm this exact positive notification.
        rig.transport.emit(_PHYSICAL[kind][0], operation_id)
        rig.transport.emit("finished", operation_id, code="observed")
        rig.manager.tick()
        assert rig.manager._operation.pending_observation
        physical_change(rig, kind)
        if invalidate == "deadline":
            rig.clock.now = rig.manager._operation.deadline
            rig.manager._lease_deadline = rig.clock.now + 5
        elif invalidate == "lease":
            rig.clock.advance(15)
        elif invalidate == "controller":
            rig.transport.state = replace(rig.transport.state, controller_epoch=4)
        elif invalidate == "identity":
            rig.transport.state = replace(rig.transport.state, devices=(Device(device_epoch=99),))
        else:
            rig.settings.saved_remote(address="33:44:55:66:77:88")
        rig.manager.tick()
        assert not rig.manager._operation.observed
        assert rig.manager._operation.pending_observation is None
        assert rig.manager._operation.error == "uncertain"
    assert not rig.settings.saves


@pytest.mark.parametrize("kind", _PHYSICAL)
def test_snapshot_truth_or_successful_terminal_without_positive_event_is_not_proof(rig, kind):
    rig.settings.saved_remote()
    operation_id = begin_command(rig, kind)
    physical_change(rig, kind)
    rig.emit("finished", operation_id, code="observed")
    assert not rig.manager._operation.observed
    assert not rig.settings.saves
    assert rig.state()["operation"]["phase"] != "observed"
    rig.manager.retire(PHONE)
    rig.emit(_PHYSICAL[kind][0], operation_id)
    assert not rig.settings.saves  # Retired late proof never starts config effects.


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("terminal", ["observed", "uncertain"])
def test_observed_reality_and_late_transport_certainty_are_independent(rig, kind, terminal):
    rig.settings.saved_remote()
    operation_id = begin_command(rig, kind)
    rig.emit(physical_change(rig, kind), operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    saved_once = copy.deepcopy(rig.settings.saves)
    rig.emit("finished", operation_id, code=terminal)
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.state()["operation"]["error"] == ("uncertain" if terminal == "uncertain" else "")
    # Retain outcome correlation even after owner and controller retirement.
    rig.manager.retire(PHONE)
    rig.transport.state = replace(rig.transport.state, controller_epoch=4)
    rig.emit("finished", operation_id, code="uncertain")
    assert rig.manager._owner is None
    assert rig.manager._operation.error == "uncertain"
    assert rig.manager._operation.phase == "observed"
    assert rig.settings.saves == saved_once
    assert rig.manager._operation.challenge is None
    assert rig.manager._operation.confirmation is None


@pytest.mark.parametrize("kind", ["discover", "pair", "connect", "disconnect", "forget"])
@pytest.mark.parametrize(
    "retirement",
    ["cancel", "expire", "release", "exact", "phones", "target", "controller", "config"],
)
def test_admitted_retirement_before_dispatch_notification_is_conservatively_uncertain(
    rig, kind, retirement
):
    rig.settings.saved_remote()
    operation_id = begin_command(rig, kind)
    assert not rig.manager._operation.dispatched
    if retirement == "cancel":
        rig.request("cancel", operation_id=operation_id)
    elif retirement == "expire":
        rig.advance(15)
    elif retirement == "release":
        rig.request("release")
    elif retirement == "exact":
        rig.manager.retire(PHONE)
    elif retirement == "phones":
        rig.manager.retire_phones()
    elif retirement == "target":
        rig.transport.state = replace(rig.transport.state, adapters=(), devices=())
        rig.manager.tick()
    elif retirement == "controller":
        rig.transport.state = replace(rig.transport.state, controller_epoch=4)
        rig.manager.tick()
    else:
        rig.settings.saved_remote(address="33:44:55:66:77:88")
        rig.manager.tick()
    operation = rig.manager._operation
    assert operation.retired and operation.error == "uncertain"
    assert operation.pending_observation is None
    owner_after = rig.manager._owner
    calls_after = list(rig.transport.calls)
    # These were dispatched before retirement but delivered afterwards, including
    # when the CURRENT controller no longer matches the old outcome's epoch.
    for event in ("requested", "accepted"):
        rig.emit(event, operation_id, **event_target(kind))
    rig.emit("finished", operation_id, code="uncertain", **event_target(kind))
    assert operation.error == "uncertain"
    assert rig.manager._owner == owner_after
    assert rig.transport.calls == calls_after
    assert operation.challenge is operation.confirmation is None
    if kind == "forget":
        rig.transport.state = replace(rig.transport.state, devices=())
        rig.emit("forgotten", operation_id)
        assert not rig.settings.saves


@pytest.mark.parametrize("kind", ["discover", "pair", "connect", "disconnect", "forget"])
def test_new_operation_never_receives_old_outcome_uncertainty(rig, kind):
    old_id = begin_command(rig, kind)
    rig.request("cancel", operation_id=old_id)
    new_id = rig.begin("pair")[0]
    for event in ("requested", "accepted", "finished"):
        rig.emit(event, old_id, code="uncertain", **event_target(kind))
    assert rig.state()["operation"]["id"] == new_id
    assert rig.state()["operation"]["phase"] == "queued"
    assert rig.state()["operation"]["error"] == ""


def overflow(rig):
    for _ in range(65):
        rig.transport.emit("inventory", None, device_id=None, device_epoch=0)


def poison_from_hook(rig, source, trigger):
    target = rig.manager if source == "config" else rig.transport
    attribute = "_get_config" if source == "config" else "snapshot"
    original = getattr(target, attribute)
    count = 0

    def hook():
        nonlocal count
        result = original()
        count += 1
        if count == trigger:
            overflow(rig)
        return result

    setattr(target, attribute, hook)


def assert_poisoned_cleanup(rig, response=None):
    if response is not None:
        status, envelope = response
        assert status == 503 and envelope["error"] == "unavailable"
        assert not ({"lease", "challenge", "confirmation_id", "observation"} & set(envelope))
    wait_until(lambda: rig.transport.closed.is_set())
    assert rig.transport.close_count == 1
    assert rig.transport.close_thread is rig.manager._thread
    assert rig.manager._owner is None
    assert not rig.settings.saves


@pytest.mark.parametrize(
    "kind,source,trigger",
    [
        (kind, source, trigger)
        for kind in ("discover", "pair", "connect", "disconnect", "forget", "answer", "cancel")
        for source in ("config", "snapshot")
        for trigger in (1, 2)
        if kind != "cancel" or trigger == 1
    ],
)
def test_poison_inside_tick_or_dispatch_hook_fences_management_and_answers(
    rig, kind, source, trigger
):
    if kind == "forget":
        operation_id, response = rig.begin("forget_prepare")
        op = "forget_confirm"
        fields = {"operation_id": operation_id, "confirmation_id": response["confirmation_id"]}
    elif kind in ("answer", "cancel"):
        operation_id = rig.begin("pair")[0]
        rig.emit("challenge", operation_id, challenge=Challenge())
        op = kind
        fields = {"operation_id": operation_id}
        if kind == "answer":
            fields.update(challenge_id="challenge", answer={"pin": "x"})
    else:
        op, fields = kind, ({} if kind == "discover" else {"device_id": "device"})
    with rig.manager._lock:
        poison_from_hook(rig, source, trigger)
        before = list(rig.transport.calls)
        result = rig.request(op, **fields)
        assert rig.transport.calls == before
    assert_poisoned_cleanup(rig, result)


@pytest.mark.parametrize("op", ["reset", "unmap"])
@pytest.mark.parametrize(
    "source,trigger", [("config", 1), ("config", 2), ("config", 3), ("snapshot", 1)]
)
def test_poison_inside_current_mapping_save_hooks_prevents_write(rig, op, source, trigger):
    rig.settings.saved_remote()
    revision = rig.state()["revision"]
    original = copy.deepcopy(rig.settings.section)
    with rig.manager._lock:
        poison_from_hook(rig, source, trigger)
        fields = {"key": "KEY_UP"} if op == "unmap" else {}
        result = rig.request(op, revision=revision, **fields)
    assert rig.settings.section == original
    assert_poisoned_cleanup(rig, result)


@pytest.mark.parametrize("source,trigger", [("config", 1), ("config", 2), ("snapshot", 1)])
def test_poison_inside_forget_resolution_prevents_exact_identity_clear(rig, source, trigger):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    with rig.manager._lock:
        rig.transport.state = replace(rig.transport.state, devices=())
        rig.transport.emit("forgotten", operation_id)
        rig.manager.tick()  # Retain proof; requires another sample before save.
        assert rig.manager._operation.pending_observation == "forgotten"
        poison_from_hook(rig, source, trigger)
        rig.manager.tick()
        assert rig.manager._failed
    assert rig.settings.section["remote"] is not None
    assert_poisoned_cleanup(rig)


@pytest.mark.parametrize("private", ["challenge", "confirmation", "acquire"])
@pytest.mark.parametrize("source", ["config", "snapshot"])
def test_poison_during_owner_poll_tick_never_returns_secrets(rig, private, source):
    if private == "challenge":
        operation_id = rig.begin()[0]
        rig.emit("challenge", operation_id, challenge=Challenge())
    elif private == "confirmation":
        rig.begin("forget_prepare")
    else:
        rig.request("release")
    with rig.manager._lock:
        poison_from_hook(rig, source, 1)
        result = (
            rig.manager.request(PHONE, {"op": "acquire"})
            if private == "acquire"
            else rig.request("poll")
        )
    assert_poisoned_cleanup(rig, result)


def test_poison_while_draining_mailbox_drops_later_forget_effect(rig):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    handler = rig.manager._event
    fired = False

    def poison_during_drain(event, now):
        nonlocal fired
        handler(event, now)
        if not fired:
            fired = True
            overflow(rig)

    with rig.manager._lock:
        rig.manager._event = poison_during_drain
        rig.transport.state = replace(rig.transport.state, devices=())
        rig.transport.emit("accepted", operation_id)
        rig.transport.emit("forgotten", operation_id)
        rig.manager.tick()
        assert rig.manager._failed
        assert rig.manager._operation.pending_observation is None
    assert_poisoned_cleanup(rig)


def test_known_poison_direct_command_save_and_private_response_guards(rig):
    operation_id = rig.begin()[0]
    rig.emit("challenge", operation_id, challenge=Challenge())
    with rig.manager._lock:
        before = list(rig.transport.calls)
        overflow(rig)
        assert not rig.manager._command("answer", operation_id, "challenge", {"pin": "x"})
        assert not rig.manager._command("cancel", operation_id)
        assert rig.manager._save({"remote": None}, 0) == "unavailable"
        result = rig.manager._reply(private=True)
        assert rig.transport.calls == before
    assert_poisoned_cleanup(rig, result)


@pytest.mark.parametrize("kind", ["pair", "connect", "disconnect", "forget"])
@pytest.mark.parametrize("code", ["busy", "unavailable", "invalidated", "adapter_off", "expired"])
def test_documented_predispatch_epoch_zero_rejections_terminate_promptly(rig, kind, code):
    previous = rig.begin("pair")[0]
    rig.request("cancel", operation_id=previous)
    # Fake cleanup is still pending; new command bool is admission only.
    operation_id = begin_command(rig, kind)
    rig.emit("finished", operation_id, device_epoch=0, code=code)
    operation = rig.manager._operation
    assert operation.phase == "finished" and operation.error == code
    assert not operation.observed
    assert rig.clock.now == 100
    assert not rig.settings.saves


@pytest.mark.parametrize(
    "changed",
    [{"operation_id": "old"}, {"controller_epoch": 2}, {"device_id": "other"}, {"device_epoch": 1}],
)
def test_epoch_zero_rejection_requires_exact_remaining_correlation(rig, changed):
    operation_id = rig.begin()[0]
    fields = {"operation_id": operation_id, "device_epoch": 0, **changed}
    rig.emit("finished", code="busy", **fields)
    assert rig.state()["operation"]["phase"] == "queued"


@pytest.mark.parametrize("kind", _PHYSICAL)
def test_epoch_zero_is_never_a_positive_observation_or_challenge_wildcard(rig, kind):
    operation_id = begin_command(rig, kind)
    event = physical_change(rig, kind)
    rig.emit(event, operation_id, device_epoch=0)
    rig.emit("challenge", operation_id, device_epoch=0, challenge=Challenge())
    assert not rig.manager._operation.observed
    assert rig.manager._operation.pending_observation is None
    assert rig.manager._operation.challenge is None
    assert not rig.settings.saves


@pytest.mark.parametrize(
    "code", ["uncertain", "observed", "denied", "failed", "cancelled", "rejected"]
)
def test_epoch_zero_does_not_relax_undocumented_terminal_codes(rig, code):
    operation_id = rig.begin()[0]
    rig.emit("finished", operation_id, device_epoch=0, code=code)
    assert rig.state()["operation"]["phase"] == "queued"


def test_placeholder_rejection_cannot_override_started_operation(rig):
    operation_id = rig.begin()[0]
    rig.emit("requested", operation_id)
    rig.emit("finished", operation_id, device_epoch=0, code="busy")
    assert rig.state()["operation"]["phase"] == "requested"


@pytest.mark.parametrize("retirement", ["cancel", "expire", "release", "exact", "phones"])
def test_prepared_forget_has_no_admission_or_dispatch_uncertainty(rig, retirement):
    operation_id, _ = rig.begin("forget_prepare")
    if retirement == "cancel":
        rig.request("cancel", operation_id=operation_id)
    elif retirement == "expire":
        rig.advance(15)
    elif retirement == "release":
        rig.request("release")
    elif retirement == "exact":
        rig.manager.retire(PHONE)
    else:
        rig.manager.retire_phones()
    assert not rig.manager._operation.admitted
    expected = "expired" if retirement == "expire" else "cancelled"
    assert rig.manager._operation.error == expected
    rig.emit("requested", operation_id)
    rig.emit("finished", operation_id, code="uncertain")
    assert rig.manager._operation.error == expected
    assert not rig.transport.calls
    assert rig.manager._operation.confirmation is None


@pytest.mark.parametrize(
    "changed",
    [{"operation_id": "old"}, {"controller_epoch": 2}, {"device_id": "other"}, {"device_epoch": 0}],
)
def test_retained_observed_outcome_uncertainty_still_requires_exact_correlation(rig, changed):
    operation_id = rig.begin()[0]
    rig.emit("paired", operation_id)  # Contradictory sample cannot confirm it yet.
    rig.transport.device(paired=True)
    assert rig.state()["operation"]["phase"] == "observed"
    rig.emit("finished", operation_id, code="observed")
    rig.manager.retire(PHONE)
    assert rig.manager._operation.error == ""
    rig.emit("finished", code="uncertain", **{"operation_id": operation_id, **changed})
    assert rig.manager._operation.error == ""
    rig.emit("finished", operation_id, code="uncertain")
    assert rig.manager._operation.error == "uncertain"
    assert rig.manager._owner is None


def test_discovery_terminal_uncertainty_is_not_lost_after_owner_retirement(rig):
    operation_id = rig.begin("discover")[0]
    fields = event_target("discover")
    rig.emit("finished", operation_id, code="cancelled", **fields)
    rig.manager.retire(PHONE)
    assert rig.manager._operation.error == "cancelled"
    rig.emit("finished", operation_id, code="uncertain", **fields)
    assert rig.manager._operation.error == "uncertain"
    assert rig.manager._owner is None
    assert len(rig.transport.calls) == 1


def test_late_uncertain_forget_does_not_rollback_or_clear_new_saved_config(rig):
    rig.settings.saved_remote()
    operation_id = confirm_forget(rig)
    rig.emit(physical_change(rig, "forget"), operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.settings.saves == [{"remote": None}]
    rig.emit("finished", operation_id, code="observed")
    rig.manager.retire_phones()
    rig.settings.saved_remote(address="33:44:55:66:77:88")
    rig.emit("finished", operation_id, code="uncertain")
    rig.emit("forgotten", operation_id)
    assert rig.state()["operation"]["phase"] == "observed"
    assert rig.state()["operation"]["error"] == "uncertain"
    assert rig.settings.section["remote"]["identity"]["address"] == "33:44:55:66:77:88"
    assert rig.settings.saves == [{"remote": None}]
    assert rig.manager._owner is None


@pytest.mark.parametrize("kind", _PHYSICAL)
def test_event_drain_cannot_validate_pending_observation_past_original_deadline(rig, kind):
    rig.settings.saved_remote()
    operation_id = begin_command(rig, kind)
    with rig.manager._lock:
        rig.transport.emit(_PHYSICAL[kind][0], operation_id)
        rig.manager.tick()
        physical_change(rig, kind)
        handler = rig.manager._event

        def cross_deadline(event, now):
            handler(event, now)
            rig.clock.now = rig.manager._operation.deadline

        rig.manager._event = cross_deadline
        rig.transport.emit("finished", operation_id, code="observed")
        rig.manager.tick()
        assert not rig.manager._operation.observed
        assert rig.manager._operation.pending_observation is None
        assert rig.manager._operation.error == "uncertain"
    assert not rig.settings.saves


def begin_terminal_pending_proof(rig, kind, terminal="uncertain"):
    if kind == "disconnect":
        rig.transport.device(connected=True)
    operation_id = begin_command(rig, kind)
    # Keep the authoritative inventory contradictory even during later HTTP
    # ticks. Only the exact event exists so far, not a confirming snapshot.
    rig.transport.emit(_PHYSICAL[kind][0], operation_id)
    rig.transport.emit("finished", operation_id, code=terminal)
    rig.manager.tick()
    operation = rig.manager._operation
    assert operation.phase == "finished" and not operation.active
    assert operation.pending_observation == _PHYSICAL[kind][0]
    assert not operation.retired and not operation.observed
    return operation


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("terminal", ["uncertain", "failed", "denied"])
def test_public_cancel_retires_terminal_pending_proof_before_later_confirmation(
    rig, kind, terminal
):
    rig.settings.saved_remote()
    original = copy.deepcopy(rig.settings.section)
    with rig.manager._lock:
        operation = begin_terminal_pending_proof(rig, kind, terminal)
        deadline = operation.deadline
        calls = list(rig.transport.calls)
        owner, lease = rig.manager._owner, rig.manager._lease
        assert operation.outstanding
        status, response = rig.request("cancel", operation_id=operation.id)
        assert status == 200
        assert response["state"]["operation"]["error"] == "uncertain"
        assert response["state"]["operation"]["remaining_ms"] == 0
        assert operation.retired and not operation.outstanding
        assert operation.pending_observation is None
        assert operation.deadline == deadline
        assert rig.manager._owner == owner and rig.manager._lease == lease
        # Transport already terminated: cancelling proof must not issue another
        # transport command or create a new lifetime/permission.
        assert rig.transport.calls == calls
        assert set(response) == {"state"}
        physical_change(rig, kind)
        for event in (_PHYSICAL[kind][0], _PHYSICAL[kind][0], "accepted", "finished"):
            rig.transport.emit(event, operation.id, code="observed")
        rig.manager.tick()
        rig.manager.tick()
        assert not operation.observed and operation.phase == "finished"
        assert operation.error == "uncertain"
        assert operation.pending_observation is None
        assert operation.challenge is operation.confirmation is None
        assert rig.request("cancel", operation_id=operation.id)[0] == 409
        assert rig.transport.calls == calls
    assert rig.settings.section == original
    assert not rig.settings.saves


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("retirement", ["cancel", "expiry"])
def test_terminal_pending_proof_is_exclusive_until_cancel_or_original_expiry(rig, kind, retirement):
    rig.settings.saved_remote()
    with rig.manager._lock:
        operation = begin_terminal_pending_proof(rig, kind)
        deadline = operation.deadline
        revision = rig.state()["revision"]
        requests = [
            ("discover", {}),
            *[
                (op, {"device_id": "device"})
                for op in ("pair", "connect", "disconnect", "forget_prepare", "select_remote")
            ],
            ("learn", {"action": "up"}),
            ("unmap", {"key": "KEY_UP", "revision": revision}),
            ("reset", {"revision": revision}),
        ]
        calls = list(rig.transport.calls)
        for op, fields in requests:
            status, response = rig.request(op, **fields)
            assert status == 409 and response["error"] == "busy"
            assert rig.manager._operation is operation and operation.outstanding
        assert rig.transport.calls == calls and not rig.settings.saves
        if retirement == "cancel":
            assert rig.request("cancel", operation_id=operation.id)[0] == 200
        else:
            while rig.clock.now < deadline:
                rig.advance(5, poll=True)
                assert operation.deadline == deadline
            assert rig.manager._owner == PHONE  # Operation expiry, not lease loss.
        assert operation.retired and not operation.outstanding
        assert operation.pending_observation is None and operation.error == "uncertain"
        assert rig.transport.calls == calls
        new_id, _ = rig.begin("discover")
        assert new_id != operation.id
        physical_change(rig, kind)
        rig.emit(_PHYSICAL[kind][0], operation.id)
        rig.emit("finished", operation.id, code="uncertain")
        assert rig.manager._operation.id == new_id
        assert rig.manager._operation.phase == "queued"
    assert not rig.settings.saves


@pytest.mark.parametrize("kind", _PHYSICAL)
@pytest.mark.parametrize("mode", ["observed", "uncertain", "busy"])
def test_completed_terminal_outcome_without_pending_proof_does_not_block_new_work(rig, kind, mode):
    operation_id = begin_command(rig, kind)
    if mode == "observed":
        rig.emit(physical_change(rig, kind), operation_id)
        rig.manager.tick()
    else:
        fields = {"device_epoch": 0} if mode == "busy" else {}
        rig.emit("finished", operation_id, code=mode, **fields)
    operation = rig.manager._operation
    assert not operation.active and not operation.outstanding
    assert operation.pending_observation is None
    assert rig.begin("discover")[0] != operation_id


@pytest.mark.parametrize("kind", _PHYSICAL)
def test_terminal_pending_proof_does_not_reauthorize_answers_confirmations_or_private_state(
    rig, kind
):
    with rig.manager._lock:
        operation = begin_terminal_pending_proof(rig, kind)
        calls = list(rig.transport.calls)
        assert set(rig.poll()) == {"state"}
        for op, fields in [
            ("answer", {"challenge_id": "old", "answer": {"pin": "x"}}),
            ("forget_confirm", {"confirmation_id": "old"}),
            ("bind", {"observation_id": "old"}),
            ("test", {"observation_id": "old"}),
        ]:
            assert rig.request(op, operation_id=operation.id, **fields)[0] == 409
        assert operation.outstanding and not operation.active
        assert operation.pending_observation == _PHYSICAL[kind][0]
        assert operation.challenge is operation.confirmation is None
        assert rig.transport.calls == calls
    assert not rig.settings.saves


def test_terminal_pending_proof_keeps_adapter_pin_and_original_remaining_deadline(rig):
    with rig.manager._lock:
        operation = begin_terminal_pending_proof(rig, "pair")
        rig.transport.state = replace(
            rig.transport.state,
            adapters=(Adapter(id="hci0", address=A0), Adapter()),
        )
        state = rig.state()
        assert state["adapter"]["id"] == "hci1"
        assert state["operation"]["phase"] == "finished"
        assert state["operation"]["remaining_ms"] == 60000
        rig.advance(5, poll=True)
        assert rig.state()["operation"]["remaining_ms"] == 55000
        assert rig.request("cancel", operation_id=operation.id)[0] == 200
        state = rig.state()
        assert state["adapter"]["id"] == "hci0"
        assert state["operation"]["remaining_ms"] == 0
