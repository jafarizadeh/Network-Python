#!/usr/bin/env python3
"""
Logging configuration and a utility function to determine the local IP address.
"""

from __future__ import annotations  # Allows forward references in type annotations
import logging
import socket
import sys
from logging.handlers import RotatingFileHandler

# Public API of this module
__all__ = ["LOG", "configure_logging", "get_local_ip"]

def configure_logging() -> logging.Logger:
    """
    Configures a logger named 'udpchat' with both console and file handlers.
    The file handler uses log rotation to manage log file size.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger("udpchat")
    logger.setLevel(logging.INFO)  # Set logging level to INFO

    # Console output handler
    sh = logging.StreamHandler(sys.stdout)

    # Rotating file handler (1MB max per file, keep 3 backups)
    fh = RotatingFileHandler(
        "udp_chat.log",
        maxBytes=1_048_576,     # 1 MB
        backupCount=3,          # Keep last 3 log files
        encoding="utf-8"
    )

    # Define a consistent log format for both handlers
    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", "%H:%M:%S")
    sh.setFormatter(fmt)
    fh.setFormatter(fmt)

    # Attach both handlers to the logger
    logger.addHandler(sh)
    logger.addHandler(fh)

    return logger

# Global logger instance used throughout the application
LOG = configure_logging()

def get_local_ip() -> str:
    """
    Attempts to determine the local IP address of the host.
    Falls back to '127.0.0.1' if unable to detect.

    Returns:
        str: Best-effort local IP address.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Use a dummy connection to a public DNS server to determine the local IP
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]  # Extract local IP from socket
    except OSError:
        return "127.0.0.1"  # Fallback to localhost
    finally:
        s.close()  # Ensure socket is always closed
