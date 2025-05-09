"""Utility helpers – logging configuration & network helpers."""

from __future__ import annotations

import logging
import socket
import sys
from logging.handlers import RotatingFileHandler

__all__ = [
    "LOG",
    "configure_logging",
    "get_local_ip",
]


def configure_logging() -> logging.Logger:
    """Configure a logger that logs to console **and** rotating file."""

    logger = logging.getLogger("udpchat")
    logger.setLevel(logging.INFO)

    # --- Console handler -------------------------------------------------
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    # --- File handler with rotation -------------------------------------
    fh = RotatingFileHandler(
        "udp_chat.log", maxBytes=1_048_576, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)

    # --- Common format ---------------------------------------------------
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%H:%M:%S"
    )
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


LOG: logging.Logger = configure_logging()


def get_local_ip() -> str:
    """Return best‑guess LAN IP (falls back to ``127.0.0.1``)."""

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
