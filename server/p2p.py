"""
This module implements a peer-to-peer (P2P) protocol for handling connections and exchanging spammer information.
It uses the Twisted framework for networking and includes functionalities for managing peers, broadcasting spammer data,
and synchronizing data with newly connected peers.

Classes:
    P2PProtocol: Handles P2P connections, data reception, and peer information exchange.
    P2PFactory: Manages P2P connections, broadcasts spammer information, and synchronizes data with peers.

Functions:
    find_available_port(start_port): Finds an available port starting from the given port.
    check_p2p_data(user_id): Placeholder function to check for P2P data.
"""

import json
import uuid

from twisted.internet import endpoints, defer, error, protocol, reactor
from twisted.internet.address import IPv4Address
from database import (
    store_spammer_data,
    retrieve_spammer_data_from_db,
    get_all_spammer_ids,
)
from server_config import LOGGER


class PeerAddress(IPv4Address):
    """Custom class that extends IPv4Address and includes a UUID property"""

    def __init__(self, addr_type, host, port, node_uuid=None):
        if node_uuid is None:
            node_uuid = str(uuid.uuid4())
        super().__init__(addr_type, host, port)
        self.node_uuid = node_uuid


class P2PProtocol(protocol.Protocol):
    """P2P protocol to handle connections and exchange spammer information."""

    def connectionMade(self):
        """Handle new P2P connections."""
        peer = self.getPeer()
        self.factory.peers.append(peer)
        LOGGER.info("P2P connection made with %s:%d", peer.host, peer.port)
        LOGGER.info("P2P connection details: %s", peer)
        self.send_peer_info()

    def getPeer(self):
        """Override getPeer to return PeerAddress with UUID."""
        peer = self.transport.getPeer()
        return PeerAddress(peer.type, peer.host, peer.port, self.factory.uuid)

    def dataReceived(self, data):
        """Handle received P2P data."""
        message = data.decode("utf-8")
        peer = self.getPeer()
        LOGGER.debug(
            "P2P message received from %s:%d: %s", peer.host, peer.port, message
        )

        try:
            # Split the message by '}{' and add the braces back
            json_strings = self.split_json_objects(message)

            for json_string in json_strings:
                try:
                    data = json.loads(json_string)
                    data = self.decode_nested_json(data)
                    # Log the decoded message in a human-readable format
                    LOGGER.debug("Decoded message: %s", data)
                    if "user_id" in data:
                        user_id = data["user_id"]
                        lols_bot_data = data.get("lols_bot_data", {})
                        if isinstance(lols_bot_data, str):
                            lols_bot_data = json.loads(lols_bot_data)
                        cas_chat_data = data.get("cas_chat_data", {})
                        if isinstance(cas_chat_data, str):
                            cas_chat_data = json.loads(cas_chat_data)
                        p2p_data = data.get("p2p_data", {})
                        if isinstance(p2p_data, str):
                            p2p_data = json.loads(p2p_data)
                        if (
                            p2p_data
                            and isinstance(p2p_data, dict)
                            and len(p2p_data) > 0
                        ):
                            store_spammer_data(
                                user_id, lols_bot_data, cas_chat_data, p2p_data
                            )
                            self.factory.broadcast_spammer_info(user_id)
                        else:
                            # Store the spammer data even if p2p_data is empty
                            store_spammer_data(
                                user_id, lols_bot_data, cas_chat_data, p2p_data
                            )
                    elif "peers" in data:
                        self.factory.update_peer_list(data["peers"])
                    elif "uuid" in data:
                        self.factory.handle_peer_uuid(self, data["uuid"])
                except json.JSONDecodeError as e:
                    LOGGER.error("Failed to decode JSON object: %s", e)
        except json.JSONDecodeError as e:
            LOGGER.error("Failed to decode JSON: %s", e)

    def split_json_objects(self, message):
        """Split concatenated JSON objects in the message."""
        json_strings = []
        depth = 0
        start = 0
        for i, char in enumerate(message):
            if char == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    json_strings.append(message[start : i + 1])
        return json_strings

    def decode_nested_json(self, data):
        """Decode nested JSON strings in the data."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    try:
                        decoded_value = json.loads(value)
                        data[key] = self.decode_nested_json(decoded_value)
                    except json.JSONDecodeError:
                        data[key] = (
                            value.encode().decode("unicode_escape").replace("\\", "")
                        )
                elif isinstance(value, dict):
                    data[key] = self.decode_nested_json(value)
                elif isinstance(value, list):
                    data[key] = [self.decode_nested_json(item) for item in value]
        elif isinstance(data, list):
            return [self.decode_nested_json(item) for item in data]
        elif isinstance(data, str):
            try:
                decoded_value = json.loads(data)
                return self.decode_nested_json(decoded_value)
            except json.JSONDecodeError:
                return data.encode().decode("unicode_escape").replace("\\", "")
        return data

    def connectionLost(self, reason=protocol.connectionDone):
        """Handle lost P2P connections."""
        peer = self.getPeer()
        self.factory.peers = [
            p for p in self.factory.peers if p.host != peer.host or p.port != peer.port
        ]
        LOGGER.info("P2P connection lost: %s", reason)

    def send_peer_info(self):
        """Send the list of known peers to the connected peer."""
        peer_info = [
            {
                "host": peer.host,
                "port": peer.port,
                "uuid": peer.node_uuid,
            }
            for peer in self.factory.peers
        ]
        message = json.dumps({"peers": peer_info, "uuid": self.factory.uuid})
        self.transport.write(message.encode("utf-8"))
        LOGGER.info("Sent peer info: %s", message)


class P2PFactory(protocol.Factory):
    """Factory to manage P2P connections."""

    protocol = P2PProtocol

    def __init__(self, uuid=None):
        self.peers = []
        self.uuid = uuid or str(uuid.uuid4())
        self.bootstrap_peers = []

    def broadcast_spammer_info(self, user_id):
        """Broadcast spammer information to all connected peers."""
        spammer_data = retrieve_spammer_data_from_db(user_id)
        if spammer_data:
            # Ensure nested JSON data is properly encoded
            message = json.dumps(
                {
                    "user_id": user_id,
                    "lols_bot_data": spammer_data["lols_bot_data"],
                    "cas_chat_data": spammer_data["cas_chat_data"],
                    "p2p_data": spammer_data["p2p_data"],
                }
            )
            for peer in self.peers:
                peer.transport.write(message.encode("utf-8"))
            LOGGER.info("Broadcasted spammer info: %s", message)
        else:
            LOGGER.warning("No spammer data found for user_id: %s", user_id)

    def connect_to_bootstrap_peers(self, bootstrap_addresses):
        """Connect to bootstrap peers and gather available peers."""
        deferreds = []
        for address in bootstrap_addresses:
            host, port = address.split(":")
            port = int(port)
            LOGGER.debug("Attempting to connect to bootstrap peer %s:%d", host, port)
            endpoint = endpoints.TCP4ClientEndpoint(reactor, host, port)
            deferred = endpoint.connect(self)
            deferred.addCallback(self.on_bootstrap_peer_connected)
            deferred.addErrback(self.on_bootstrap_peer_failed, address)
            deferreds.append(deferred)
        return defer.gatherResults(deferreds)

    def on_bootstrap_peer_connected(self, peer_protocol):
        """Handle successful connection to a bootstrap peer."""
        peer = peer_protocol.transport.getPeer()
        peer_address = PeerAddress(peer.type, peer.host, peer.port, self.uuid)
        LOGGER.info("Connected to bootstrap peer %s:%d", peer.host, peer.port)
        self.bootstrap_peers.append(peer_address)
        # Wait for the UUID to be received in dataReceived
        peer_protocol.transport.write(json.dumps({"uuid": self.uuid}).encode("utf-8"))

    def handle_peer_uuid(self, peer_protocol, peer_uuid):
        """Handle the received UUID from a peer."""
        peer = peer_protocol.transport.getPeer()
        if peer_uuid == self.uuid:
            LOGGER.info(
                "Disconnecting peer with same UUID %s:%d (UUID: %s)",
                peer.host,
                peer.port,
                peer_uuid,
            )
            peer_protocol.transport.loseConnection()
            return
        LOGGER.info("Received UUID %s from peer %s:%d", peer_uuid, peer.host, peer.port)
        self.synchronize_spammer_data(peer_protocol)

    def on_bootstrap_peer_failed(self, failure, address):
        """Handle failed connection to a bootstrap peer."""
        LOGGER.error("Failed to connect to bootstrap peer %s: %s", address, failure)

    def update_peer_list(self, peers):
        """Update the list of known peers."""
        for peer in peers:
            host = peer["host"]
            port = peer["port"]
            peer_uuid = peer.get("uuid")
            if peer_uuid == self.uuid:
                LOGGER.info(
                    "Skipping self connection to %s:%d (UUID: %s)",
                    host,
                    port,
                    peer_uuid,
                )
                continue
            if not any(p.host == host and p.port == port for p in self.peers):
                endpoint = endpoints.TCP4ClientEndpoint(reactor, host, port)
                endpoint.connect(self).addCallback(
                    lambda _, h=host, p=port: LOGGER.info(
                        "Connected to new peer %s:%d", h, p
                    )
                ).addErrback(
                    lambda err, h=host, p=port: LOGGER.error(
                        "Failed to connect to new peer %s:%d: %s", h, p, err
                    )
                )
                LOGGER.info("Connecting to new peer %s:%d", host, port)

    def synchronize_spammer_data(self, sync_protocol):
        """Synchronize spammer data with a newly connected peer."""
        for user_id in self.get_all_spammer_ids():
            spammer_data = retrieve_spammer_data_from_db(user_id)
            if spammer_data:
                message = json.dumps(
                    {
                        "user_id": user_id,
                        "lols_bot_data": spammer_data["lols_bot_data"],
                        "cas_chat_data": spammer_data["cas_chat_data"],
                        "p2p_data": spammer_data["p2p_data"],
                    }
                )
                sync_protocol.transport.write(message.encode("utf-8"))
                LOGGER.info("Synchronized spammer data for user_id: %s", user_id)

    def get_all_spammer_ids(self):
        """Retrieve all spammer IDs from the database."""
        return get_all_spammer_ids()


def find_available_port(start_port):
    """Find an available port starting from the given port."""
    port = start_port
    while True:
        try:
            endpoint = endpoints.TCP4ServerEndpoint(reactor, port)
            endpoint.listen(protocol.Factory())
            return port
        except error.CannotListenError:
            port += 1


def check_p2p_data(user_id):
    """Placeholder function to check for P2P data."""
    _reply_ = {
        "ok": True,
        "user_id": user_id,
    }
    LOGGER.info("Check p2p data reply: %s", _reply_)
    # dumb response None fro tests
    return None
