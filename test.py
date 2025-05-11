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
        self.name = input("Your name: ").strip() or f"Guest{random.randint(1000, 9999)}"
        LOG.info("Welcome, %s", self.name)
        