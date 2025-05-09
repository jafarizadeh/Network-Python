"""UDP Chat – a minimal UDP‑based chat library.

Importing this package gives access to :class:`udpchat.UDPChatServer` and
:class:`udpchat.UDPChatClient` so the whole stack can be embedded in another
application or started via ``python -m``.
"""

from .client import UDPChatClient  # noqa: F401  (re‑export)
from .server import UDPChatServer  # noqa: F401

__all__ = ["UDPChatClient", "UDPChatServer"]