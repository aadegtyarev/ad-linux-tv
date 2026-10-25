"""Absolute-deadline request reader for untrusted HTTP connections."""

import select
import socket
import time


class DeadlineReader:
    def __init__(self, connection, timeout):
        self.connection = connection
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        self.buffer = bytearray()
        self.eof = False

    def reset_deadline(self):
        self.deadline = time.monotonic() + self.timeout

    def _fill(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or not select.select([self.connection], [], [], remaining)[0]:
            raise socket.timeout("request read deadline exceeded")
        data = self.connection.recv(4096)
        if data:
            self.buffer.extend(data)
        else:
            self.eof = True

    def readline(self, size=-1):
        while True:
            end = self.buffer.find(b"\n") + 1
            if end or (size >= 0 and len(self.buffer) >= size):
                count = end if end and (size < 0 or end <= size) else size
                value = bytes(self.buffer[:count])
                del self.buffer[:count]
                return value
            if self.eof:
                value = bytes(self.buffer)
                self.buffer.clear()
                return value
            self._fill()

    def read(self, size=-1):
        if size < 0:
            while not self.eof:
                self._fill()
            size = len(self.buffer)
        while len(self.buffer) < size and not self.eof:
            self._fill()
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value

    def close(self):
        self.buffer.clear()
