#!/usr/bin/env python3
"""Simple *stateless* UDP server managing:

* Public lobby broadcasting
* Private rooms (membership tracking + invitation workflow)
* No persistence – everything lives in RAM until process exits.
"""

from __future__ import annotations

import argparse                       # CLI parsing
import json                           # For packet decode
import queue                          # Thread‑safe FIFO between recv‑thread & main
import socket                         # UDP socket operations
import threading                      # Concurrency primitives
from typing import Dict, Set, Tuple   # Typing helpers

from .protocol import (
    ACCEPT_INV, BUF_SIZE, CREATE_ROOM, DEFAULT_PORT, INVITE, JOIN, PUBLIC_MSG,
    QUIT, ROOM_MSG, SYSTEM_MSG, ClientInfo, make_packet, parse_packet,
)
from .util import LOG, get_local_ip
from .packet_spec import EXPECTED_FIELDS_BY_TYPE


class UDPChatServer:
    """Event‑driven UDP server / message router."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        # Listening endpoint (0.0.0.0 allowed if host passed accordingly)
        self.host = host
        self.port = port

        # ------ bind socket ------
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))

        # ------ runtime state ------
        self.clients: Dict[Tuple[str, int], ClientInfo] = {}   # addr ➜ info
        self.rooms: Dict[str, Set[Tuple[str, int]]] = {}       # room ➜ set(addr)
        self.pending_inv: Dict[Tuple[str, int], Set[str]] = {} # addr ➜ invited rooms

        # Thread‑safe queue: recv‑thread pushes datagrams, main thread pops.
        self.recv_q: "queue.Queue[Tuple[bytes, Tuple[str, int]]]" = queue.Queue()

        # Flag to shut all loops down cooperatively.
        self.running = threading.Event()
        self.running.set()

    # ================================================================= main ===
    def start(self) -> None:
        LOG.info("Server listening on %s:%d", self.host, self.port)
        threading.Thread(target=self._recv_loop, daemon=True).start()
        try:
            self._process_loop()              # Forever until Ctrl‑C
        except KeyboardInterrupt:
            LOG.info("Shutdown requested")
        finally:
            self.running.clear()
            self.sock.close()

    # ---------------------------------------------------------------- internals
    def _recv_loop(self) -> None:
        """Listener thread – immediately enqueue received datagrams."""
        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))  # Non‑blocking put()
            except OSError:                    # Socket closed / error
                break

    def _send(self, pkt: bytes, addr: Tuple[str, int]) -> None:
        """Send helper with failure cleanup."""
        try:
            self.sock.sendto(pkt, addr)
        except OSError:
            self._disconnect(addr)             # Remove from tables on network error

    def _broadcast(self, pkt: bytes, exclude: Tuple[str, int] | None = None) -> None:
        """Send a packet to **all** clients except the optional excluded one."""
        for a in list(self.clients):           # Iterate over copy – may mutate inside
            if a != exclude:
                self._send(pkt, a)

    def _disconnect(self, addr: Tuple[str, int]) -> None:
        """Remove client from every structure & log."""
        client = self.clients.pop(addr, None)
        if not client:
            return
        for members in self.rooms.values():   # Remove from all rooms
            members.discard(addr)
        LOG.info("%s left the chat", client.name)

    def _validate_packet(self, pkt: dict) -> bool:
        """Check if a packet contains all required keys for its declared type."""
        ptype = pkt.get("type")
        expected = EXPECTED_FIELDS_BY_TYPE.get(ptype)
        if not expected:
            return False
        return expected.issubset(pkt.keys())
    # ---------------------------------------------------------------- main loop
    def _process_loop(self) -> None:
        """Single‑threaded *router* – dequeue datagrams and dispatch by type."""
        while self.running.is_set():
            try:
                data, addr = self.recv_q.get(timeout=0.5)  # Raises queue.Empty
            except queue.Empty:
                continue                                   # Allow shutdown check

            try:
                pkt = parse_packet(data)
            except json.JSONDecodeError:                   # Ignore garbage
                continue

            if not self._validate_packet(pkt):
                LOG.warning("Dropped malformed packet: %s", pkt)
                continue

            ptype = pkt.get("type")                       # Packet discriminator
            if ptype == JOIN:
                self._handle_join(pkt, addr)
            elif ptype == PUBLIC_MSG:
                self._handle_public(pkt, addr)
            elif ptype == QUIT:
                self._disconnect(addr)
            elif ptype == CREATE_ROOM:
                self._handle_create(pkt, addr)
            elif ptype == INVITE:
                self._handle_invite(pkt, addr)
            elif ptype == ACCEPT_INV:
                self._handle_accept(pkt, addr)
            elif ptype == ROOM_MSG:
                self._handle_room_msg(pkt, addr)

    # ---------------------------------------------------------------- handlers
    def _handle_join(self, pkt: dict, addr: Tuple[str, int]) -> None:
        name = pkt.get("name", "?")
        self.clients[addr] = ClientInfo(addr, name)
        LOG.info("%s joined the chat", name)

    def _handle_public(self, pkt: dict, addr: Tuple[str, int]) -> None:
        client = self.clients.get(addr)
        if not client:
            LOG.warning("Unknown sender %s tried to send public msg", addr)
            return
        text = pkt.get("text", "")
        LOG.info("<%s> %s", client.name, text)
        self._broadcast(make_packet(PUBLIC_MSG, name=client.name, text=text), exclude=addr)

    def _handle_create(self, pkt: dict, addr: Tuple[str, int]) -> None:
        room = pkt.get("room")
        if not room:
            return
        self.rooms.setdefault(room, set()).add(addr)
        LOG.info("%s created room '%s'", self.clients[addr].name, room)
        self._send(make_packet(SYSTEM_MSG, text=f"Room '{room}' created"), addr)

    def _handle_invite(self, pkt: dict, addr: Tuple[str, int]) -> None:
        room, target_name = pkt.get("room"), pkt.get("to")
        if room not in self.rooms or addr not in self.rooms[room]:  # Abuse check
            self._send(make_packet(SYSTEM_MSG, text="You are not in that room"), addr)
            return

        # Find target's network address from name
        target_addr = next((a for a, c in self.clients.items() if c.name == target_name), None)
        if not target_addr:
            self._send(make_packet(SYSTEM_MSG, text="User not found"), addr)
            return

        # Record pending invitation
        self.pending_inv.setdefault(target_addr, set()).add(room)
        invite_pkt = make_packet(INVITE, room=room, **{"from": self.clients[addr].name}, to=target_name)
        self._send(invite_pkt, target_addr)

    def _handle_accept(self, pkt: dict, addr: Tuple[str, int]) -> None:
        room = pkt.get("room")
        if room in self.pending_inv.get(addr, set()):
            self.rooms.setdefault(room, set()).add(addr)
            self.pending_inv[addr].discard(room)
            self._send(make_packet(SYSTEM_MSG, text=f"Joined room '{room}'"), addr)
        else:
            self._send(make_packet(SYSTEM_MSG, text="No invite for that room"), addr)

    def _handle_room_msg(self, pkt: dict, addr: Tuple[str, int]) -> None:
        room, text = pkt.get("room"), pkt.get("text", "")
        if room not in self.rooms or addr not in self.rooms[room]:
            self._send(make_packet(SYSTEM_MSG, text="You are not in that room"), addr)
            return
        sender = self.clients[addr].name
        room_pkt = make_packet(ROOM_MSG, room=room, text=text, **{"from": sender})
        for member in list(self.rooms[room]):
            if member != addr:                # Don't echo to sender
                self._send(room_pkt, member)

# ======================================================================
#  Command‑line entry point
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser("UDP chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    UDPChatServer(get_local_ip(), args.port).start()


if __name__ == "__main__":
    main()
