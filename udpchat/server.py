"""UDP chat **server** module – run with ``python -m udpchat.server``."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from typing import Dict, Tuple

from .protocol import (
    BUF_SIZE,
    DEFAULT_PORT,
    ClientInfo,
    make_packet,
    parse_packet,
)
from .utils import LOG, get_local_ip

__all__ = ["UDPChatServer", "main"]


class UDPChatServer:
    """A very lightweight UDP chat server."""

    def __init__(self, host: str, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))

        self.clients: Dict[Tuple[str, int], ClientInfo] = {}
        self.recv_q: "queue.Queue[Tuple[bytes, Tuple[str, int]]]" = queue.Queue()
        self.running = threading.Event()
        self.running.set()

    # ------------------------------------------------------------------
    def start(self) -> None:
        LOG.info("Server listening on %s:%d", self.host, self.port)
        threading.Thread(target=self._recv_loop, daemon=True).start()
        try:
            self._process_loop()
        except KeyboardInterrupt:
            LOG.info("KeyboardInterrupt → shutting down server")
        finally:
            self.running.clear()
            self.sock.close()

    # ------------------------------------------------------------------
    def _recv_loop(self) -> None:
        """Background thread – receives UDP datagrams and queues them."""

        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))
            except OSError:  # socket closed
                break

    # ------------------------------------------------------------------
    def _broadcast(self, data: bytes, exclude: Tuple[str, int] | None = None):
        for addr in list(self.clients.keys()):
            if addr == exclude:
                continue
            try:
                self.sock.sendto(data, addr)
            except OSError:
                LOG.warning("Failed to send to %s – removing from client list", addr)
                self.clients.pop(addr, None)

    # ------------------------------------------------------------------
    def _process_loop(self):
        while self.running.is_set():
            try:
                data, addr = self.recv_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                pkt = parse_packet(data)
            except json.JSONDecodeError:
                LOG.warning("Malformed packet from %s", addr)
                continue

            ptype = pkt.get("type")
            if ptype == "join":
                name = pkt.get("name", "?")
                self.clients[addr] = ClientInfo(addr, name)
                LOG.info("%s joined from %s", name, addr)
                self._broadcast(
                    make_packet("msg", name="System", text=f"{name} joined the chat")
                )

            elif ptype == "msg":
                client = self.clients.get(addr)
                if not client:
                    LOG.warning("Unknown client %s tried to send a message", addr)
                    continue
                LOG.info("<%s> %s", client.name, pkt.get("text", ""))
                self._broadcast(data, exclude=addr)

            elif ptype == "quit":
                client = self.clients.pop(addr, None)
                if client:
                    LOG.info("%s left the chat", client.name)
                    self._broadcast(
                        make_packet("msg", name="System", text=f"{client.name} left the chat")
                    )


# -------------------------------------------------------------
# CLI entry point for server
# -------------------------------------------------------------

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="UDP chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to listen on")
    args = parser.parse_args(argv)
    UDPChatServer(get_local_ip(), args.port).start()


if __name__ == "__main__":  # pragma: no cover
    main()
