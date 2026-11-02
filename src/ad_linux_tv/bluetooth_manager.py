"""Rootless Bluetooth management, not input capture or an action dispatcher.

The injected transport implements the frozen BluezTransport API/DTO attributes;
no transport module, system bus, thread or settings IO is used at import/init.
Integration constructs Principal AFTER authenticating the real connection (never
from JSON). Only owner POST replies contain transient pairing/forget secrets.

Input attachment/learning is intentionally unavailable pending reviewed physical
identity/topology proof. Existing saved maps may be reset/unmapped, never executed.
get_config returns the strict detached Bluetooth section; save_config targets
SettingsManager.set_bluetooth. This coordinator is the sole live section writer:
latest-section checks detect intervening edits, but are NOT cross-process CAS.
Other settings remain the atomic writer's responsibility, not a cached YAML copy.
"""

import math
import queue
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field

from .bluetooth_schema import ACTIONS, BUTTON_CODES, validate_bluetooth

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_LEASE = re.compile(r"[0-9a-f]{32}\Z")
_ADDRESS = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")
_ERRORS = frozenset(
    "busy stale unavailable adapter_off helper_unavailable unsupported invalidated "
    "expired cancelled uncertain denied failed save_failed rejected".split()
)
_FIELDS = {
    "acquire": (),
    "poll": ("lease",),
    "release": ("lease",),
    "discover": ("lease",),
    "cancel": ("lease", "operation_id"),
    "pair": ("lease", "device_id"),
    "connect": ("lease", "device_id"),
    "disconnect": ("lease", "device_id"),
    "select_remote": ("lease", "device_id"),
    "answer": ("lease", "operation_id", "challenge_id", "answer"),
    "forget_prepare": ("lease", "device_id"),
    "forget_confirm": ("lease", "operation_id", "confirmation_id"),
    "learn": ("lease", "action"),
    "bind": ("lease", "operation_id", "observation_id"),
    "test": ("lease", "operation_id", "observation_id"),
    "unmap": ("lease", "key", "revision"),
    "reset": ("lease", "revision"),
}
_DURATIONS = {"discover": 30, "pair": 60, "connect": 60, "disconnect": 15, "forget": 15}
# Only these documented admission rejections use a placeholder device epoch.
_PRE_DISPATCH_REJECTIONS = frozenset("busy unavailable invalidated adapter_off expired".split())
_OBSERVATIONS = {
    "pair": "paired",
    "connect": "connected",
    "disconnect": "disconnected",
    "forget": "forgotten",
}


@dataclass(frozen=True)
class Principal:
    """Internal authenticated subject AND connection, never a client DTO."""

    kind: str
    owner: str = field(repr=False)
    connection: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if (
            self.kind not in ("tv", "phone")
            or not isinstance(self.owner, str)
            or not 1 <= len(self.owner) <= 256
            or (
                self.connection is not None
                and (not isinstance(self.connection, str) or not 1 <= len(self.connection) <= 256)
            )
        ):
            raise ValueError("invalid principal")


@dataclass
class _Operation:
    id: str
    kind: str
    deadline: float
    controller_epoch: int
    adapter_id: str
    adapter_address: str
    revision: int
    device_id: str | None = None
    device_epoch: int = 0
    identity: dict | None = field(default=None, repr=False)
    phase: str = "queued"
    error: str = ""
    dispatched: bool = False
    admitted: bool = False
    observed: bool = False
    retired: bool = False
    transport_result: str | None = None
    pending_observation: str | None = None
    pending_generation: int = 0
    challenge: dict | None = field(default=None, repr=False)
    confirmation: str | None = field(default=None, repr=False)
    retired_challenges: set = field(default_factory=set, repr=False)

    @property
    def active(self):
        return self.phase not in ("finished", "observed")


