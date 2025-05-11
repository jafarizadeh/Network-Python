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
