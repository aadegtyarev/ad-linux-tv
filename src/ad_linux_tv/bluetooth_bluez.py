"""Rootless, explicitly started BlueZ transport (no policy or input-device access).

Public API: BluezTransport.start(on_event), snapshot(), discover(operation_id,
adapter_id, deadline), stop_discovery(operation_id), pair/connect/disconnect/forget
(operation_id, device_id, deadline), answer(operation_id, challenge_id, answer),
cancel(operation_id), close(). Commands return bool: queued, NOT method success.
The trusted coordinator must use unique operation IDs, never reused across epochs;
control calls are correlated by these IDs, not by a client-supplied D-Bus path.
Deadlines use the injected monotonic clock; durations are capped (discovery 30s,
pair/connect 60s, disconnect/forget 15s). One operation, 32 queued commands, 8
adapters, 128 tracked objects and 64 published devices. No adapter auto-selection.

Frozen DTOs below are the integration interface. AdapterSnapshot contains all
valid adapters, not a selected adapter. IDs are opaque per-controller handles;
addresses are canonical identity metadata, never D-Bus paths. An empty device
address_type means unknown/unproven, not a persistable identity. Snapshot available
means bus/agent ready; no_adapter and per-adapter powered flags remain authoritative.
Device epochs change
on removal/replacement; controller epochs change on service loss. BluezEvent has
kind, operation_id, controller_epoch, device_id, device_epoch, code and challenge.
Kinds: inventory, unavailable, requested (dispatched), accepted (method returned),
paired, connected, disconnected, forgotten (observed), challenge, finished.
Cancellation stops waiting; it never asserts bond/effect rollback.
Finished codes: observed, expired, uncertain, cancelled, invalidated, rejected,
unavailable, busy, adapter_off, denied, failed. Acceptance is NOT observation.
Inventory/unsolicited observations have no operation_id. Challenge fields: id,
kind (pin, passkey, confirmation, display_pin, display_passkey), deadline, value,
entered. Only confirmation/pin/passkey accept answers; display values are private
memory-only secrets. Do not log events or expose them to non-owning clients.

Callbacks run on the dedicated thread: they MUST be quick/nonblocking and must
not call close(). A raising listener is retired, including its active operation.
close() suppresses new callbacks immediately and joins the thread; a stuck caller
callback raises rather than silently leaking a worker. No automatic restart or
retry after bus loss or a cleanup failure (which disconnects to release this
client's discovery session). Construct a new transport to reconnect after bus
loss. Service owner replacement on the same bus is handled with fresh epochs.

bus_factory (async, returns a connected dbus-fast-compatible MessageBus) and clock
are injectable; a factory owns partial resources until it returns successfully.
Imports of dbus-fast and all IO occur only after start().
"""

import asyncio
import contextlib
import math
import queue
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Callable

_BLUEZ = "org.bluez"
_ADAPTER = "org.bluez.Adapter1"
_DEVICE = "org.bluez.Device1"
_AGENT = "org.bluez.Agent1"
_OM = "org.freedesktop.DBus.ObjectManager"
_PROPS = "org.freedesktop.DBus.Properties"
_DBUS = "org.freedesktop.DBus"
_AGENT_PATH = "/org/ad_linux_tv/agent"
_HID = frozenset({"00001124-0000-1000-8000-00805f9b34fb", "00001812-0000-1000-8000-00805f9b34fb"})
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_ADDRESS = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")
_MATCHES = (
    "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
    "member='NameOwnerChanged',arg0='org.bluez'",
    "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.ObjectManager'",
    "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties'",
)


@dataclass(frozen=True)
class Adapter:
    id: str
    address: str
    powered: bool
    discovering: bool


@dataclass(frozen=True)
class Device:
    id: str
    adapter_id: str
    address: str
    address_type: str
    name: str
    paired: bool
    connected: bool
    device_epoch: int


@dataclass(frozen=True)
class AdapterSnapshot:
    available: bool = False
    reason: str = "not_started"
    controller_epoch: int = 0
    adapters: tuple[Adapter, ...] = ()
    devices: tuple[Device, ...] = ()


@dataclass(frozen=True)
class Challenge:
    id: str
    kind: str
    deadline: float
    value: str = field(default="", repr=False)
    entered: int = 0


@dataclass(frozen=True)
class BluezEvent:
    kind: str
    operation_id: str | None
    controller_epoch: int
    device_id: str | None = None
    device_epoch: int = 0
    code: str = ""
    challenge: Challenge | None = field(default=None, repr=False)


