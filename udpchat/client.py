#!/usr/bin/env python3
"""
UDP Chat Client – lobby + private rooms with context-aware prompt.

* default prompt  : "> "
* after /create or /accept → "roomName# "
* plain text goes to current room
* type `exit` or `end` to leave the room and return to lobby
"""

from __future__ import annotations

import argparse
import json
import random
import shlex
import socket
import threading
from typing import Optional, Set, Tuple
import sys

from .protocol import (
    ACCEPT_INV,
    BUF_SIZE,
    CREATE_ROOM,
    DEFAULT_PORT,
    INVITE,
    JOIN,
    PUBLIC_MSG,
    QUIT,
    ROOM_MSG,
    SYSTEM_MSG,
    make_packet,
    parse_packet,
)
from .utils import LOG, get_local_ip
from colorama import Fore, Style, init
init(autoreset=True)



class UDPChatClient:
    def __init__(self, server_ip: str, server_port: int = DEFAULT_PORT) -> None:
        self.server: Tuple[str, int] = (server_ip, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        local_host = get_local_ip()
        local_port = random.randint(6000, 10000)
        self.sock.bind((local_host, local_port))
        LOG.info("Client bound on %s:%d", local_host, local_port)

        self.running = threading.Event()
        self.running.set()

        self.name: str = ""
        self.rooms: Set[str] = set()
        self.pending_inv: Set[str] = set()
        self.current_room: Optional[str] = None  # active room context

    # ---------------------------------------------------------------- main
    def start(self) -> None:
        self.name = (
            input("Your name: ").strip() or f"Guest{random.randint(1000, 9999)}"
        )
        LOG.info("Welcome, %s", self.name)
        self._send(make_packet(JOIN, name=self.name))

        threading.Thread(target=self._recv_loop, daemon=True).start()

        try:
            while self.running.is_set():
                try:
                    line = input(self._prompt())
                except EOFError:
                    break

                # leave room context
                if self.current_room and line.strip().lower() in {"exit", "end"}:
                    self.current_room = None
                    continue

                # global quit
                if line.lower() in {"/quit", "qqq"}:
                    self._send(make_packet(QUIT, name=self.name))
                    break

                # slash command
                if line.startswith("/"):
                    self._handle_command(line)
                    continue

                # inside room → send to room
                if self.current_room:
                    self._send(
                        make_packet(
                            ROOM_MSG,
                            room=self.current_room,
                            **{"from": self.name},
                            text=line,
                        )
                    )
                    continue

                # default public lobby
                self._send(make_packet(PUBLIC_MSG, name=self.name, text=line))
        except KeyboardInterrupt:
            pass
        finally:
            self.running.clear()
            self.sock.close()
            LOG.info("Disconnected")

    # --------------------------------------------------------- networking
    def _send(self, pkt: bytes) -> None:
        try:
            self.sock.sendto(pkt, self.server)
        except OSError as exc:
            LOG.error("Send failed: %s", exc)
            self.running.clear()

    # --------------------------------------------------------- receive loop
    def _recv_loop(self) -> None:
        while self.running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)
                pkt = parse_packet(data)
            except (OSError, json.JSONDecodeError):
                break

            ptype = pkt.get("type")
            if ptype == SYSTEM_MSG:
                print(f"\r{Fore.CYAN}[SYSTEM]{Style.RESET_ALL} {pkt['text']}")
            elif ptype == PUBLIC_MSG:
                print(f"\r{Fore.GREEN}<{pkt['name']}>{Style.RESET_ALL} {pkt['text']}")
            elif ptype == INVITE:
                room = pkt["room"]
                inviter = pkt["from"]
                self.pending_inv.add(room)
                print(
                    f"\r{Fore.MAGENTA}[INVITE]{Style.RESET_ALL} {inviter} invited you to room '{room}' – /accept {room}"
                )
            elif ptype == ROOM_MSG:
                room, sender, text = pkt["room"], pkt["from"], pkt["text"]
                tag = "" if room == self.current_room else f"[{room}] "
                colour = Fore.YELLOW if room == self.current_room else Fore.BLUE
                print(f"\r{colour}{tag}<{sender}>{Style.RESET_ALL} {text}")
            sys.stdout.write(self._prompt())
            sys.stdout.flush()

    # --------------------------------------------------------- command parser
    def _handle_command(self, line: str) -> None:
        try:
            cmd, *args = shlex.split(line)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            return

        match cmd.lower():
            case "/create":
                if len(args) != 1:
                    print("Usage: /create <room>")
                    return
                room = args[0]
                self._send(make_packet(CREATE_ROOM, name=self.name, room=room))
                self.rooms.add(room)
                self.current_room = room
            case "/invite":
                if len(args) != 2:
                    print("Usage: /invite <room> <user>")
                    return
                room, user = args
                self._send(
                    make_packet(
                        INVITE,
                        room=room,
                        **{"from": self.name},
                        to=user,
                    )
                )
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
                self.current_room = room
            case "/room":
                if len(args) < 2:
                    print("Usage: /room <room> <msg>")
                    return
                room, msg_text = args[0], " ".join(args[1:])
                if room not in self.rooms:
                    print("You are not a member of that room")
                    return
                self._send(
                    make_packet(
                        ROOM_MSG,
                        room=room,
                        **{"from": self.name},
                        text=msg_text,
                    )
                )
            case _:
                print("Unknown command")

    # --------------------------------------------------------- helper prompt
    def _prompt(self) -> str:
        return f"{self.current_room}# " if self.current_room else "> "


# ---------------------------------------------------------------- CLI
def main() -> None:
    parser = argparse.ArgumentParser("UDP chat client")
    parser.add_argument("server_ip", help="IP address of chat server")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="UDP port of server"
    )
    args = parser.parse_args()
    UDPChatClient(args.server_ip, args.port).start()


if __name__ == "__main__":
    main()
