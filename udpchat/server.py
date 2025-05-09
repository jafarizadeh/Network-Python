#!/usr/bin/env python3
"""
UDP Chat Server – Supports public lobby and private rooms with invitation mechanism.
"""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from typing import Dict, Set, Tuple

# Import protocol definitions and utilities
from .protocol import (
    ACCEPT_INV, BUF_SIZE, CREATE_ROOM, DEFAULT_PORT, INVITE,
    JOIN, PUBLIC_MSG, QUIT, ROOM_MSG, SYSTEM_MSG,
    ClientInfo, make_packet, parse_packet,
)
from .utils import LOG, get_local_ip


class UDPChatServer:
    """
    Main server class handling user connections, message routing, 
    public lobby and private room management over UDP.
    """
    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port

        # Set up a UDP socket with address reuse option
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))

        # Connected clients: addr -> ClientInfo
        self.clients: Dict[Tuple[str, int], ClientInfo] = {}

        # Rooms: room_name -> set of client addresses
        self.rooms: Dict[str, Set[Tuple[str, int]]] = {}

        # Pending invitations: addr -> set of room names
        self.pending_inv: Dict[Tuple[str, int], Set[str]] = {}

        # Queue for incoming messages
        self.recv_q: "queue.Queue[Tuple[bytes, Tuple[str, int]]]" = queue.Queue()

        # Control flag for server loop
        self.running = threading.Event()
        self.running.set()

    def start(self) -> None:
        """
        Starts the server: begins receiving and processing packets.
        """
        LOG.info("Server listening on %s:%d", self.host, self.port)
        threading.Thread(target=self._recv_loop, daemon=True).start()

        try:
            self._process_loop()
        except KeyboardInterrupt:
            LOG.info("Shutdown requested")
        finally:
            self.running.clear()
            self.sock.close()

    # ===================== Internal helpers =====================
    def _recv_loop(self) -> None:
        """
        Background thread that receives incoming UDP packets and puts them into the queue.
        """
        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))
            except OSError:
                break

    def _send(self, pkt: bytes, addr: Tuple[str, int]) -> None:
        """
        Sends a packet to a specific client address.
        """
        try:
            self.sock.sendto(pkt, addr)
        except OSError:
            self._disconnect(addr)

    def _broadcast(self, pkt: bytes, exclude: Tuple[str, int] | None = None) -> None:
        """
        Sends a packet to all connected clients, optionally excluding one.
        """
        for a in list(self.clients):
            if a != exclude:
                self._send(pkt, a)

    def _disconnect(self, addr: Tuple[str, int]) -> None:
        """
        Handles client disconnection: removes from all lists and broadcasts a leave message.
        """
        client = self.clients.pop(addr, None)
        if not client:
            return
        for members in self.rooms.values():
            members.discard(addr)
        msg = f"{client.name} left the chat"
        LOG.info(msg)
        self._broadcast(make_packet(SYSTEM_MSG, text=msg))

    # ===================== Main loop =========================
    def _process_loop(self) -> None:
        """
        Main loop that processes incoming packets from the queue.
        """
        while self.running.is_set():
            try:
                data, addr = self.recv_q.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                pkt = parse_packet(data)
            except json.JSONDecodeError:
                continue

            ptype = pkt.get("type")

            # Dispatch based on packet type
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

    # ===================== Handlers ==========================
    def _handle_join(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles new client joining the chat.
        """
        name = pkt.get("name", "?")
        self.clients[addr] = ClientInfo(addr, name)
        msg = f"{name} joined the chat"
        LOG.info(msg)
        self._broadcast(make_packet(SYSTEM_MSG, text=msg))

    def _handle_public(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles public message sent to all clients in the lobby.
        """
        client = self.clients.get(addr)
        if not client:
            return
        text = pkt.get("text", "")
        LOG.info("<%s> %s", client.name, text)
        self._broadcast(
            make_packet(PUBLIC_MSG, name=client.name, text=text),
            exclude=addr,
        )

    def _handle_create(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles creation of a new private room by a client.
        """
        room = pkt.get("room")
        if not room:
            return
        self.rooms.setdefault(room, set()).add(addr)
        self._send(make_packet(SYSTEM_MSG, text=f"Room '{room}' created"), addr)

    def _handle_invite(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles sending an invitation from one client to another for a private room.
        """
        room, target_name = pkt.get("room"), pkt.get("to")
        if room not in self.rooms or addr not in self.rooms[room]:
            self._send(make_packet(SYSTEM_MSG, text="You are not in that room"), addr)
            return

        # Find target by name
        target_addr = next(
            (a for a, c in self.clients.items() if c.name == target_name), None
        )
        if not target_addr:
            self._send(make_packet(SYSTEM_MSG, text="User not found"), addr)
            return

        self.pending_inv.setdefault(target_addr, set()).add(room)
        invite_pkt = make_packet(
            INVITE,
            room=room,
            **{"from": self.clients[addr].name},
        )
        self._send(invite_pkt, target_addr)

    def _handle_accept(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles a client accepting an invitation to join a private room.
        """
        room = pkt.get("room")
        if room in self.pending_inv.get(addr, set()):
            self.rooms.setdefault(room, set()).add(addr)
            self.pending_inv[addr].discard(room)
            self._send(make_packet(SYSTEM_MSG, text=f"Joined room '{room}'"), addr)
        else:
            self._send(make_packet(SYSTEM_MSG, text="No invite for that room"), addr)

    def _handle_room_msg(self, pkt: dict, addr: Tuple[str, int]) -> None:
        """
        Handles sending a message within a specific private room.
        """
        room, text = pkt.get("room"), pkt.get("text", "")
        if room not in self.rooms or addr not in self.rooms[room]:
            self._send(make_packet(SYSTEM_MSG, text="You are not in that room"), addr)
            return
        sender = self.clients[addr].name
        room_pkt = make_packet(
            ROOM_MSG, room=room, text=text, **{"from": sender}
        )
        for member in list(self.rooms[room]):
            if member != addr:
                self._send(room_pkt, member)

# ===================== Command-Line Interface =====================
def main() -> None:
    """
    Parses command-line arguments and starts the server.
    """
    parser = argparse.ArgumentParser("UDP chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    UDPChatServer(get_local_ip(), args.port).start()

if __name__ == "__main__":
    main()