@dataclass
class _Object:
    id: str
    epoch: int
    props: dict


@dataclass
class _Operation:
    id: str
    kind: str
    adapter_path: str
    device_path: str | None
    device_id: str | None
    device_epoch: int
    epoch: int
    deadline: float
    dispatched: bool = False
    discovery_owned: bool = False
    task: asyncio.Task | None = None
    challenge: Challenge | None = None
    answer: asyncio.Future | None = None


def _address(value):
    if not isinstance(value, str) or len(value) != 17:
        return None
    value = value.upper()
    return (
        value
        if _ADDRESS.fullmatch(value) and value not in {"00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"}
        else None
    )


def _name(value):
    if not isinstance(value, str):
        return ""
    result = ""
    for char in value[:320]:
        if char.isprintable() and not unicodedata.category(char).startswith("C"):
            if len(result) == 80 or len((result + char).encode("utf-8")) > 160:
                break
            result += char
    return result


def _agent_service(transport):
    # Lazy factory keeps dependency absence harmless at import/construction time.
    from dbus_fast.service import ServiceInterface, method

    class Agent(ServiceInterface):
        def __init__(self):
            super().__init__(_AGENT)

        @method()
        async def Release(self):
            transport._release_agent("Release")

        @method()
        async def Cancel(self):
            transport._release_agent("Cancel")

        @method()
        async def RequestPinCode(self, device: "o") -> "s":  # noqa: F821
            return await transport._agent("RequestPinCode", device)

        @method()
        async def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: F821
            await transport._agent("DisplayPinCode", device, pincode)

        @method()
        async def RequestPasskey(self, device: "o") -> "u":  # noqa: F821
            return await transport._agent("RequestPasskey", device)

        @method()
        async def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: F821
            await transport._agent("DisplayPasskey", device, passkey, entered)

        @method()
        async def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: F821
            await transport._agent("RequestConfirmation", device, passkey)

        @method()
        async def RequestAuthorization(self, device: "o"):  # noqa: F821
            await transport._agent("RequestAuthorization", device)

        @method()
        async def AuthorizeService(self, device: "o", service: "s"):  # noqa: F821
            await transport._agent("AuthorizeService", device, service)

    return Agent()


