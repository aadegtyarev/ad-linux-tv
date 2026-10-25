"""One authenticated WebSocket for live phone remote traffic."""

import base64
import binascii
import hashlib
import json
import os
import socket
import struct

from .remote_rpc import RemoteDispatcher

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 4096


class RemoteSocket:
    def __init__(self, handler, dispatcher):
        self.handler = handler
        self.dispatcher = dispatcher

    def _read(self, count):
        data = self.handler.rfile.read(count)
        if len(data) != count:
            raise ConnectionError("socket closed")
        return data

    def _send(self, opcode, payload):
        size = len(payload)
        if size < 126:
            length = bytes([size])
        elif size < 65536:
            length = b"\x7e" + struct.pack("!H", size)
        else:
            length = b"\x7f" + struct.pack("!Q", size)
        self.handler.wfile.write(bytes([0x80 | opcode]) + length + payload)

    def _frame(self):
        self.handler.rfile.reset_deadline()
        first, second = self._read(2)
        if first & 0x70 or not first & 0x80 or not second & 0x80:
            raise ValueError("invalid frame")
        opcode = first & 0x0F
        size = second & 0x7F
        if size == 126:
            size = struct.unpack("!H", self._read(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self._read(8))[0]
        if size > MAX_MESSAGE or opcode not in (1, 8, 9, 10):
            raise ValueError("unsupported frame")
        if opcode >= 8 and size > 125:
            raise ValueError("invalid control frame")
        mask = self._read(4)
        payload = self._read(size)
        return opcode, bytes(value ^ mask[index % 4] for index, value in enumerate(payload))

    def run(self):
        self.handler.rfile.timeout = 30.0
        while True:
            try:
                opcode, payload = self._frame()
                if opcode == 8:
                    self._send(8, b"")
                    return
                if opcode == 9:
                    self._send(10, payload)
                    continue
                if opcode == 10:
                    continue
                item = json.loads(payload.decode("utf-8"))
                if not isinstance(item, dict) or set(item) != {"id", "method", "path", "body"}:
                    raise ValueError("invalid request")
                request_id = item["id"]
                if type(request_id) is not int or not 0 <= request_id <= 2**53 - 1:
                    raise ValueError("invalid request id")
                if not self.handler.authorized():
                    self._send(8, struct.pack("!H", 1008))
                    return
                status, body = self.dispatcher.dispatch(item["method"], item["path"], item["body"])
                reply = json.dumps({"id": request_id, "status": status, "body": body}).encode()
                self._send(1, reply)
            except (ConnectionError, OSError, socket.timeout):
                return
            except (ValueError, TypeError, UnicodeError):
                try:
                    self._send(8, struct.pack("!H", 1002))
                except OSError:
                    pass
                return


def serve_remote_socket(
    handler, config, queue, sessions, failures, display_timer, static, settings=None
):
    """Authenticate the upgrade using the same cookie, Origin and CSRF as POST."""
    protocol = handler.headers.get("Sec-WebSocket-Protocol", "")
    token = handler.authorized()
    csrf = protocol.removeprefix("csrf.") if protocol.startswith("csrf.") else ""
    key = handler.headers.get("Sec-WebSocket-Key", "")
    try:
        valid_key = len(base64.b64decode(key, validate=True)) == 16
    except (ValueError, binascii.Error):
        valid_key = False
    if (
        os.environ.get("AD_LINUX_TV_KIOSK") != "1"
        or not handler.private()
        or not handler.valid_origin()
        or not token
        or not sessions.csrf_valid(token, csrf)
        or handler.headers.get("Upgrade", "").lower() != "websocket"
        or "upgrade"
        not in {part.strip().lower() for part in handler.headers.get("Connection", "").split(",")}
        or handler.headers.get("Sec-WebSocket-Version") != "13"
        or not valid_key
    ):
        handler.close_connection = True
        return handler.send(403, "{}")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    handler.send_response(101)
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.send_header("Sec-WebSocket-Protocol", protocol)
    handler.end_headers()
    handler.close_connection = True
    dispatcher = RemoteDispatcher(
        handler, config, queue, sessions, failures, display_timer, static, csrf, settings
    )
    RemoteSocket(handler, dispatcher).run()
