"""Message protocol, shared constants & data‑classes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Tuple

BUF_SIZE: int = 1024
DEFAULT_PORT: int = 5000


def make_packet(ptype: str, **payload) -> bytes:
    """Serialize a packet to bytes.

    Each packet is JSON with at minimum a ``type`` field. Additional
    keyword arguments are included as payload attributes.
    """
    payload["type"] = ptype
    return json.dumps(payload).encode()


def parse_packet(data: bytes) -> Dict:
    """Deserialize raw UDP bytes into a Python ``dict``."""
    return json.loads(data.decode())


@dataclass(slots=True)
class ClientInfo:
    """Minimal information we track for each connected client."""

    addr: Tuple[str, int]
    name: str
