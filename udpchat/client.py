"""UDP chat **client** module – run with ``python -m udpchat.client``."""

from __future__ import annotations

import argparse
import json
import random
import socket
import threading
from typing import Tuple

from .protocol import BUF_SIZE, DEFAULT_PORT, make_packet, parse_packet
from .utils import LOG, get_local_ip

__all__ = ["UDPChatClient", "main"]


class UDPChatClient:
    """Simple terminal‑based chat client for the UDP chat protocol."""

    def __init__(self, server_ip: str, server_port: int = DEFAULT_PORT):
        self.server: Tuple[str, int] = (server_ip, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        local_host = get_local_ip()
        local_port = random.randint(6000, 10000)
        self.sock.bind((local_host, local_port))
        LOG.info("Client bound on %s:%d", local_host, local_port)

        self.running = threading.Event()
        self.running.set()

    # ------------------------------------------------------------------
    def start(self):
        name = input("Your name: ").strip() or f"Guest{random.randint(1000, 9999)}"
        LOG.info("Welcome, %s", name)
        self.sock.sendto(make_packet("join", name=name), self.server)

        threading.Thread(target=self._recv_loop, daemon=True).start()

        try:
            while self.running.is_set():
                try:
                    text = input()
                except EOFError:
                    break
                if text.lower() in {"/quit", "qqq"}:
                    self.sock.sendto(make_packet("quit", name=name), self.server)
                    break
                if text.strip():
                    self.sock.sendto(make_packet("msg", name=name, text=text), self.server)
        except KeyboardInterrupt:
            pass
        finally:
            self.running.clear()
            self.sock.close()
            LOG.info("Disconnected.")

    # ------------------------------------------------------------------
    def _recv_loop(self):
        while self.running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)
                pkt = parse_packet(data)
                if pkt.get("type") == "msg":
                    print(f"\r<{pkt['name']}> {pkt['text']}")
                    print("> ", end="", flush=True)
            except (OSError, json.JSONDecodeError):
                break


# -------------------------------------------------------------
# CLI entry point for client
# -------------------------------------------------------------

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="UDP chat client")
    parser.add_argument("server_ip", help="IP address of chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port of server")
    args = parser.parse_args(argv)
    UDPChatClient(args.server_ip, args.port).start()


if __name__ == "__main__":  # pragma: no cover
    main()
