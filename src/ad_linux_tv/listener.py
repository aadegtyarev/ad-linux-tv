"""Start configured LAN and loopback-only bridge listeners."""

import ipaddress
import socket
from http.server import ThreadingHTTPServer
from threading import Thread

from .server import make_handler


class AddressServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def make_server(address, port, handler):
    server_class = type(
        "Listener",
        (AddressServer,),
        {"address_family": socket.AF_INET6 if ":" in address else socket.AF_INET},
    )
    return server_class((address, port), handler)


def serve(config):
    address = ipaddress.ip_address(config["bind"])
    handler = make_handler(config)
    servers = [make_server(str(address), config["port"], handler)]
    if str(address) != "127.0.0.1" and not (address.version == 4 and address.is_unspecified):
        servers.append(make_server("127.0.0.1", config["port"], handler))
    for listener in servers[1:]:
        Thread(target=listener.serve_forever, daemon=True).start()
    servers[0].serve_forever()
