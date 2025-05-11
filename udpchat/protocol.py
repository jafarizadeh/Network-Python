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