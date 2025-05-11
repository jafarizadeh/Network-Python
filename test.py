# ========================
#  udpchat/__init__.py
# ========================
"""UDP Chat – a minimal UDP‑based chat library.

Importing this package exposes :class:`udpchat.UDPChatServer` and
:class:`udpchat.UDPChatClient`, allowing the whole stack to be embedded in
another application or launched via ``python -m udpchat``.
"""

# ------------------------ re‑exports ------------------------
# Importing here makes `from udpchat import UDPChatClient` possible without
# digging into sub‑modules.
from .client import UDPChatClient   # noqa: F401  ── re‑export client class
from .server import UDPChatServer   # noqa: F401  ── re‑export server class

# ------------------------ public API ------------------------
# __all__ tells linters / wildcard importers which names are considered the
# library's official surface.
__all__: list[str] = [
    "UDPChatClient",  # Chat client (lobby + private rooms)
    "UDPChatServer",  # Matching UDP server implementation
]

# ======================================================================
#  udpchat/protocol.py
# ======================================================================
#!/usr/bin/env python3
"""Shared constants, helpers and a dataclass used by **both** client & server.

Everything that travels over the network is encoded/decoded via the utilities
here so that client & server never disagree on wire‑format details.
"""

from __future__ import annotations       # Postponed annotation evaluation (PEP 563)
import json                              # JSON is our lightweight wire format
from dataclasses import dataclass        # Handy, immutable record type for client info
from typing import Dict, Tuple           # Standard typing aliases

# --- Network configuration -------------------------------------------------
BUF_SIZE: int = 1024          # Max UDP datagram size we accept/read (bytes)
DEFAULT_PORT: int = 5000      # Well‑known port on which server listens

# --- Packet‑type identifiers ----------------------------------------------
# Every datagram carries a JSON object with a top‑level "type" field set to one
# of the below symbolic strings.  Having explicit names beats using raw ints
# because: a) self‑documenting, b) easy to grep.
JOIN         = "join"           # A client announces presence in the public lobby
PUBLIC_MSG   = "msg"            # A plain lobby chat message
QUIT         = "quit"           # A client disconnects cleanly

CREATE_ROOM  = "create_room"    # Ask server to create private room & add caller
INVITE       = "invite"         # Invite another user to a private room
ACCEPT_INV   = "accept_invite"  # Target user accepts invitation
ROOM_MSG     = "room_msg"       # Message scoped to a private room

SYSTEM_MSG   = "sys"            # Server → client informational / error note

# --- Packet helpers --------------------------------------------------------

def make_packet(ptype: str, **payload) -> bytes:
    """Serialize a python dict ⟶ JSON ⟶ UTF‑8 bytes suitable for socket.sendto().

    Args:
        ptype: symbolic packet‑type string, must be one of the constants above.
        **payload: arbitrary key/value data (MUST be JSON‑serialisable).
    """
    payload["type"] = ptype                 # Inject discriminator field
    return json.dumps(payload).encode()      # str ⟶ bytes


def parse_packet(data: bytes) -> Dict:
    """Inverse of :func:`make_packet` – bytes ⟶ dict."""
    return json.loads(data.decode())         # bytes ⟶ str ⟶ dict

# --- Metadata container ----------------------------------------------------

@dataclass(slots=True)
class ClientInfo:
    """Lightweight record for connected clients (stored on server side only)."""

    addr: Tuple[str, int]   # Client's UDP (ip, port)  e.g. ("192.0.2.10", 64233)
    name: str               # Human‑readable nickname supplied at JOIN

# ======================================================================
#  udpchat/util.py
# ======================================================================
#!/usr/bin/env python3
"""Logging utils **and** helper that discovers our outward‑facing IP address."""

from __future__ import annotations
import logging                           # Python stdlib logging framework
import socket                            # Needed for IP detection
import sys                               # For stderr/stdout handles
from logging.handlers import RotatingFileHandler

__all__ = ["LOG", "configure_logging", "get_local_ip"]

# ----------------------------------------------------------------------
# configure_logging() builds a ready‑to‑use Logger with both console + file
# output.  We call it *once* (module import time) and keep the singleton in LOG.
# ----------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    """Return a logger named "udpchat" with sane defaults (INFO level)."""

    logger = logging.getLogger("udpchat")   # Create / fetch named logger
    logger.setLevel(logging.INFO)           # Verbose enough for diagnostics

    # ----- Console handler (stdout) -----
    sh = logging.StreamHandler(sys.stdout)  # Emit human output in foreground

    # ----- Rotating file handler -----
    # Rotates once file hits ±1 MiB, keeps 3 backups ⇒ log ≲ 4 MiB on disk.
    fh = RotatingFileHandler(
        "udp_chat.log",
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )

    # Unified log line format.  Example: [23:59:59] INFO     User joined
    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%H:%M:%S")
    sh.setFormatter(fmt)
    fh.setFormatter(fmt)

    # Register both handlers once only.
    logger.addHandler(sh)
    logger.addHandler(fh)

    return logger

