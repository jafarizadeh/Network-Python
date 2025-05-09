#!/usr/bin/env python3
"""
UDP Chat Client – Simple terminal-based interface using slash commands.
"""

from __future__ import annotations

import argparse
import json
import random
import shlex
import socket
import threading
from typing import Set, Tuple

from .protocol import (
    ACCEPT_INV, BUF_SIZE, CREATE_ROOM, DEFAULT_PORT, INVITE,
    JOIN, PUBLIC_MSG, QUIT, ROOM_MSG, SYSTEM_MSG,
    make_packet, parse_packet,
)
from .utils import LOG, get_local_ip

PROMPT = "> "  # Command-line prompt

class UDPChatClient:
    """
    Client class for connecting to a UDP chat server.
    Supports public messages, private rooms, and invitations.
    """
    def __init__(self, server_ip: str, server_port: int = DEFAULT_PORT) -> None:
        self.server: Tuple[str, int] = (server_ip, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind to a random local port to avoid conflicts
        local_host = get_local_ip()
        local_port = random.randint(6000, 10000)
        self.sock.bind((local_host, local_port))
        LOG.info("Client bound on %s:%d", local_host, local_port)

        self.running = threading.Event()
        self.running.set()

        self.name: str = ""
        self.rooms: Set[str] = set()         # Rooms the client has joined
        self.pending_inv: Set[str] = set()   # Rooms the client has been invited to

    def start(self) -> None:
        """
        Starts the client interface: registers user, starts receiver thread,
        and enters the input loop.
        """
        self.name = input("Your name: ").strip() or f"Guest{random.randint(1000, 9999)}"
        LOG.info("Welcome, %s", self.name)
        self._send(make_packet(JOIN, name=self.name))

        threading.Thread(target=self._recv_loop, daemon=True).start()

        try:
            while self.running.is_set():
                try:
                    line = input(PROMPT)
                except EOFError:
                    break

                if not line:
                    continue
                if line.lower() in {"/quit", "qqq"}:
                    self._send(make_packet(QUIT, name=self.name))
                    break
                if line.startswith("/"):
                    self._handle_command(line)
                else:
                    self._send(make_packet(PUBLIC_MSG, name=self.name, text=line))
        except KeyboardInterrupt:
            pass
        finally:
            self.running.clear()
            self.sock.close()
            LOG.info("Disconnected")

    # ---------------------- Network Helpers ----------------------

    def _send(self, pkt: bytes) -> None:
        """
        Sends a packet to the server.
        """
        try:
            self.sock.sendto(pkt, self.server)
        except OSError as exc:
            LOG.error("Send failed: %s", exc)
            self.running.clear()

    # ---------------------- Receive Loop -------------------------

    def _recv_loop(self) -> None:
        """
        Continuously listens for incoming messages from the server
        and handles them appropriately.
        """
        while self.running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)
                pkt = parse_packet(data)
            except (OSError, json.JSONDecodeError):
                break

            ptype = pkt.get("type")
            if ptype == SYSTEM_MSG:
                print(f"\r[SYSTEM] {pkt['text']}")
            elif ptype == PUBLIC_MSG:
                print(f"\r<{pkt['name']}> {pkt['text']}")
            elif ptype == INVITE:
                room = pkt["room"]
                inviter = pkt["from"]
                self.pending_inv.add(room)
                print(f"\r[INVITE] {inviter} invited you to room '{room}' – /accept {room}")
            elif ptype == ROOM_MSG:
                room, sender, text = pkt["room"], pkt["from"], pkt["text"]
                print(f"\r[Room:{room}] <{sender}> {text}")

            # Reprint prompt after incoming messages
            print(PROMPT, end="", flush=True)

    # ---------------------- Slash Commands ------------------------

    def _handle_command(self, line: str) -> None:
        """
        Parses and executes a slash command entered by the user.
        """
        try:
            cmd, *args = shlex.split(line)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            return

        match cmd.lower():
            case "/create":
                # Usage: /create <room>
                if len(args) != 1:
                    print("Usage: /create <room>"); return
                room = args[0]
                self._send(make_packet(CREATE_ROOM, name=self.name, room=room))
                self.rooms.add(room)  # Optimistically add room
            case "/invite":
                # Usage: /invite <room> <user>
                if len(args) != 2:
                    print("Usage: /invite <room> <user>"); return
                room, user = args
                self._send(make_packet(INVITE, room=room, **{"from": self.name}, to=user))
            case "/accept":
                # Usage: /accept <room>
                if len(args) != 1:
                    print("Usage: /accept <room>"); return
                room = args[0]
                if room not in self.pending_inv:
                    print(f"No pending invite for '{room}'"); return
                self._send(make_packet(ACCEPT_INV, name=self.name, room=room))
                self.pending_inv.discard(room)
                self.rooms.add(room)
            case "/room":
                # Usage: /room <room> <message>
                if len(args) < 2:
                    print("Usage: /room <room> <msg>"); return
                room, msg_text = args[0], " ".join(args[1:])
                if room not in self.rooms:
                    print("You are not a member of that room"); return
                self._send(make_packet(ROOM_MSG, room=room,
                                       **{"from": self.name}, text=msg_text))
            case _:
                print("Unknown command – try /create, /invite, /accept, /room, /quit")

# --------------------------- CLI Entry Point ----------------------------

def main() -> None:
    """
    Parses command-line arguments and launches the chat client.
    """
    parser = argparse.ArgumentParser("UDP chat client")
    parser.add_argument("server_ip", help="IP address of chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port of server")
    args = parser.parse_args()
    UDPChatClient(args.server_ip, args.port).start()

if __name__ == "__main__":
    main()
