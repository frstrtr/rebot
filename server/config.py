# config.py

"""
This module contains configuration settings for the P2P server.
"""

import logging

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
LOGGER = logging.getLogger(__name__)

# Default port for P2P server
DEFAULT_P2P_PORT = 9828

# WebSocket server port
WEBSOCKET_PORT = 9000

# HTTP server port
HTTP_PORT = 8081

# Bootstrap addresses for P2P network
BOOTSTRAP_ADDRESSES = [
    "172.19.113.234:9002",
    "172.19.112.1:9001",
    "192.168.86.109:9828",
]

# Database file for storing spammer data
DATABASE_FILE = "spammers.db"