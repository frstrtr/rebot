"""Address module for handling peer addresses in a P2P network"""

# -*- coding: utf-8 -*-
# server/p2p/address.py
# SPDX-License-Identifier: MIT

import uuid
from twisted.internet.address import IPv4Address


class PeerAddress(IPv4Address):
    """Custom class that extends IPv4Address and includes a UUID property"""

    def __init__(self, addr_type, host, port, node_uuid=None):
        super().__init__(addr_type, host, port)
        self.node_uuid = node_uuid or str(uuid.uuid4())
