# server_config.py

"""
This module contains configuration settings for the P2P server.
"""

import logging

# Logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger(__name__)

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
