# server_config.py

"""
This module contains configuration settings for the P2P server.
"""
import logging

# Logging configuration
class RedFormatter(logging.Formatter):
    RED = "\033[91m"
    RESET = "\033[0m"

    def format(self, record):
        if record.levelno == logging.ERROR:
            record.msg = f"{self.RED}{record.msg}{self.RESET}"
        return super().format(record)

formatter = RedFormatter(
    fmt="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(handler)

# Default port for P2P server
DEFAULT_P2P_PORT = 9828

# WebSocket server port
WEBSOCKET_PORT = 9000

# HTTP server port
HTTP_API_PORT = 8081

# Bootstrap addresses for P2P network
BOOTSTRAP_ADDRESSES = [
    "192.168.86.109:9828",
    "192.168.86.30:9828",
    "34.35.78.201:9828",
]

# Database file for storing spammer data
DATABASE_FILE = "spammers.db"
