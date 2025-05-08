#!/usr/bin/env python3
"""A more robust UDP chat application (client & server in one file) with proper
logging support (console + rotating file log).

Run as server:
    python udp_chat.py server --port 5000

Run as client:
    python udp_chat.py client <SERVER_IP> --port 5000

Key features:
  • argparse CLI
  • JSON‑based protocol {type: join|msg|quit}
  • logging module (INFO level to console + rotating file)
  • graceful shutdown with threading.Event
  • SO_REUSEADDR to avoid “address already in use”
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
from logging.handlers import RotatingFileHandler
from typing import Dict, Tuple
import logging

###############################################################################
# Logging configuration
###############################################################################

def configure_logging() -> logging.Logger:
    logger = logging.getLogger("udpchat")
    logger.setLevel(logging.INFO)

    # Console handler --------------------------------------------------------
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    # File handler with rotation --------------------------------------------
    fh = RotatingFileHandler("udp_chat.log", maxBytes=1_048_576, backupCount=3)
    fh.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%H:%M:%S")
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

LOG = configure_logging()

###############################################################################
# Constants & helpers
###############################################################################

BUF_SIZE = 1024
DEFAULT_PORT = 5000


def get_local_ip() -> str:
    """Return best‑guess LAN IP (falls back to 127.0.0.1)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

###############################################################################
# Message protocol helpers
###############################################################################

def make_packet(ptype: str, **payload) -> bytes:
    payload["type"] = ptype
    return json.dumps(payload).encode()


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
        self.running = threading.Event()
        self.running.set()

    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    def _recv_loop(self) -> None:
        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))
            except OSError:
                break

    def _broadcast(self, data: bytes, exclude: Tuple[str, int] | None = None):
        for addr in list(self.clients.keys()):
            if addr == exclude:
                continue
            try:
                self.sock.sendto(data, addr)
            except OSError:
                LOG.warning("Failed to send to %s – removing from client list", addr)
                self.clients.pop(addr, None)

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
                self._broadcast(make_packet("msg", name="System", text=f"{name} joined the chat"))

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
                    self._broadcast(make_packet("msg", name="System", text=f"{client.name} left the chat"))

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

###############################################################################
# CLI entry point
###############################################################################

def main():
    parser = argparse.ArgumentParser(description="UDP chat application")
    sub = parser.add_subparsers(dest="mode", required=True)

    srv = sub.add_parser("server", help="run as server")
    srv.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to listen on")

    cli = sub.add_parser("client", help="run as client")
    cli.add_argument("server_ip", help="IP address of chat server")
    cli.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port of server")

    args = parser.parse_args()

    if args.mode == "server":
        UDPChatServer(get_local_ip(), args.port).start()
    elif args.mode == "client":
        UDPChatClient(args.server_ip, args.port).start()


if __name__ == "__main__":
    main()