def _identifier(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _address(value):
    return (
        isinstance(value, str)
        and _ADDRESS.fullmatch(value) is not None
        and value not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
    )


def _name(value):
    if not isinstance(value, str):
        return ""
    result = ""
    for char in value[:160]:
        if char.isprintable() and not unicodedata.category(char).startswith("C"):
            candidate = result + char
            if len(candidate) > 80 or len(candidate.encode("utf-8")) > 160:
                break
            result = candidate
    return result


def _answer(value):
    if not isinstance(value, dict) or len(value) != 1:
        return False
    if set(value) == {"confirm"}:
        return type(value["confirm"]) is bool
    if set(value) == {"pin"}:
        pin = value["pin"]
        return isinstance(pin, str) and 1 <= len(pin) <= 16 and all("!" <= c <= "~" for c in pin)
    if set(value) == {"passkey"}:
        pin = value["passkey"]
        return isinstance(pin, str) and len(pin) == 6 and all("0" <= c <= "9" for c in pin)
    return False


def _valid_request(dto):
    if not isinstance(dto, dict) or not isinstance(dto.get("op"), str):
        return False
    op = dto["op"]
    if op not in _FIELDS or set(dto) != {"op", *_FIELDS[op]}:
        return False
    for key, value in dto.items():
        if key == "lease" and not (isinstance(value, str) and _LEASE.fullmatch(value)):
            return False
        if key.endswith("_id") and not _identifier(value):
            return False
        if key == "action" and (not isinstance(value, str) or value not in ACTIONS):
            return False
        if key == "key" and (not isinstance(value, str) or value not in BUTTON_CODES):
            return False
        if key == "revision" and (type(value) is not int or not 0 <= value <= 2**53 - 1):
            return False
        if key == "answer" and not _answer(value):
            return False
    return True


class BluetoothManager:
    """One owner lease/operation, bounded mailbox and one expiry/cleanup worker.

    Transport callbacks only attempt put_nowait and set Events. Mailbox overflow
    poisons the session; the worker retires ownership and closes transport off the
    callback thread. No reconnect/replay, and no command bool implies observation.
    tick() is a deterministic injected-clock test seam; the worker also calls it
    every <=50ms, independently of HTTP and event traffic. close() joins <=9s
    (transport contract bounds its own close to8s), raising a fixed error on failure.
    """

    def __init__(self, *, transport, get_config, save_config, enabled=False, clock=time.monotonic):
        self._transport = transport
        self._get_config = get_config
        self._save_config = save_config
        self._enabled = enabled is True
        self._clock = clock
        self._lock = threading.RLock()
        self._events = queue.Queue(maxsize=64)
        self._wake = threading.Event()
        self._poison = threading.Event()
        self._thread = None
        self._started = False
        self._closed = False
        self._failed = False
        self._cleanup_failed = False
        self._transport_closed = False
        self._owner = None
        self._lease = None
        self._lease_deadline = 0
        self._operation = None
        self._config = None
        self._config_ok = False
        self._revision = 0
        self._inventory = None
        self._inventory_generation = 0

    def start(self):
        with self._lock:
            if self._started or self._closed or not self._enabled:
                return
            self._started = True
            try:
                self._transport.start(self._on_event)
            except Exception:
                self._poison.set()
            self._thread = threading.Thread(target=self._run, name="bluetooth-manager", daemon=True)
            self._thread.start()

    def _on_event(self, event):
        if self._closed or self._poison.is_set():
            return
        try:
            self._events.put_nowait(event)
        except queue.Full:
            self._poison.set()
        self._wake.set()

    def _run(self):
        try:
            while True:
                self._wake.clear()
                self.tick()
                with self._lock:
                    if self._closed or self._failed:
                        break
                self._wake.wait(0.05)
        except Exception:
            with self._lock:
                self._fail_closed()
        finally:
            # Never run close/join, settings IO, or user hooks on transport's callback.
            try:
                self._transport.close()
            except Exception:
                with self._lock:
                    self._cleanup_failed = True
                    self._failed = True
            finally:
                with self._lock:
                    self._transport_closed = True
                    while True:
                        try:
                            self._events.get_nowait()
                        except queue.Empty:
                            break

    def close(self):
        with self._lock:
            self._closed = True
            self._retire_owner("cancelled")
            thread = self._thread
        self._wake.set()
        if thread is not None:
            thread.join(9)
            if thread.is_alive():
                raise RuntimeError("Bluetooth shutdown failed")
        if self._cleanup_failed:
            raise RuntimeError("Bluetooth shutdown failed")

    def retire(self, principal):
        """Called by integration on session/socket retirement; no runtime input exists here."""
        with self._lock:
            if isinstance(principal, Principal) and principal == self._owner:
                self._retire_owner("cancelled")
        self._wake.set()

    def retire_phones(self):
        """Internal auth-retirement hook, called OUTSIDE SettingsManager's lock.

        PIN/session invalidation must retire a phone owner immediately, not wait
        for its next socket message or lease expiry. TV ownership is unaffected.
        """
        with self._lock:
            if self._owner is not None and self._owner.kind == "phone":
                self._retire_owner("cancelled")
        self._wake.set()

    def _history_ok(self):
        if self._poison.is_set():
            self._fail_closed()
            self._wake.set()
        return not self._failed

    def _command(self, method, *args):
        if not self._history_ok():
            return False
        if method in _DURATIONS:
            # Admission does not prove dispatch, but from here dispatch cannot be
            # excluded merely because its notification is still in the mailbox.
            self._operation.admitted = True
        try:
            queued = getattr(self._transport, method)(*args)
        except Exception:
            queued = False
        if queued is not True:
            # A failed cancellation may leave owned discovery or agent callbacks alive.
            self._fail_closed()
            self._wake.set()
            return False
        return self._history_ok()

    def _fail_closed(self):
        self._failed = True
        self._poison.set()
        self._owner = self._lease = None
        self._lease_deadline = 0
        if self._operation:
            self._finish("uncertain", retire=True)

    def _finish(self, error="", *, observed=False, retire=False):
        operation = self._operation
        operation.observed |= observed
        operation.phase = "observed" if operation.observed else "finished"
        operation.error = error if error in _ERRORS else ""
        operation.challenge = None
        operation.confirmation = None
        operation.retired |= retire
        if observed or retire:
            operation.pending_observation = None

    def _cancel(self, reason):
        operation = self._operation
        if operation is None or not (operation.active or operation.pending_observation):
            return
        if operation.admitted and operation.transport_result is None:
            if not self._command("cancel", operation.id):
                return
        # All admitted command types (including pair/discovery) can have an
        # unconfirmed write. Local retirement cannot certify no physical effect.
        self._finish("uncertain" if operation.admitted else reason, retire=True)

    def _retire_owner(self, reason):
        self._cancel(reason)
        self._owner = self._lease = None
        self._lease_deadline = 0
        if self._operation:
            operation = self._operation
            if operation.admitted and operation.transport_result is None:
                operation.error = "uncertain"
            operation.retired = True
            operation.pending_observation = None
            operation.challenge = None
            operation.confirmation = None

    def _load_config(self):
        try:
            latest = validate_bluetooth(self._get_config())
            if not self._history_ok():
                return
        except Exception:
            self._config_ok = False
            self._cancel("invalidated")
            return
        self._config_ok = True
        if self._config is None:
            self._config = latest
        elif self._config != latest:
            self._config = latest
            self._revision += 1
            self._cancel("invalidated")

    def _refresh(self):
        try:
            inventory = self._transport.snapshot()
            if not self._history_ok():
                return
            if (
                type(inventory.available) is not bool
                or type(inventory.controller_epoch) is not int
                or inventory.controller_epoch < 0
                or len(inventory.adapters) > 8
                or len(inventory.devices) > 128
            ):
                raise ValueError
            self._inventory = inventory
            self._inventory_generation += 1
        except Exception:
            self._inventory = None
            self._fail_closed()

    def _adapters(self):
        if self._inventory is None:
            return []
        return sorted(
            (
                adapter
                for adapter in self._inventory.adapters
                if _identifier(adapter.id)
                and _address(adapter.address)
                and type(adapter.powered) is bool
                and type(adapter.discovering) is bool
            ),
            key=lambda adapter: (adapter.address, adapter.id),
        )

    def _adapter(self):
        adapters = self._adapters()
        operation = self._operation
        if operation and operation.active:
            return next(
                (
                    a
                    for a in adapters
                    if a.id == operation.adapter_id and a.address == operation.adapter_address
                ),
                None,
            )
        remote = self._config["remote"] if self._config else None
        if remote:
            return next((a for a in adapters if a.address == remote["identity"]["adapter"]), None)
        return next((a for a in adapters if a.powered), adapters[0] if adapters else None)

    def _devices(self):
        if self._inventory is None:
            return []
        adapters = {adapter.id for adapter in self._adapters()}
        return [
            device
            for device in self._inventory.devices
            if _identifier(device.id)
            and device.adapter_id in adapters
            and _address(device.address)
            and device.address_type in ("", "public", "random")
            and type(device.paired) is bool
            and type(device.connected) is bool
            and type(device.device_epoch) is int
            and device.device_epoch >= 0
        ]

    def _identity(self, device):
        adapter = next((a for a in self._adapters() if a.id == device.adapter_id), None)
        if adapter is None:
            return None
        return {
            "adapter": adapter.address,
            "address": device.address,
            "address_type": device.address_type,
        }

    def _device(self, device_id):
        return next((d for d in self._devices() if d.id == device_id), None)

    def _current_target(self, operation, *, allow_missing=False):
        inventory = self._inventory
        if (
            inventory is None
            or not inventory.available
            or inventory.controller_epoch != operation.controller_epoch
        ):
            return False
        adapter = next((a for a in self._adapters() if a.id == operation.adapter_id), None)
        if adapter is None or adapter.address != operation.adapter_address or not adapter.powered:
            return False
        if operation.device_id is None:
            return True
        device = self._device(operation.device_id)
        if device is None:
            return allow_missing
        return (
            device.device_epoch == operation.device_epoch
            and self._identity(device) == operation.identity
            and device.adapter_id == operation.adapter_id
        )

    def _dispatch_fence(self, operation):
        # Recheck immediately before effects, not just at the beginning of HTTP
        # processing. The transport independently fences its queued dispatch.
        self._load_config()
        self._refresh()
        if not self._history_ok():
            return 503, "unavailable"
        now = self._clock()
        if self._owner is None or now >= self._lease_deadline:
            self._retire_owner("expired")
            return (503, "unavailable") if self._failed else (409, "expired")
        if not operation.active:
            return 409, "stale"
        if now >= operation.deadline or (
            operation.challenge and now >= operation.challenge["deadline"]
        ):
            self._cancel("expired")
            return (503, "unavailable") if self._failed else (409, "expired")
        if not self._current_target(operation):
            self._cancel("invalidated")
            return (503, "unavailable") if self._failed else (409, "invalidated")
        return None

    def _expire(self, now):
        if self._owner is not None and now >= self._lease_deadline:
            self._retire_owner("expired")
        operation = self._operation
        if (
            operation
            and (operation.active or operation.pending_observation)
            and now >= operation.deadline
        ):
            self._cancel("expired")

    def tick(self):
        """Drain at most64 events and service original deadlines even under a flood."""
        with self._lock:
            if not self._started or self._closed or self._failed:
                return
            if not self._history_ok():
                return
            self._load_config()
            if not self._history_ok():
                return
            self._refresh()
            if not self._history_ok():
                return
            now = self._clock()
            self._expire(now)
            for _ in range(64):
                if not self._history_ok():
                    return
                try:
                    event = self._events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._event(event, now)
                except Exception:
                    self._fail_closed()
                    break
            if not self._history_ok():
                return
            now = self._clock()
            self._expire(now)
            self._resolve_observation(now)
            operation = self._operation
            if operation and (operation.active or operation.pending_observation):
                allow_missing = operation.kind == "forget" and operation.phase != "confirm"
                if not self._current_target(operation, allow_missing=allow_missing):
                    self._cancel("invalidated")
                elif operation.challenge and now >= operation.challenge["deadline"]:
                    self._cancel("expired")

    def _event(self, event, now):
        operation = self._operation
        if (
            not self._history_ok()
            or operation is None
            or not operation.admitted
            or event.operation_id != operation.id
            or event.controller_epoch != operation.controller_epoch
            or event.device_id != operation.device_id
        ):
            return
        rejection = (
            event.kind == "finished"
            and event.code in _PRE_DISPATCH_REJECTIONS
            and event.device_epoch == 0
            and not operation.dispatched
            and not operation.observed
            and operation.pending_observation is None
            and operation.transport_result is None
        )
        if event.device_epoch != operation.device_epoch and not rejection:
            return
        # Retain only CURRENT outcome correlation, even after ownership/target
        # retirement. Terminal uncertainty needs no live target and authorizes no
        # new command, secret delivery or settings effect.
        if event.kind == "finished":
            code = event.code if event.code in _ERRORS or event.code == "observed" else "uncertain"
            if operation.transport_result == "uncertain":
                return
            operation.transport_result = code
            if code == "uncertain":
                self._finish(code)
            elif operation.retired:
                return
            elif code != "observed":
                self._finish(code, retire=operation.pending_observation is None)
            # Successful termination alone is NOT physical proof. A correlated
            # observation may still be waiting for a later snapshot publication.
            return
        if event.kind in ("requested", "accepted"):
            operation.dispatched = True
            if operation.active and not operation.retired:
                if event.kind == "requested" and operation.phase == "queued":
                    operation.phase = "requested"
                elif event.kind == "accepted" and operation.phase in ("queued", "requested"):
                    operation.phase = "accepted"
            return
        if (
            not operation.active
            or operation.retired
            or self._owner is None
            or now >= operation.deadline
        ):
            return
        allow_missing = operation.kind == "forget"
        if not self._current_target(operation, allow_missing=allow_missing):
            return
        if event.kind == "challenge" and operation.kind == "pair":
            self._challenge(event.challenge, operation, now)
        elif event.kind == _OBSERVATIONS.get(operation.kind):
            # One fixed-kind observation, not a history. Always require a sample
            # taken AFTER consumption; snapshot() may have returned an older DTO
            # while publishing this very callback. Duplicates cannot delay it.
            if operation.pending_observation is None:
                operation.pending_observation = event.kind
                operation.pending_generation = self._inventory_generation

    def _resolve_observation(self, now):
        operation = self._operation
        if (
            not self._history_ok()
            or operation is None
            or operation.pending_observation is None
            or operation.retired
            or self._owner is None
            or now >= self._lease_deadline
            or now >= operation.deadline
            or self._inventory_generation <= operation.pending_generation
            or not self._current_target(operation, allow_missing=operation.kind == "forget")
        ):
            return
        device = self._device(operation.device_id)
        if operation.kind == "forget":
            proven = device is None
        else:
            proven = (
                device is not None
                and {
                    "pair": device.paired,
                    "connect": device.connected,
                    "disconnect": not device.connected,
                }[operation.kind]
            )
        if not proven:
            return
        error = operation.transport_result if operation.transport_result in _ERRORS else ""
        self._finish(error, observed=True)
        if operation.kind == "forget":
            # Both the exact removal EVENT and later matching snapshot are
            # necessary. Retirement clears the pending proof; absence alone is
            # never enough, and a later uncertain reply cannot undo physical truth.
            remote = self._config["remote"] if self._config_ok else None
            if remote and remote["identity"] == operation.identity:
                if (
                    self._save({"remote": None}, operation.revision) is not None
                    and not self._failed
                ):
                    operation.error = "save_failed"

    def _challenge(self, challenge, operation, now):
        if challenge is None or not _identifier(challenge.id):
            self._cancel("invalidated")
            return
        if challenge.id in operation.retired_challenges:
            return
        kind = challenge.kind
        deadline = challenge.deadline
        value = challenge.value
        entered = challenge.entered
        if (
            kind not in ("pin", "passkey", "confirmation", "display_pin", "display_passkey")
            or type(deadline) not in (int, float)
            or not math.isfinite(deadline)
            or deadline <= now
            or type(entered) is not int
            or not 0 <= entered <= 6
            or not isinstance(value, str)
            or (kind == "display_pin" and not _answer({"pin": value}))
            or (kind in ("confirmation", "display_passkey") and not _answer({"passkey": value}))
            or (kind in ("pin", "passkey") and value != "")
        ):
            self._cancel("invalidated")
            return
        # A display update can change 'entered', never extend the same challenge.
        old = operation.challenge
        if old and (
            old["id"] != challenge.id or old["kind"] != kind or old.get("value", "") != value
        ):
            self._cancel("invalidated")
            return
        operation.dispatched = True
        operation.phase = "waiting"
        operation.challenge = {
            "id": challenge.id,
            "kind": kind,
            "deadline": min(deadline, operation.deadline, old["deadline"] if old else deadline),
        }
        if kind in ("display_pin", "display_passkey", "confirmation"):
            operation.challenge["value"] = value
        if kind == "display_passkey":
            operation.challenge["entered"] = entered

    def _save(self, section, revision):
        if not self._history_ok():
            return "unavailable"
        self._load_config()
        if not self._history_ok():
            return "unavailable"
        if not self._config_ok:
            return "save_failed"
        if revision != self._revision:
            return "stale"
        if self._owner is None or self._clock() >= self._lease_deadline:
            self._retire_owner("expired")
            return "unavailable" if self._failed else "expired"
        candidate = validate_bluetooth(section)
        if not self._history_ok():
            return "unavailable"
        try:
            self._save_config(candidate)
        except Exception:
            return "save_failed"
        self._load_config()
        return None if self._config_ok and self._config == section else "save_failed"

    def _reason(self):
        if not self._enabled or not self._started or self._closed or self._failed:
            return "unavailable"
        if not self._config_ok:
            return "save_failed"
        if self._inventory is None or not self._inventory.available:
            return "unavailable"
        adapter = self._adapter()
        if adapter is None:
            return "unavailable"
        if not adapter.powered:
            return "adapter_off"
        return ""

    def _state(self):
        self._history_ok()
        adapter = self._adapter()
        remote = self._config["remote"] if self._config else None
        devices = [d for d in self._devices() if adapter and d.adapter_id == adapter.id]
        selected = next(
            (d for d in devices if remote and self._identity(d) == remote["identity"]), None
        )
        devices.sort(key=lambda d: (d is not selected, not d.paired, d.id))
        # Opaque handles are unique; identity duplicates are never guessed as a selection.
        if selected and sum(self._identity(d) == remote["identity"] for d in devices) != 1:
            selected = None
        unique = {}
        for device in devices:
            unique.setdefault(device.id, device)
        operation = self._operation
        reason = self._reason()
        state = {
            "available": reason in ("", "adapter_off"),
            "reason": reason,
            "revision": self._revision,
            "adapter": (
                {"id": adapter.id, "powered": adapter.powered, "discovering": adapter.discovering}
                if adapter
                else None
            ),
            "devices": [
                {
                    "id": d.id,
                    "name": _name(d.name),
                    "paired": d.paired,
                    "connected": d.connected,
                    "selected": d is selected,
                    "input_available": False,
                }
                for d in list(unique.values())[:64]
            ],
            "remote": (
                {
                    "device_id": selected.id if selected else None,
                    "connected": selected.connected if selected else False,
                    "bindings": dict(remote["bindings"]),
                    "input_available": False,
                    "reason": "helper_unavailable",
                }
                if remote
                else None
            ),
            "operation": (
                {
                    "id": operation.id,
                    "kind": operation.kind,
                    "phase": operation.phase,
                    "device_id": operation.device_id,
                    "remaining_ms": max(0, int((operation.deadline - self._clock()) * 1000))
                    if operation.active
                    else 0,
                    "error": operation.error,
                }
                if operation
                else None
            ),
        }
        return state

    def snapshot(self, principal):
        """Private authenticated inventory, but NEVER lease/challenge/confirmation."""
        if not isinstance(principal, Principal):
            raise ValueError("invalid principal")
        with self._lock:
            self.tick()
            return self._state()

    def _reply(self, status=200, error=None, *, private=False):
        if not self._history_ok():
            status, error, private = 503, "unavailable", False
        envelope = {"state": self._state()}
        if error:
            envelope["error"] = error
        operation = self._operation
        if (
            private
            and self._history_ok()
            and self._owner is not None
            and operation
            and operation.active
        ):
            if operation.challenge:
                challenge = dict(operation.challenge)
                deadline = challenge.pop("deadline")
                challenge["remaining_ms"] = max(0, int((deadline - self._clock()) * 1000))
                envelope["challenge"] = challenge
            if operation.confirmation:
                envelope["confirmation_id"] = operation.confirmation
        if not self._history_ok():
            return 503, {"state": self._state(), "error": "unavailable"}
        return status, envelope

    def request(self, principal, dto):
        with self._lock:
            self.tick()
            if not isinstance(principal, Principal):
                return self._reply(403, "denied")
            if not _valid_request(dto):
                return self._reply(400, "failed")
            op = dto["op"]
            if not self._enabled or not self._started or self._closed or self._failed:
                return self._reply(503, "unavailable")
            if op == "acquire":
                if self._owner is not None:
                    return self._reply(409, "busy")
                self._owner = principal
                self._lease = uuid.uuid4().hex
                self._lease_deadline = self._clock() + 15
                status, result = self._reply()
                if status == 200 and self._history_ok():
                    result["lease"] = self._lease
                    return status, result
                return self._reply(503, "unavailable")
            if self._owner is None or dto["lease"] != self._lease:
                return self._reply(409, "stale")
            if principal != self._owner:
                return self._reply(403, "denied")
            if op == "poll":
                self._lease_deadline = self._clock() + 15
                return self._reply(private=True)
            if op == "release":
                self._retire_owner("cancelled")
                return self._reply(
                    503 if self._failed else 200, "unavailable" if self._failed else None
                )
            if op in ("cancel", "answer", "forget_confirm", "bind", "test"):
                operation = self._operation
                if operation is None or not operation.active or dto["operation_id"] != operation.id:
                    return self._reply(409, "stale")
                if op in ("bind", "test"):
                    # No observations exist until a reviewed input adapter is integrated.
                    return self._reply(409, "stale")
                if op == "cancel":
                    self._cancel("cancelled")
                    return self._reply(
                        503 if self._failed else 200, "unavailable" if self._failed else None
                    )
                failure = self._dispatch_fence(operation)
                if failure:
                    return self._reply(*failure)
                if op == "answer":
                    return self._respond(dto, operation)
                if (
                    operation.kind != "forget"
                    or operation.phase != "confirm"
                    or dto["confirmation_id"] != operation.confirmation
                ):
                    return self._reply(409, "stale")
                operation.confirmation = None  # Consume BEFORE irreversible dispatch.
                operation.deadline = self._clock() + 15
                operation.phase = "queued"
                if not self._command(
                    "forget", operation.id, operation.device_id, operation.deadline
                ):
                    return self._reply(503, "unavailable")
                return self._reply(202, private=True)
            if self._operation and self._operation.active:
                return self._reply(409, "busy")
            if op in ("unmap", "reset"):
                return self._edit_maps(dto)
            if op == "learn":
                if not self._config_ok or not self._config["remote"]:
                    return self._reply(409, "stale")
                remote = self._config["remote"]
                if not any(
                    self._identity(d) == remote["identity"] and d.paired and d.connected
                    for d in self._devices()
                ):
                    return self._reply(409, "stale")
                return self._reply(503, "helper_unavailable")
            reason = self._reason()
            if reason:
                return self._reply(503, reason)
            adapter = self._adapter()
            device = self._device(dto.get("device_id")) if op != "discover" else None
            if op != "discover" and (device is None or device.adapter_id != adapter.id):
                return self._reply(409, "stale")
            if op == "select_remote":
                if not device.paired or not device.connected:
                    return self._reply(409, "stale")
                return self._reply(503, "helper_unavailable")
            kind = "forget" if op == "forget_prepare" else op
            self._operation = _Operation(
                id=uuid.uuid4().hex,
                kind=kind,
                deadline=self._clock() + (20 if op == "forget_prepare" else _DURATIONS[kind]),
                controller_epoch=self._inventory.controller_epoch,
                adapter_id=adapter.id,
                adapter_address=adapter.address,
                revision=self._revision,
                device_id=device.id if device else None,
                device_epoch=device.device_epoch if device else 0,
                identity=self._identity(device) if device else None,
            )
            operation = self._operation
            if op == "forget_prepare":
                operation.phase = "confirm"
                operation.confirmation = uuid.uuid4().hex
                return self._reply(private=True)
            target = adapter.id if op == "discover" else device.id
            failure = self._dispatch_fence(operation)
            if failure:
                return self._reply(*failure)
            if not self._command(op, operation.id, target, operation.deadline):
                return self._reply(503, "unavailable")
            return self._reply(202, private=True)

    def _respond(self, dto, operation):
        challenge = operation.challenge
        if challenge is None or dto["challenge_id"] != challenge["id"]:
            return self._reply(409, "stale")
        key = {"pin": "pin", "passkey": "passkey", "confirmation": "confirm"}.get(challenge["kind"])
        if key is None or set(dto["answer"]) != {key}:
            return self._reply(400, "failed")
        if len(operation.retired_challenges) >= 8:
            self._cancel("invalidated")
            return (
                self._reply(503, "unavailable") if self._failed else self._reply(409, "invalidated")
            )
        operation.retired_challenges.add(challenge["id"])
        operation.challenge = None  # At most once, even if queueing fails.
        operation.phase = "waiting"
        if not self._command("answer", operation.id, dto["challenge_id"], dict(dto["answer"])):
            return self._reply(503, "unavailable")
        return self._reply(202, private=True)

    def _edit_maps(self, dto):
        self._load_config()
        if not self._config_ok:
            return self._reply(503, "save_failed")
        if dto["revision"] != self._revision or not self._config["remote"]:
            return self._reply(409, "stale")
        section = validate_bluetooth(self._config)
        bindings = section["remote"]["bindings"]
        if dto["op"] == "reset":
            bindings.clear()
        else:
            bindings.pop(dto["key"], None)
        if section != self._config:
            error = self._save(section, dto["revision"])
            if error:
                return self._reply(409 if error in ("stale", "expired") else 503, error)
        return self._reply()
