"""Start configured LAN and loopback-only bridge listeners."""

import ipaddress
import os
import socket
import time
from http.server import ThreadingHTTPServer
from threading import Semaphore, Thread

from . import audio
from .server import make_handler


class AddressServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, worker_slots):
        self.worker_slots = worker_slots
        self.read_timeout = 5.0
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.worker_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def make_server(address, port, handler, worker_slots=None):
    server_class = type(
        "Listener",
        (AddressServer,),
        {"address_family": socket.AF_INET6 if ":" in address else socket.AF_INET},
    )
    return server_class((address, port), handler, worker_slots or Semaphore(32))


def serve(config, config_path=None):
    address = ipaddress.ip_address(config["bind"])
    handler = make_handler(config, config_path)
    worker_slots = Semaphore(32)
    servers = [make_server(str(address), config["port"], handler, worker_slots)]
    if str(address) != "127.0.0.1" and not (address.version == 4 and address.is_unspecified):
        servers.append(make_server("127.0.0.1", config["port"], handler, worker_slots))
    for listener in servers[1:]:
        Thread(target=listener.serve_forever, daemon=True).start()
    if os.environ.get("AD_LINUX_TV_KIOSK") == "1":

        def keep_browser_gain_neutral():
            while True:
                try:
                    audio.normalize_browser_volume(config.get("audio", {}).get("browser", 100))
                    audio.normalize_browser_mute(
                        config.get("audio", {}).get("browser_muted", False)
                    )
                except audio.AudioUnavailable:
                    pass
                time.sleep(2)

        Thread(target=keep_browser_gain_neutral, daemon=True).start()
    servers[0].serve_forever()
