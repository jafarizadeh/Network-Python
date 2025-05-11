#!/usr/bin/env python3
"""Command‑line UDP chat *client* supporting:

* Public lobby
* Private rooms (create / invite / accept)
* Context‑aware prompt: "room# " while inside a room, plain "> " otherwise.
* ANSI‑coloured output via *colorama*.

Usage (after installing package locally):

    python -m udpchat.client 203.0.113.22  # Connect to server's IP
"""

from __future__ import annotations                # ↩ type hints forward refs OK

import argparse                                    # For CLI parsing
import json                                        # For packet decoding in listener
import random                                      # Random guest name / port choice
import shlex                                       # Robust command splitting
import socket                                      # Low‑level UDP API
import threading                                   # Background listener thread
from typing import Optional, Set, Tuple            # Typing aids
import sys                                         # Needed for prompt redraw

# ---------- Shared protocol symbols / helpers ----------
from .protocol import (
    ACCEPT_INV, BUF_SIZE, CREATE_ROOM, DEFAULT_PORT, INVITE, JOIN, PUBLIC_MSG,
    QUIT, ROOM_MSG, SYSTEM_MSG, make_packet, parse_packet,
)

# ---------- Local utilities ----------
from .util import LOG, get_local_ip

# 3rd‑party: coloured terminal output (safe if absent – pip install colorama)
from colorama import Fore, Style, init
init(autoreset=True)                               # Reset colour after each print