class BluezTransport:
    def __init__(self, *, bus_factory=None, clock: Callable[[], float] = time.monotonic):
        self._factory = bus_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshot = AdapterSnapshot()
        self._closed = threading.Event()
        self._thread = None
        self._loop = None
        self._main_task = None
        self._shutting_down = False
        self._listener = None
        self._queue = queue.Queue(maxsize=32)
        self._wake = None
        self._bus = None
        self._owner = None
        self._epoch = 0
        self._serial = 0
        self._adapters = {}
        self._devices = {}
        self._op = None
        self._registered = False
        self._inventory_ready = False
        self._exported = False
        self._matches = []
        self._agent_task = None
        self._bootstrap_task = None
        self._cleanup_task = None
        self._service = None
        self._pending = {}

    def start(self, on_event: Callable[[BluezEvent], None]) -> None:
        with self._lock:
            if self._thread is not None or self._closed.is_set():
                raise RuntimeError("transport already started or closed")
            self._listener = on_event
            self._thread = threading.Thread(target=self._run, name="bluez", daemon=True)
            self._thread.start()

    def snapshot(self) -> AdapterSnapshot:
        with self._lock:
            return self._snapshot

    def discover(self, operation_id: str, adapter_id: str, deadline: float) -> bool:
        return self._submit("discover", operation_id, adapter_id, deadline)

    def stop_discovery(self, operation_id: str) -> bool:
        return self._submit("stop_discovery", operation_id)

    def pair(self, operation_id: str, device_id: str, deadline: float) -> bool:
        return self._submit("pair", operation_id, device_id, deadline)

    def connect(self, operation_id: str, device_id: str, deadline: float) -> bool:
        return self._submit("connect", operation_id, device_id, deadline)

    def disconnect(self, operation_id: str, device_id: str, deadline: float) -> bool:
        return self._submit("disconnect", operation_id, device_id, deadline)

    def forget(self, operation_id: str, device_id: str, deadline: float) -> bool:
        return self._submit("forget", operation_id, device_id, deadline)

    def answer(self, operation_id: str, challenge_id: str, answer: dict) -> bool:
        # Copy and validate before crossing threads; never retain caller-owned data.
        if not isinstance(answer, dict) or len(answer) != 1:
            return False
        key, value = next(iter(answer.items()))
        if key == "confirm":
            valid = type(value) is bool
        elif key == "pin":
            valid = isinstance(value, str) and bool(re.fullmatch(r"[\x21-\x7e]{1,16}", value))
        elif key == "passkey":
            valid = isinstance(value, str) and bool(re.fullmatch(r"[0-9]{6}", value))
        else:
            valid = False
        if not valid or not isinstance(challenge_id, str) or not _ID.fullmatch(challenge_id):
            return False
        return self._submit("answer", operation_id, challenge_id, (key, value))

    def cancel(self, operation_id: str) -> bool:
        return self._submit("cancel", operation_id)

    def _submit(self, kind, operation_id, *args):
        if not isinstance(operation_id, str) or not _ID.fullmatch(operation_id):
            return False
        if kind in {"discover", "pair", "connect", "disconnect", "forget"}:
            target, deadline = args
            if not isinstance(target, str) or not _ID.fullmatch(target):
                return False
            if (
                type(deadline) not in {int, float}
                or type(deadline) is float
                and not math.isfinite(deadline)
            ):
                return False
        with self._lock:
            if (
                self._thread is None
                or self._closed.is_set()
                or self._shutting_down
                or not self._thread.is_alive()
            ):
                return False
            try:
                self._queue.put_nowait((kind, operation_id, args))
            except queue.Full:
                return False
            if self._loop and self._wake:
                with contextlib.suppress(RuntimeError):
                    self._loop.call_soon_threadsafe(self._wake.set)
            return True

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            loop, wake = self._loop, self._wake
        if loop and wake and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(wake.set)
                loop.call_soon_threadsafe(self._request_close)
        if self._thread:
            if self._thread is threading.current_thread():
                raise RuntimeError("close must run outside callback")
            self._thread.join(8)
            if self._thread.is_alive():
                raise RuntimeError("transport shutdown did not finish")
        with self._lock:
            self._listener = None
            self._snapshot = AdapterSnapshot(False, "closed", self._epoch)

    def _request_close(self):
        if self._main_task and not self._shutting_down:
            self._main_task.cancel()

    def _run(self):
        asyncio.run(self._main())

    async def _main(self):
        if self._closed.is_set():
            return
        self._main_task = asyncio.current_task()
        from_import = False
        try:
            from dbus_fast import Message, MessageType
            from dbus_fast.aio import MessageBus
            from dbus_fast.constants import BusType

            from_import = True
            self._Message, self._MessageType = Message, MessageType
            self._loop = asyncio.get_running_loop()
            self._wake = asyncio.Event()
            if self._factory:
                self._bus = await asyncio.wait_for(self._factory(), 2)
            else:
                self._bus = MessageBus(bus_type=BusType.SYSTEM)
                await asyncio.wait_for(self._bus.connect(), 2)
            self._service = _agent_service(self)
            self._bus.add_message_handler(self._on_message)
            self._bus.export(_AGENT_PATH, self._service)
            self._exported = True
            for rule in _MATCHES:
                await self._dbus("AddMatch", "s", [rule])
                self._matches.append(rule)
            self._epoch += 1
            query_epoch = self._epoch
            try:
                owner = await self._dbus("GetNameOwner", "s", [_BLUEZ])
            except Exception:
                if query_epoch == self._epoch:
                    self._unavailable("service_unavailable")
            else:
                if query_epoch == self._epoch:
                    self._owner = owner[0]
                    await self._bootstrap(query_epoch)
            while not self._closed.is_set():
                self._wake.clear()
                for _ in range(32):
                    try:
                        kind, op_id, args = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    self._command(kind, op_id, args)
                if self._op and self._clock() >= self._op.deadline:
                    self._retire("uncertain" if self._op.dispatched else "expired")
                if getattr(self._bus, "connected", True) is False:
                    self._invalidate("bus_unavailable")
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), 0.05)
        except asyncio.CancelledError:
            pass
        except ImportError:
            self._unavailable("dependency_unavailable")
        except Exception:
            self._unavailable("bus_unavailable" if from_import else "dependency_unavailable")
        finally:
            self._shutting_down = True
            await self._shutdown()

    async def _dbus(self, member, signature="", body=None):
        return await self._call(_DBUS, "/org/freedesktop/DBus", _DBUS, member, signature, body)

    async def _call(
        self, destination, path, interface, member, signature="", body=None, *, timeout=2
    ):
        # Use public send/next_serial plus our bounded reply ledger. dbus-fast.call()
        # retains its reply handler after cancellation until a remote reply arrives.
        # Pair cancellation/timeouts must not grow that ledger indefinitely.
        if len(self._pending) >= 8:
            raise RuntimeError("call capacity")
        msg = self._Message(
            destination=destination,
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=body or [],
            serial=self._bus.next_serial(),
        )
        future = asyncio.get_running_loop().create_future()
        self._pending[msg.serial] = (destination, future)
        try:
            async with asyncio.timeout(timeout):
                await self._bus.send(msg)
                reply = await future
        finally:
            self._pending.pop(msg.serial, None)
        if reply.message_type == self._MessageType.ERROR:
            from dbus_fast import DBusError

            # Only a fixed code escapes; never propagate remote text.
            code = (
                "uncertain"
                if reply.error_name
                in {
                    "org.freedesktop.DBus.Error.NoReply",
                    "org.freedesktop.DBus.Error.Timeout",
                    "org.freedesktop.DBus.Error.Disconnected",
                }
                else "denied"
                if reply.error_name
                in {
                    "org.freedesktop.DBus.Error.AccessDenied",
                    "org.bluez.Error.NotAuthorized",
                    "org.bluez.Error.AuthenticationRejected",
                    "org.bluez.Error.Rejected",
                }
                else "failed"
            )
            raise DBusError("org.ad_linux_tv.Error.Failed", code)
        return reply.body

    async def _bootstrap(self, epoch):
        try:
            owner = self._owner
            body = await self._call(owner, "/", _OM, "GetManagedObjects")
            if epoch != self._epoch or self._closed.is_set():
                return
            # Adapters first; no first-hci or power-selection policy here.
            objects = body[0]
            for path, interfaces in objects.items():
                if _ADAPTER in interfaces:
                    self._add(path, _ADAPTER, interfaces[_ADAPTER])
            for path, interfaces in objects.items():
                if _DEVICE in interfaces:
                    self._add(path, _DEVICE, interfaces[_DEVICE])
            # Signals arriving while RegisterAgent is pending must not be lost.
            self._inventory_ready = True
            await self._call(
                owner,
                "/org/bluez",
                "org.bluez.AgentManager1",
                "RegisterAgent",
                "os",
                [_AGENT_PATH, "KeyboardDisplay"],
            )
            if epoch != self._epoch or self._closed.is_set():
                return
            self._registered = True
            self._publish()
        except Exception:
            if epoch == self._epoch:
                self._inventory_ready = False
                self._adapters.clear()
                self._devices.clear()
                self._unavailable("service_unavailable")

    def _unavailable(self, reason):
        with self._lock:
            self._snapshot = AdapterSnapshot(False, reason, self._epoch)
        self._emit("unavailable", code=reason)

    def _publish(self):
        adapters = tuple(
            Adapter(
                obj.id,
                obj.props["Address"],
                obj.props.get("Powered") is True,
                obj.props.get("Discovering") is True,
            )
            for obj in self._adapters.values()
        )
        devices = []
        for obj in sorted(self._devices.values(), key=lambda o: o.props.get("Paired") is not True):
            adapter = self._adapters.get(obj.props.get("Adapter"))
            if not adapter:
                continue
            p = obj.props
            devices.append(
                Device(
                    obj.id,
                    adapter.id,
                    p["Address"],
                    p.get("AddressType", ""),
                    _name(p.get("Alias", p.get("Name"))),
                    p.get("Paired") is True,
                    p.get("Connected") is True,
                    obj.epoch,
                )
            )
        reason = ("" if adapters else "no_adapter") if self._registered else "starting"
        with self._lock:
            self._snapshot = AdapterSnapshot(
                self._registered, reason, self._epoch, adapters, tuple(devices[:64])
            )
        self._emit("inventory")

    def _emit(self, kind, op=None, *, code="", challenge=None, device=None):
        if self._closed.is_set() or self._listener is None:
            return
        event = BluezEvent(
            kind,
            op.id if op else None,
            op.epoch if op else self._epoch,
            op.device_id if op else device.id if device else None,
            op.device_epoch if op else device.epoch if device else 0,
            code,
            challenge,
        )
        try:
            self._listener(event)
        except Exception:
            self._listener = None
            self._retire("cancelled")

    @staticmethod
    def _props(raw):
        allowed = {
            "Address",
            "AddressType",
            "Adapter",
            "Powered",
            "Discovering",
            "Paired",
            "Connected",
            "Alias",
            "Name",
        }
        props = {
            key: getattr(value, "value", value) for key, value in raw.items() if key in allowed
        }
        for key in ("Name", "Alias"):
            if key in props:
                props[key] = _name(props[key])
        if "AddressType" in props and props["AddressType"] not in ("public", "random"):
            props["AddressType"] = ""
        for key in ("Powered", "Discovering", "Paired", "Connected"):
            if key in props and type(props[key]) is not bool:
                props[key] = None
        return props

    def _add(self, path, interface, raw):
        if not isinstance(path, str) or len(path) > 256:
            return
        props = self._props(raw)
        address = _address(props.get("Address"))
        if not address:
            self._remove(path, interface)
            return
        props["Address"] = address
        if interface == _ADAPTER:
            objects, limit = self._adapters, 8
        else:
            adapter = props.get("Adapter")
            if not isinstance(adapter, str) or adapter not in self._adapters:
                self._remove(path, interface)
                return
            objects, limit = self._devices, 120
        old = objects.get(path)
        if old:
            identity = (
                ("Address",) if interface == _ADAPTER else ("Address", "Adapter", "AddressType")
            )
            if any(old.props.get(k) != props.get(k) for k in identity):
                self._remove(path, interface)
            else:
                old.props = props
                return
        if len(objects) >= limit:
            # Retain bonded inventory in preference to transient discoveries.
            victim = next(
                (
                    p
                    for p, o in objects.items()
                    if not o.props.get("Paired") and (not self._op or p != self._op.device_path)
                ),
                None,
            )
            if interface != _DEVICE or not props.get("Paired") or victim is None:
                return
            self._remove(victim, interface)
        self._serial += 1
        objects[path] = _Object(uuid.uuid4().hex, self._serial, props)

    def _remove(self, path, interface, *, observed_removal=False):
        objects = self._adapters if interface == _ADAPTER else self._devices
        obj = objects.pop(path, None)
        if not obj:
            return
        op = self._op
        if op and (path == op.device_path or path == op.adapter_path):
            if (
                observed_removal
                and op.kind == "forget"
                and path == op.device_path
                and op.dispatched
            ):
                self._emit("forgotten", op)
                self._retire("observed", cleanup=False)
            else:
                self._retire("invalidated", cleanup=False)
        if interface == _ADAPTER:
            for child in list(self._devices):
                if self._devices[child].props.get("Adapter") == path:
                    self._remove(child, _DEVICE)

    def _on_message(self, msg):
        try:
            return self._handle_message(msg)
        except Exception:
            # Never let dbus-fast's generic handler log an untrusted message/traceback.
            if msg.message_type == self._MessageType.METHOD_CALL:
                return self._Message.new_error(msg, "org.bluez.Error.Rejected", "Rejected")
            return None

    def _handle_message(self, msg):
        if msg.message_type in {self._MessageType.METHOD_RETURN, self._MessageType.ERROR}:
            pending = self._pending.get(msg.reply_serial)
            if pending and msg.sender in {pending[0], _DBUS}:
                if not pending[1].done():
                    pending[1].set_result(msg)
                return True
            return None
        if self._closed.is_set():
            if msg.message_type == self._MessageType.METHOD_CALL and msg.path == _AGENT_PATH:
                return self._Message.new_error(msg, "org.bluez.Error.Rejected", "Rejected")
            return None
        if msg.message_type == self._MessageType.METHOD_CALL and msg.path == _AGENT_PATH:
            if (
                msg.interface == "org.freedesktop.DBus.Introspectable"
                and msg.member == "Introspect"
                and msg.signature == ""
            ):
                return None  # Public interface description only, no values or secrets.
            if msg.interface != _AGENT:
                # Missing interface otherwise bypasses sender checks via service dispatch.
                return self._Message.new_error(msg, "org.bluez.Error.Rejected", "Rejected")
            return self._agent_message(msg)
        if msg.message_type != self._MessageType.SIGNAL:
            return None
        if (
            msg.sender == _DBUS
            and msg.interface == _DBUS
            and msg.member == "NameOwnerChanged"
            and msg.body[0] == _BLUEZ
        ):
            self._invalidate("service_unavailable")
            self._owner = msg.body[2] or None
            if self._owner:
                self._bootstrap_task = asyncio.create_task(self._bootstrap(self._epoch))
            return None
        if msg.sender != self._owner or not self._inventory_ready:
            return None
        if msg.interface == _OM and msg.member == "InterfacesAdded":
            path, interfaces = msg.body
            for interface in (_ADAPTER, _DEVICE):
                if interface in interfaces:
                    self._add(path, interface, interfaces[interface])
            self._publish()
        elif msg.interface == _OM and msg.member == "InterfacesRemoved":
            path, interfaces = msg.body
            for interface in interfaces:
                if interface in {_ADAPTER, _DEVICE}:
                    self._remove(path, interface, observed_removal=True)
            self._publish()
        elif msg.interface == _PROPS and msg.member == "PropertiesChanged":
            interface, raw, invalidated = msg.body
            objects = self._adapters if interface == _ADAPTER else self._devices
            obj = objects.get(msg.path) if interface in {_ADAPTER, _DEVICE} else None
            if obj:
                # Invalidated identity/state is unknown, not a successful false read.
                # BlueZ also invalidates untracked RSSI/TxPower; those are irrelevant.
                relevant = {
                    "Address",
                    "AddressType",
                    "Adapter",
                    "Powered",
                    "Discovering",
                    "Paired",
                    "Connected",
                }
                if relevant.intersection(invalidated):
                    self._remove(msg.path, interface)
                else:
                    props = {
                        key: value for key, value in obj.props.items() if key not in invalidated
                    }
                    props.update(self._props(raw))
                    self._add(msg.path, interface, props)
                    if objects.get(msg.path) is obj:
                        self._observe(msg.path, obj, self._props(raw))
                self._publish()
        return None

    def _observe(self, path, obj, changes):
        if path in self._adapters:
            if (
                "Powered" in changes
                and changes["Powered"] is not True
                and self._op
                and self._op.adapter_path == path
            ):
                self._retire("invalidated")
            return
        for prop, kind in (("Paired", "paired"), ("Connected", "connected")):
            if prop not in changes:
                continue
            if type(changes[prop]) is not bool:
                if self._op and self._op.device_path == path:
                    self._retire("invalidated", cleanup=False)
                continue
            observed = changes[prop] is True
            event_kind = kind if observed else "disconnected" if prop == "Connected" else None
            op = self._op if self._op and self._op.device_path == path else None
            if event_kind:
                self._emit(event_kind, op, device=obj)
            success = (
                op
                and op.dispatched
                and (
                    (op.kind == "pair" and prop == "Paired" and observed)
                    or (op.kind == "connect" and prop == "Connected" and observed)
                    or (op.kind == "disconnect" and prop == "Connected" and not observed)
                )
            )
            if success:
                self._retire("observed", cleanup=False)

    def _command(self, kind, op_id, args):
        op = self._op
        if kind in {"cancel", "stop_discovery"}:
            if op and op.id == op_id and (kind == "cancel" or op.kind == "discover"):
                self._retire(
                    "uncertain"
                    if op.dispatched and op.kind in {"connect", "disconnect", "forget"}
                    else "cancelled"
                )
            return
        if kind == "answer":
            challenge_id, (key, value) = args
            if (
                op
                and op.id == op_id
                and self._current(op)
                and op.challenge
                and op.challenge.id == challenge_id
                and op.answer
                and not op.answer.done()
            ):
                expected = {"pin": "pin", "passkey": "passkey", "confirmation": "confirm"}
                if expected.get(op.challenge.kind) == key:
                    op.answer.set_result(value)
            return
        target, deadline = args
        dummy = _Operation(
            op_id, kind, "", None, target if kind != "discover" else None, 0, self._epoch, deadline
        )
        if op or self._cleanup_task and not self._cleanup_task.done():
            self._emit("finished", dummy, code="busy")
            return
        if not self._registered or not self._owner:
            self._emit("finished", dummy, code="unavailable")
            return
        objects = self._adapters if kind == "discover" else self._devices
        path = next((p for p, obj in objects.items() if obj.id == target), None)
        if path is None:
            self._emit("finished", dummy, code="invalidated")
            return
        obj = objects[path]
        adapter_path = path if kind == "discover" else obj.props["Adapter"]
        adapter = self._adapters.get(adapter_path)
        if not adapter or adapter.props.get("Powered") is not True:
            self._emit("finished", dummy, code="adapter_off")
            return
        duration = {"discover": 30, "pair": 60, "connect": 60, "disconnect": 15, "forget": 15}[kind]
        deadline = min(deadline, self._clock() + duration)
        if deadline <= self._clock():
            self._emit("finished", dummy, code="expired")
            return
        self._op = op = _Operation(
            op_id,
            kind,
            adapter_path,
            None if kind == "discover" else path,
            None if kind == "discover" else obj.id,
            0 if kind == "discover" else obj.epoch,
            self._epoch,
            deadline,
        )
        op.task = asyncio.create_task(self._dispatch(op))

    def _current(self, op):
        return (
            self._op is op
            and self._owner
            and op.epoch == self._epoch
            and self._clock() < op.deadline
            and not self._closed.is_set()
        )

    async def _dispatch(self, op):
        try:
            if not self._current(op):
                return
            member = {
                "discover": "StartDiscovery",
                "pair": "Pair",
                "connect": "Connect",
                "disconnect": "Disconnect",
                "forget": "RemoveDevice",
            }[op.kind]
            adapter_call = op.kind in {"discover", "forget"}
            op.dispatched = True
            # StartDiscovery takes a per-client session; even an uncertain reply needs cleanup.
            op.discovery_owned = op.kind == "discover"
            self._emit("requested", op)
            if not self._current(op):
                return
            await self._call(
                self._owner,
                op.adapter_path if adapter_call else op.device_path,
                _ADAPTER if adapter_call else _DEVICE,
                member,
                "o" if op.kind == "forget" else "",
                [op.device_path] if op.kind == "forget" else [],
                timeout=max(0.001, op.deadline - self._clock()),
            )
            if self._current(op):
                self._emit("accepted", op)
        except TimeoutError:
            if self._op is op:
                self._retire("uncertain")
        except Exception as exc:
            if self._op is op:
                code = getattr(exc, "text", "uncertain")
                self._retire(code if code in {"denied", "failed"} else "uncertain")

    def _retire(self, code, *, cleanup=True):
        op, self._op = self._op, None
        if not op:
            return
        if op.answer and not op.answer.done():
            op.answer.cancel()
        op.challenge = None
        if op.task and op.task is not asyncio.current_task():
            op.task.cancel()
        if self._agent_task and self._agent_task is not asyncio.current_task():
            self._agent_task.cancel()
        self._emit("finished", op, code=code)
        if cleanup and op.dispatched and op.epoch == self._epoch and self._owner:
            if op.discovery_owned or op.kind == "pair":
                if not self._cleanup_task or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._cleanup(op, self._owner))

    async def _cleanup(self, op, owner):
        if op.epoch != self._epoch or owner != self._owner:
            return
        if op.device_path:
            obj = self._devices.get(op.device_path)
            if not obj or obj.id != op.device_id or obj.epoch != op.device_epoch:
                return
        if op.adapter_path not in self._adapters:
            return
        try:
            await self._call(
                owner,
                op.adapter_path if op.discovery_owned else op.device_path,
                _ADAPTER if op.discovery_owned else _DEVICE,
                "StopDiscovery" if op.discovery_owned else "CancelPairing",
            )
        except Exception:
            # Release BlueZ's per-client discovery/agent ownership even if Stop fails.
            # Do not keep a potentially permanent scan on a surviving connection.
            self._invalidate("cleanup_failed")
            self._bus.disconnect()

    def _invalidate(self, reason):
        self._retire("invalidated", cleanup=False)
        for task in (self._bootstrap_task, self._cleanup_task, self._agent_task):
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
        self._epoch += 1
        self._registered = False
        self._inventory_ready = False
        self._owner = None
        self._adapters.clear()
        self._devices.clear()
        self._unavailable(reason)

    def _agent_message(self, msg):
        def reject():
            return self._Message.new_error(msg, "org.bluez.Error.Rejected", "Rejected")

        if msg.sender != self._owner or not self._registered:
            return reject()
        if msg.member in {"Cancel", "Release"} and msg.signature == "":
            self._release_agent(msg.member)
            return self._Message.new_method_return(msg)
        methods = {method.name: method for method in self._service._get_methods(self._service)}
        method = methods.get(msg.member)
        op = self._op
        if (
            not method
            or method.in_signature != msg.signature
            or not msg.body
            or not op
            or op.kind != "pair"
            or not self._current(op)
            or not op.dispatched
            or msg.body[0] != op.device_path
            or self._agent_task
            and not self._agent_task.done()
        ):
            return reject()
        self._agent_task = asyncio.create_task(self._reply_agent(msg, method, op))
        return True

    def _release_agent(self, member):
        self._retire("cancelled")
        if member == "Release":
            self._registered = False
            self._inventory_ready = False
            self._unavailable("agent_unavailable")

    async def _reply_agent(self, msg, method, op):
        try:
            if not self._current(op):
                raise ValueError("stale")
            result = await method.fn(self._service, *msg.body)
            if not self._current(op):
                raise ValueError("stale")
            reply = self._Message.new_method_return(
                msg, method.out_signature, [] if not method.out_signature else [result]
            )
        except (Exception, asyncio.CancelledError):
            reply = self._Message.new_error(msg, "org.bluez.Error.Rejected", "Rejected")
        if not self._closed.is_set():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._bus.send(reply), 2)

    async def _agent(self, member, path=None, *args):
        from dbus_fast import DBusError

        op = self._op
        if not op or op.kind != "pair" or path != op.device_path or not self._current(op):
            raise DBusError("org.bluez.Error.Rejected", "Rejected")
        if member == "AuthorizeService":
            if len(args[0]) != 36 or args[0].lower() not in _HID:
                raise DBusError("org.bluez.Error.Rejected", "Rejected")
            return None
        # Just Works authorization still needs explicit confirmation, not blanket approval.
        kind = {
            "RequestPinCode": "pin",
            "RequestPasskey": "passkey",
            "DisplayPinCode": "display_pin",
            "DisplayPasskey": "display_passkey",
            "RequestConfirmation": "confirmation",
            "RequestAuthorization": "confirmation",
        }[member]
        value, entered = "", 0
        if member == "DisplayPinCode":
            if not isinstance(args[0], str) or not re.fullmatch(r"[\x21-\x7e]{1,16}", args[0]):
                raise DBusError("org.bluez.Error.Rejected", "Rejected")
            value = args[0]
        elif member in {"DisplayPasskey", "RequestConfirmation"}:
            if type(args[0]) is not int or not 0 <= args[0] <= 999999:
                raise DBusError("org.bluez.Error.Rejected", "Rejected")
            value = f"{args[0]:06d}"
            if member == "DisplayPasskey":
                entered = args[1]
                if type(entered) is not int or not 0 <= entered <= 6:
                    raise DBusError("org.bluez.Error.Rejected", "Rejected")
        challenge = Challenge(uuid.uuid4().hex, kind, op.deadline, value, entered)
        op.challenge = challenge
        if kind.startswith("display_"):
            self._emit("challenge", op, challenge=challenge)
            return None
        future = op.answer = asyncio.get_running_loop().create_future()
        self._emit("challenge", op, challenge=challenge)
        try:
            result = await asyncio.wait_for(future, max(0, op.deadline - self._clock()))
            if not self._current(op) or op.challenge is not challenge:
                raise DBusError("org.bluez.Error.Rejected", "Rejected")
            if kind == "confirmation":
                if result is not True:
                    raise DBusError("org.bluez.Error.Rejected", "Rejected")
                return None
            return int(result) if kind == "passkey" else result
        finally:
            if op.challenge is challenge:
                op.challenge, op.answer = None, None

    async def _shutdown(self):
        self._retire("cancelled")
        tasks = [
            t
            for t in (self._bootstrap_task, self._agent_task, self._cleanup_task)
            if t and not t.done()
        ]
        # Cleanup already in flight gets one bounded chance; all other work is retired.
        for task in tasks:
            if task is not self._cleanup_task:
                task.cancel()
        if tasks:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 2.1)
        if self._bus:
            if self._registered and self._owner:
                with contextlib.suppress(Exception):
                    await self._call(
                        self._owner,
                        "/org/bluez",
                        "org.bluez.AgentManager1",
                        "UnregisterAgent",
                        "o",
                        [_AGENT_PATH],
                    )
            if self._exported:
                with contextlib.suppress(Exception):
                    self._bus.unexport(_AGENT_PATH, self._service)
            with contextlib.suppress(Exception):
                await asyncio.gather(
                    *(self._dbus("RemoveMatch", "s", [rule]) for rule in self._matches),
                    return_exceptions=True,
                )
            with contextlib.suppress(Exception):
                self._bus.remove_message_handler(self._on_message)
            with contextlib.suppress(Exception):
                self._bus.disconnect()
        while not self._queue.empty():
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
        self._adapters.clear()
        self._devices.clear()
        self._listener = None
