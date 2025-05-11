import logging
import socket
import sys
from colorama import Fore, Style
from logging.handlers import RotatingFileHandler

__all__ = ["LOG", "configure_logging", "get_local_ip"]

# ----------------------------------------------------------------------
# ColorFormatter: Adds color to log levels in console output
# ----------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    def format(self, record):
        # Standard format: timestamp, level, module:function:line, message
        base_format = "[%(asctime)s] %(levelname)-8s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
        formatter = logging.Formatter(base_format, "%H:%M:%S")
        message = formatter.format(record)

        # Color based on log level
        if record.levelno >= logging.ERROR:
            return Fore.RED + message + Style.RESET_ALL
        elif record.levelno == logging.WARNING:
            return Fore.YELLOW + message + Style.RESET_ALL
        return message

# ----------------------------------------------------------------------
# configure_logging: Initializes logger with both console and rotating file output
# ----------------------------------------------------------------------
def configure_logging() -> logging.Logger:
    """Return a logger named "udpchat" with standardized format and color output."""

    logger = logging.getLogger("udpchat")
    logger.setLevel(logging.INFO)

    # ----- Console handler (colored) -----
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(ColorFormatter())

    # ----- Rotating file handler (plain format) -----
    fh = RotatingFileHandler(
        "udp_chat.log",
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )
    file_fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s [%(name)s.%(funcName)s:%(lineno)d] %(message)s", "%H:%M:%S")
    fh.setFormatter(file_fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)

    return logger

# ----------------------------------------------------------------------
# Global logger instance available throughout the application
# ----------------------------------------------------------------------
LOG = configure_logging()

# ----------------------------------------------------------------------
# get_local_ip: Best-effort method to determine the outward-facing IP address
# ----------------------------------------------------------------------
def get_local_ip() -> str:
    """Return the host's primary IP, fallback to 127.0.0.1 on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()