class UDPChatClient:
    """Embeds the entire client state machine – can also be used programmatically."""

    def __init__(self, server_ip: str, server_port: int = DEFAULT_PORT) -> None:
        # -------- server endpoint --------
        self.server: Tuple[str, int] = (server_ip, server_port)  # Where to send to

        # -------- create/bind UDP socket --------
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Rebind ok

        # Bind to *random* high port on the local machine so multiple clients can run
        local_host = get_local_ip()
        local_port = random.randint(6000, 10000)
        self.sock.bind((local_host, local_port))
        LOG.info("Client bound on %s:%d", local_host, local_port)

        # -------- control flags --------
        self.running = threading.Event()  # Cooperative shutdown across threads
        self.running.set()

        # -------- dynamic state --------
        self.name: str = ""                    # Chosen nickname (set in start())
        self.rooms: Set[str] = set()           # Rooms we're member of
        self.pending_inv: Set[str] = set()     # Invitations awaiting /accept
        self.current_room: Optional[str] = None  # ≈ context for prompt & sends

    # ================================================================== main ===
    def start(self) -> None:
        """Blocking run‑loop: interactively read stdin while a background thread
        listens for server datagrams.
        """
        # -------- greet & join lobby --------
        self.name = input("Your name: ").strip() or f"Guest{random.randint(1000,9999)}"
        LOG.info("Welcome, %s", self.name)
        self._send(make_packet(JOIN, name=self.name))

        # -------- spawn receiver thread --------
        threading.Thread(target=self._recv_loop, daemon=True).start()

        # -------- main input loop --------
        try:
            while self.running.is_set():                  # until /quit or Ctrl‑C
                try:
                    line = input(self._prompt())          # Blocking stdin read
                except EOFError:                          # Ctrl‑D on *nix
                    break

                # ---- context escape (exit private room) ----
                if self.current_room and line.strip().lower() in {"exit", "end"}:
                    self.current_room = None              # Back to lobby
                    continue

                # ---- global quit ----
                if line.lower() in {"/quit", "qqq"}:     # Short alias `qqq`
                    self._send(make_packet(QUIT, name=self.name))
                    break

                # ---- slash command (/create /invite ...) ----
                if line.startswith("/"):
                    self._handle_command(line)
                    continue

                # ---- room‑scoped message ----
                if self.current_room:
                    self._send(make_packet(ROOM_MSG, room=self.current_room, **{"from": self.name}, text=line))
                    continue

                # ---- default: lobby public message ----
                self._send(make_packet(PUBLIC_MSG, name=self.name, text=line))
        except KeyboardInterrupt:  # Graceful Ctrl‑C
            pass
        finally:
            self.running.clear()
            self.sock.close()
            LOG.info("Disconnected")

    # ---------------------------------------------------------------- networking
    def _send(self, pkt: bytes) -> None:
        """Thin wrapper around sock.sendto() with basic error handling."""
        try:
            self.sock.sendto(pkt, self.server)
        except OSError as exc:
            LOG.error("Send failed: %s", exc)
            self.running.clear()

    # ---------------------------------------------------------------- receive loop
    def _recv_loop(self) -> None:
        """Background thread – prints inbound packets then redraws prompt."""
        while self.running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)     # Blocking recv
                pkt = parse_packet(data)                   # bytes ⟶ dict
            except (OSError, json.JSONDecodeError):        # Socket closed or garbled
                break

            ptype = pkt.get("type")                        # Discriminator
            if ptype == SYSTEM_MSG:                        # Informational/error
                print(f"\r{Fore.CYAN}[SYSTEM]{Style.RESET_ALL} {pkt['text']}")
            elif ptype == PUBLIC_MSG:                      # Lobby broadcast
                print(f"\r{Fore.GREEN}<{pkt['name']}>{Style.RESET_ALL} {pkt['text']}")
            elif ptype == INVITE:                          # Room invitation
                room = pkt["room"]; inviter = pkt["from"]
                self.pending_inv.add(room)
                print(f"\r{Fore.MAGENTA}[INVITE]{Style.RESET_ALL} {inviter} invited you to room '{room}' – /accept {room}")
            elif ptype == ROOM_MSG:                        # Private room chat
                room, sender, text = pkt["room"], pkt["from"], pkt["text"]
                tag = "" if room == self.current_room else f"[{room}] "
                colour = Fore.YELLOW if room == self.current_room else Fore.BLUE
                print(f"\r{colour}{tag}<{sender}>{Style.RESET_ALL} {text}")
            # Prompt re‑paint so the user's current input line isn't lost
            sys.stdout.write(self._prompt())
            sys.stdout.flush()

    # ---------------------------------------------------------------- command parser
    def _handle_command(self, line: str) -> None:
        """Parse & execute user slash‑commands using shlex for proper quoting."""
        try:
            cmd, *args = shlex.split(line)            # Splits honouring quotes
        except ValueError as exc:
            print(f"Parse error: {exc}")
            return

        match cmd.lower():
            # ------------------------- /create <room> -------------------------
            case "/create":
                if len(args) != 1:
                    print("Usage: /create <room>")
                    return
                room = args[0]
                self._send(make_packet(CREATE_ROOM, name=self.name, room=room))
                self.rooms.add(room)
                self.current_room = room               # Auto‑enter

            # ------------------------- /invite <room> <user> ------------------
            case "/invite":
                if len(args) != 2:
                    print("Usage: /invite <room> <user>")
                    return
                room, user = args
                self._send(make_packet(INVITE, room=room, **{"from": self.name}, to=user))

            # ------------------------- /accept <room> -------------------------
            case "/accept":
                if len(args) != 1:
                    print("Usage: /accept <room>")
                    return
                room = args[0]
                if room not in self.pending_inv:
                    print(f"No pending invite for '{room}'")
                    return
                self._send(make_packet(ACCEPT_INV, name=self.name, room=room))
                self.pending_inv.discard(room)
                self.rooms.add(room)
                self.current_room = room              # Switch context

            # ------------------------- /room <room> <msg> ---------------------
            case "/room":
                if len(args) < 2:
                    print("Usage: /room <room> <msg>")
                    return
                room, msg_text = args[0], " ".join(args[1:])
                if room not in self.rooms:
                    print("You are not a member of that room")
                    return
                self._send(make_packet(ROOM_MSG, room=room, **{"from": self.name}, text=msg_text))

            # ------------------------- unknown cmd ----------------------------
            case _:
                print("Unknown command")

    # ---------------------------------------------------------------- helper prompt
    def _prompt(self) -> str:
        """Return dynamic prompt according to context (room#  vs  > )."""
        return f"{self.current_room}# " if self.current_room else "> "

# ======================================================================
#  Command‑line entry point
# ======================================================================

def main() -> None:
    """Parse CLI args then instantiate & run the chat client."""
    parser = argparse.ArgumentParser("UDP chat client")
    parser.add_argument("server_ip", help="IP address of chat server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port of server")
    args = parser.parse_args()
    UDPChatClient(args.server_ip, args.port).start()


if __name__ == "__main__":
    main()
