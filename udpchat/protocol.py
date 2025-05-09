#!/usr/bin/env python3
"""
Shared constants, packet helper functions, and a dataclass used to
store client-related information on the server.
"""

from __future__ import annotations  # Enables postponed evaluation of annotations (Python 3.7+ feature)
import json
from dataclasses import dataclass
from typing import Dict, Tuple

# --- Network Configuration Constants
BUF_SIZE: int = 1024         # Default buffer size for socket communication (in bytes)
DEFAULT_PORT: int = 5000     # Default port number used by the server

# --- Packet Type Identifiers
JOIN = "join"                # Indicates a user is joining the lobby
PUBLIC_MSG = "msg"           # Public message sent within the lobby
QUIT = "quit"                # Indicates a user is disconnecting or exiting

CREATE_ROOM = "create_room"  # Request to create a new private room
INVITE = "invite"            # Invitation sent to a user to join a room
ACCEPT_INV = "accept_invite" # Acceptance of an invitation to join a room
ROOM_MSG = "room_msg"        # Message sent within a private room

SYSTEM_MSG = "sys"           # System-level or error message

# --- Helper Functions for Packet Handling

def make_packet(ptype: str, **payload) -> bytes:
    """
    Constructs a JSON-encoded packet as bytes, embedding the specified packet type.

    Args:
        ptype (str): Type identifier of the packet (e.g., 'join', 'msg').
        **payload: Arbitrary keyword arguments to include in the packet.

    Returns:
        bytes: JSON-encoded representation of the packet, ready for transmission.
    """
    payload["type"] = ptype  # Injects the packet type into the payload
    return json.dumps(payload).encode()  # Serializes to JSON and encodes as bytes

def parse_packet(data: bytes) -> Dict:
    """
    Decodes a received JSON packet (as bytes) back into a Python dictionary.

    Args:
        data (bytes): Incoming packet data.

    Returns:
        Dict: Deserialized Python dictionary representing the packet.
    """
    return json.loads(data.decode())  # Decode bytes to str, then parse JSON

# --- Data Structure for Client Metadata

@dataclass(slots=True)
class ClientInfo:
    """
    Holds metadata about a connected client.

    Attributes:
        addr (Tuple[str, int]): IP address and port tuple of the client.
        name (str): The username or identifier of the client.
    """
    addr: Tuple[str, int]  # Network address (IP, port)
    name: str              # Client's chosen name
