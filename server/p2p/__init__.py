"""P2P module."""

import os
import sys

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from server.p2p.config import *
from server.p2p.address import PeerAddress
from server.p2p.protocol import P2PProtocol
from server.p2p.factory import P2PFactory
from server.p2p.utils import split_json_objects, decode_nested_json, find_available_port

__all__ = [
    "RED_COLOR",
    "YELLOW_COLOR",
    "GREEN_COLOR",
    "PURPLE_COLOR",
    "INVERSE_COLOR",
    "RESET_COLOR",
    "HANDSHAKE_INIT",
    "HANDSHAKE_RESPONSE",
    "PeerAddress",
    "P2PProtocol",
    "P2PFactory",
    "split_json_objects",
    "decode_nested_json",
    "find_available_port",
]
