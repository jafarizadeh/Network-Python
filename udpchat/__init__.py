"""UDP Chat – a minimal UDP-based chat library.

Importing this package exposes :class:`udpchat.UDPChatServer` and
:class:`udpchat.UDPChatClient`, allowing the whole stack to be embedded in
another application or launched via ``python -m udpchat``.
"""

# ------------------------ re-exports ------------------------
# Importing here makes `from udpchat import UDPChatClient` possible without
# digging into sub-modules.
from .client import UDPChatClient   # noqa: F401  ── re-export client class
from .server import UDPChatServer   # noqa: F401  ── re-export server class

# ------------------------ public API ------------------------
# __all__ tells linters / wildcard importers which names are considered the
# library's official surface.
__all__: list[str] = [
    "UDPChatClient",  # Chat client (lobby + private rooms)
    "UDPChatServer",  # Matching UDP server implementation
]