# Instantiate global logger so that *importers* can simply do:
#     from udpchat.util import LOG
LOG = configure_logging()

# ----------------------------------------------------------------------
# best‑effort outward IP discovery (no external calls, works offline)
# ----------------------------------------------------------------------

def get_local_ip() -> str:
    """Return the host's primary IP, fallback to 127.0.0.1 on failure."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP socket ≠ connect
    try:
        # connect() with UDP doesn't actually send packets until sendto(); that's
        # good: we just want to force the OS to select a source IP for that dest.
        sock.connect(("8.8.8.8", 80))          # Google DNS (never contacted)
        return sock.getsockname()[0]            # (<chosen‑ip>, <port>) tuple
    except OSError:
        return "127.0.0.1"                      # Either offline or no NIC
    finally:
        sock.close()                            # Always release resources

# ======================================================================
#  udpchat/client.py (heavily commented)
# ======================================================================
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

    def start(self) -> None:
        self.name = input("Your name: ").strip() or f"Gueset{random.randint(1000, 9999)}"
        LOG.info("Welcome, %s", self.name)
        self._send(make_packet(JOIN, name=self.name))

        threading.Thread(target=self._recv_loop, daemon=True).start()

        try:
            while self.running.is_set():
                try:
                    line = input(self._prompt())
                except EOFError:
                    break

                if self.current_room and line.strip().lower() in {"exit", "end"}:
                    self.current_room = None
                    continue

                if line.lower() in {"/quir", "qqq"}:
                    self._send(make_packet(QUIT, name=self.name))
                    break

                if line.startswith("/"):
                    self._handle_command(line)
                    continue

                if self.current_room:
                    self._send(make_packet(ROOM_MSG, room=self.current_room, **{"from": self.name}, text=line))
                    continue

                self._send(make_packet(PUBLIC_MSG, name=self.name, text=line))
        except KeyboardInterrupt:
            pass
        finally:
            self.running.clear()
            self.sock.close()
            LOG.info("Discounnected")

        
    def _send(self, pkt: bytes) -> None:
        try:
            self.sock.sendto(pkt, self.server)
        except OSError as exc:
            LOG.error ("Send failed: %s", exc)
            self.running.clear()


    def _recv_loop(self) -> None:
        """Background thread – prints inbound packets then redraws prompt."""
        while self.running.is_set():
            try:
                data, _ = self.sock.recvfrom(BUF_SIZE)     # Blocking recv
                pkt = parse_packet(data)                   # bytes ⟶ dict

                if not self._validate_packet(pkt):
                    LOG.warning("Received malformed packet: %s", pkt)
                    continue

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
            print()
            sys.stdout.write(self._prompt())
            sys.stdout.flush()

    def _handle_command(self, line: str) -> None:
        try:
            cmd, *args = shlex.split(line)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            return
        
        match cmd.lower():
            case "/create":
                if len(args) != 1:
                    print("Usage: /Create <room>")
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
                self._send(make_packet(INVITE, room=room, **{"from": self.name}, to=user))

            case "/accept":
                if len(args) != 1:
                    print("Using: /accept <room>")
                    return
                room = args[0]
                if room not in self.pending_inv:
                    print(f"No pending invite for '{room}'")
                    return
                



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

    def start(self) -> None:
        LOG.info("Server listening on %s:%d", self.host, self.port)
        threading.Thread(target=self._recv_loop, daemon=True).start()
        try:
            self._process_loop()
        except KeyboardInterrupt:
            LOG.info("Shutdown requested")
        finally:
            self.running.clear()
            self.sock.close()

    def _recv_loop(self) -> None:
        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(BUF_SIZE)
                self.recv_q.put((data, addr))
            except OSError:
                break

    def _send(self, pkt: bytes, addr: Tuple[str, int]) -> None:
        try:
            self.sock.sendto(pkt, addr)
        except OSError:
            self._disconnect(addr)

    def _broadcast(self, pkt: bytes, exclude: Tuple[str, int] | None = None) -> None:
        for a in list(self.clients):
            if a != exclude:
                self._send(pkt, a)
            
    def _disconnect(self, addr: Tuple[str, int]) -> None:
        Client = self.clients.pop(addr, None)
        if not Client:
            return
        
