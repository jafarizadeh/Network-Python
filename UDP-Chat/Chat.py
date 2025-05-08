#!/usr/bin/env python3
"""A more robust UDP chat application (client & server in one file).

Improvements over the original script:
  • uses argparse for clean CLI handling
  • separates concerns via Server & Client classes
  • JSON‑based message protocol with explicit **type** fields
  • proper logging & graceful shutdown (no os._exit!)
  • thread‑safe queues + Event objects for clean thread termination
  • gets a real LAN IP instead of hard‑coding 127.0.0.1 in most cases
  • avoids WinError 10048 by allowing SO_REUSEADDR and exposing the port as an argument
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import socket
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

BUF_SIZE = 1024  # bytes
DEFAULT_PORT = 5000

###############################################################################
# Helper utilities
###############################################################################

def get_local_ip() -> str:
    """Return the best‑guess LAN IP of this machine (e.g. 192.168.x.x)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # We don’t need to reach 8.8.8.8 – connect() just selects the interface.
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def now() -> str:
    """Current time (HH:MM:SS) for log messages."""
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}")

###############################################################################
# Message protocol helpers
###############################################################################

def make_join(name: str) -> bytes:
    return json.dumps({"type": "join", "name": name}).encode()


def make_msg(name: str, text: str) -> bytes:
    return json.dumps({"type": "msg", "name": name, "text": text}).encode()


def make_quit(name: str) -> bytes:
    return json.dumps({"type": "quit", "name": name}).encode()


def parse_packet(data: bytes) -> dict:
    return json.loads(data.decode())

###############################################################################
# Server implementation
###############################################################################

@dataclass
class ClientInfo:
    addr: Tuple[str, int]
    name: str


class UDPChatServer:
    def __init__(self, host: str, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))

        self.clients: Dict[Tuple[str, int], ClientInfo] = {}
        self.recv_q: "queue.Queue[Tuple[bytes, Tuple[str, int]]]" = queue.Queue()
        self._running = threading.Event()
        self._running.set()

    # -------------------------- public API ----------------------------------
    def start(self) -> None:
        log(f"Server listening on {self.host}:{self.port}")
        threading.Thread(target=self._recv_loop, daemon=True).start()
        try:
            self._process_loop()
        except KeyboardInterrupt:
            log("Shutting down server …")
        finally:
            self.sock.close()

    # ------------------------ internal helpers ------------------------------
    def _recv_loop(self) -> None:
        while self._running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))
            except OSError:
                break  # socket closed

    def _broadcast(self, data: bytes, exclude: Tuple[str, int] | None = None) -> None:
        for addr in list(self.clients.keys()):
            if addr == exclude:
                continue
            try:
                self.sock.sendto(data, addr)
            except OSError:
                # client unreachable → drop it
                self.clients.pop(addr, None)

    def _process_loop(self) -> None:
        while self._running.is_set():
            try:
                data, addr = self.recv_q.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                pkt = parse_packet(data)
            except json.JSONDecodeError:
                log(f"Malformed packet from {addr}: {data!r}")
                continue

            ptype = pkt.get("type")
            if ptype == "join":
                name = pkt["name"]
                self.clients[addr] = ClientInfo(addr, name)
                log(f"{name} joined from {addr}")
                self._broadcast(make_msg("System", f"{name} joined the chat"))

            elif ptype == "msg":
                if addr not in self.clients:
                    # ignore unknown client messages
                    continue
                name = self.clients[addr].name
                text = pkt.get("text", "")
                log(f"<{name}> {text}")
                self._broadcast(make_msg(name, text), exclude=addr)

            elif ptype == "quit":
                client = self.clients.pop(addr, None)
                if client:
                    log(f"{client.name} left the chat")
                    self._broadcast(make_msg("System", f"{client.name} left the chat"), exclude=addr)

###############################################################################
# Client implementation
###############################################################################

class UDPChatClient:
    def __init__(self, server_ip: str, server_port: int = DEFAULT_PORT):
        self.server = (server_ip, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        local_host = get_local_ip()
        local_port = random.randint(6000, 10000)
        self.sock.bind((local_host, local_port))
        log(f"Client bound on {local_host}:{local_port}")

        self._running = threading.Event()
        self._running.set()

    # -------------------------- public API ----------------------------------
    def start(self) -> None:
        name = input("Your name: ").strip() or f"Guest{random.randint(1000, 9999)}"
        log(f"Welcome, {name}!")
        self.sock.sendto(make_join(name), self.server)

        threading.Thread(target=self._recv_loop, daemon=True).start()
        try:
            while self._running.is_set():
                try:
                    text = input()
                except EOFError:
                    break
                if text.lower() in {"/quit", "qqq"}:
                    self.sock.sendto(make_quit(name), self.server)
                    break
                if text.strip():
                    self.sock.sendto(make_msg(name, text), self.server)
        except KeyboardInterrupt:
            pass
        finally:
            self._running.clear()
            self.sock.close()
            log("Disconnected.")

    # ------------------------ internal helpers ------------------------------
    def _recv_loop(self) -> None:
        while self._running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)
                pkt = parse_packet(data)
                ptype = pkt.get("type")
                if ptype == "msg":
                    print(f"\r<{pkt['name']}> {pkt['text']}")
                    print("> ", end="", flush=True)  # prompt again
            except (OSError, json.JSONDecodeError):
                break

###############################################################################
# CLI handling
###############################################################################

def main() -> None:
    parser = argparse.ArgumentParser(description="UDP Chat (client & server)")
    sub = parser.add_subparsers(dest="mode", required=True)

    srv = sub.add_parser("server", help="run as chat server")
    srv.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to listen on")

    cli = sub.add_parser("client", help="run as chat client")
    cli.add_argument("server_ip", help="IP address of chat server")
    cli.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port of server")

    args = parser.parse_args()

    if args.mode == "server":
        host = get_local_ip()
        UDPChatServer(host, args.port).start()
    elif args.mode == "client":
        UDPChatClient(args.server_ip, args.port).start()
    else:
        parser.error("Unknown mode")


if __name__ == "__main__":
    main()
