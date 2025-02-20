"""p2p Module"""

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

# Define ANSI escape codes for terminal colors
RED_COLOR = "\033[91m"
YELLOW_COLOR = "\033[93m"
GREEN_COLOR = "\033[92m"
PURPLE_COLOR = "\033[95m"
INVERSE_COLOR = "\033[7m"
RESET_COLOR = "\033[0m"

HANDSHAKE_INIT = "handshake_init"
HANDSHAKE_RESPONSE = "handshake_response"


class PeerAddress(IPv4Address):
    """Custom class that extends IPv4Address and includes a UUID property"""

    def __init__(self, addr_type, host, port, node_uuid=None):
        super().__init__(addr_type, host, port)
        self.node_uuid = node_uuid or str(uuid.uuid4())


class P2PProtocol(protocol.Protocol):
    """P2P protocol to handle connections and exchange spammer information."""

    def connectionMade(self):
        """Handle new P2P connections."""
        peer = self.get_peer()
        self.factory.peers.append(peer)
        LOGGER.info(
            "%sP2P connection made with %s:%d%s",
            YELLOW_COLOR,
            peer.host,
            peer.port,
            RESET_COLOR,
        )
        LOGGER.info("%sP2P connection details: %s%s", YELLOW_COLOR, peer, RESET_COLOR)
        self.send_handshake_init()

    def get_peer(self):
        """Override getPeer to return PeerAddress with UUID."""
        peer = self.transport.getPeer()
        return PeerAddress(peer.type, peer.host, peer.port, self.factory.node_uuid)

    def send_handshake_init(self):
        """Send handshake initiation message."""
        message = json.dumps({"type": HANDSHAKE_INIT, "uuid": self.factory.node_uuid})
        self.transport.write(message.encode("utf-8"))
        LOGGER.info("Sent handshake initiation: %s", message)

    def send_handshake_response(self, node_uuid):
        """Send handshake response message."""
        message = json.dumps({"type": HANDSHAKE_RESPONSE, "uuid": node_uuid})
        self.transport.write(message.encode("utf-8"))
        LOGGER.info("Sent handshake response: %s", message)

    def dataReceived(self, data):
        """Handle received P2P data."""
        message = data.decode("utf-8")
        peer = self.get_peer()
        LOGGER.debug(
            "P2P message received from %s:%d: %s", peer.host, peer.port, message
        )

        # Split the message by '}{' and add the braces back
        json_strings = self.split_json_objects(message)

        for json_string in json_strings:
            try:
                data = json.loads(json_string)
                if "type" not in data:
                    self.handle_p2p_data(data)
                    continue

                if data["type"] == HANDSHAKE_INIT:
                    self.handle_handshake_init(data)
                elif data["type"] == HANDSHAKE_RESPONSE:
                    self.handle_handshake_response(data)
                elif data["type"] == "check_p2p_data":
                    self.handle_check_p2p_data(data)
                elif data["type"] == "check_p2p_data_response":
                    self.handle_check_p2p_data_response(data)
                else:
                    self.handle_p2p_data(data)

            except json.JSONDecodeError as e:
                LOGGER.error("Failed to decode JSON: %s", e)

    def handle_handshake_init(self, data):
        """Handle handshake initiation message."""
        peer_uuid = data["uuid"]
        peer = self.get_peer()
        peer.node_uuid = peer_uuid
        LOGGER.info(
            "%sReceived handshake initiation from %s:%d (UUID: %s)%s",
            GREEN_COLOR,
            peer.host,
            peer.port,
            peer.node_uuid,
            RESET_COLOR,
        )
        if peer.node_uuid == self.factory.node_uuid:
            LOGGER.info(
                "%sDisconnecting self-connection to %s:%d (UUID: %s)%s",
                RED_COLOR,
                peer.host,
                peer.port,
                peer.node_uuid,
                RESET_COLOR,
            )
            self.transport.loseConnection()
        else:
            self.send_handshake_response(self.factory.node_uuid)

    def handle_handshake_response(self, data):
        """Handle handshake response message."""
        peer_uuid = data["uuid"]
        peer = self.get_peer()
        peer.node_uuid = peer_uuid
        LOGGER.info(
            "%sReceived handshake response from %s:%d (UUID: %s)%s",
            GREEN_COLOR,
            peer.host,
            peer.port,
            peer.node_uuid,
            RESET_COLOR,
        )
        if peer.node_uuid == self.factory.node_uuid:
            LOGGER.info(
                "%sDisconnecting self-connection to %s:%d (UUID: %s)%s",
                RED_COLOR,
                peer.host,
                peer.port,
                peer.node_uuid,
                RESET_COLOR,
            )
            self.transport.loseConnection()

    def handle_check_p2p_data(self, data):
        """Handle check_p2p_data request and respond with data if available."""
        user_id = data["user_id"]
        LOGGER.info("%s Received check_p2p_data request", user_id)
        spammer_data = retrieve_spammer_data_from_db(user_id)
        if spammer_data:
            # If p2p_data is not available, construct it from other data
            if not spammer_data.get("p2p_data"):
                spammer_data["p2p_data"] = {
                    "lols_bot_data": spammer_data["lols_bot_data"],
                    "cas_chat_data": spammer_data["cas_chat_data"],
                }
            response = {
                "type": "check_p2p_data_response",
                "user_id": user_id,
                "lols_bot_data": spammer_data["lols_bot_data"],
                "cas_chat_data": spammer_data["cas_chat_data"],
                "p2p_data": spammer_data["p2p_data"],
            }
            self.transport.write(json.dumps(response).encode("utf-8"))
            LOGGER.info("%s sent check_p2p_data response: %s", user_id, response)
        else:
            response = {
                "type": "check_p2p_data_response",
                "user_id": user_id,
                "error": "No spammer data found",
            }
            self.transport.write(json.dumps(response).encode("utf-8"))
            LOGGER.info(
                "%s No spammer data found, sent response: %s", user_id, response
            )

    def handle_check_p2p_data_response(self, data):
        """Handle check_p2p_data_response and resolve the deferred."""
        user_id = data["user_id"]
        LOGGER.info("%s Received check_p2p_data_response", user_id)
        for proto in self.factory.protocol_instances:
            if proto.transport.getPeer() == self.transport.getPeer():
                if hasattr(proto, "deferred"):
                    if "error" in data:
                        proto.deferred.callback(None)
                    else:
                        proto.deferred.callback(json.dumps(data))
                    del proto.deferred

    def handle_p2p_data(self, data):
        """Handle received P2P data."""
        peer = self.get_peer()
        LOGGER.debug("Handling P2P data from %s:%d", peer.host, peer.port)
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
            if p2p_data and isinstance(p2p_data, dict) and len(p2p_data) > 0:
                store_spammer_data(user_id, lols_bot_data, cas_chat_data, p2p_data)
                self.factory.broadcast_spammer_info(user_id)
            else:
                # Store the spammer data even if p2p_data is empty
                store_spammer_data(user_id, lols_bot_data, cas_chat_data, p2p_data)
        elif "peers" in data:
            self.factory.update_peer_list(data["peers"])

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
        peer = self.get_peer()
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
        message = json.dumps({"peers": peer_info, "uuid": self.factory.node_uuid})
        self.transport.write(message.encode("utf-8"))
        LOGGER.info("Sent peer info: %s", message)


class P2PFactory(protocol.Factory):
    """Factory to manage P2P connections."""

    protocol = P2PProtocol

    def __init__(self, node_uuid=None):
        self.peers = []
        self.node_uuid = node_uuid or str(uuid.uuid4())
        self.bootstrap_peers = []
        self.protocol_instances = []

    def buildProtocol(self, addr):
        """Build and return a protocol instance."""
        proto = self.protocol()
        proto.factory = self
        self.protocol_instances.append(proto)
        return proto

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
            for proto in self.protocol_instances:
                proto.transport.write(message.encode("utf-8"))
            LOGGER.info("Broadcasted spammer info: %s", message)
        else:
            LOGGER.warning("No spammer data found for user_id in local DB: %s", user_id)
            # TODO check other spam nodes and endpoints

    def connect_to_bootstrap_peers(self, bootstrap_addresses):
        """Connect to bootstrap peers and gather available peers."""
        deferreds = []
        for address in bootstrap_addresses:
            host, port = address.split(":")
            port = int(port)
            LOGGER.debug(
                "%sAttempting to connect to bootstrap peer %s:%d%s",
                PURPLE_COLOR,
                host,
                port,
                RESET_COLOR,
            )
            endpoint = endpoints.TCP4ClientEndpoint(reactor, host, port)
            deferred = endpoint.connect(self)
            deferred.addCallback(self.on_bootstrap_peer_connected)
            deferred.addErrback(self.on_bootstrap_peer_failed, address)
            deferreds.append(deferred)
        return defer.gatherResults(deferreds)

    def on_bootstrap_peer_connected(self, peer_protocol):
        """Handle successful connection to a bootstrap peer."""
        peer = peer_protocol.get_peer()
        peer_address = PeerAddress(peer.type, peer.host, peer.port, peer.node_uuid)
        LOGGER.info(
            "%sConnected to bootstrap peer %s:%d%s",
            GREEN_COLOR,
            peer.host,
            peer.port,
            RESET_COLOR,
        )
        self.bootstrap_peers.append(peer_address)
        # Send local UUID to the bootstrap node
        peer_protocol.send_handshake_init()

    def handle_peer_uuid(self, peer_protocol, peer_uuid):
        """Handle the received UUID from a peer."""
        peer = peer_protocol.get_peer()
        if peer_uuid == self.node_uuid:
            LOGGER.info(
                "\033[93mDisconnecting peer with same UUID %s:%d (UUID: %s)\033[0m",
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
        LOGGER.error(
            "%sFailed to connect to bootstrap peer %s: %s%s",
            RED_COLOR,
            address,
            failure,
            RESET_COLOR,
        )

    def update_peer_list(self, peers):
        """Update the list of known peers."""
        for peer in peers:
            host = peer["host"]
            port = peer["port"]
            peer_uuid = peer.get("uuid")
            if peer_uuid == self.node_uuid:
                LOGGER.info(
                    "%sSkipping self connection to %s:%d (UUID: %s)%s",
                    YELLOW_COLOR,
                    host,
                    port,
                    peer_uuid,
                    RESET_COLOR,
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
                        "%sFailed to connect to new peer %s:%d: %s%s",
                        RED_COLOR,
                        h,
                        p,
                        err,
                        RESET_COLOR,
                    )
                )
                LOGGER.info(
                    "%sConnecting to new peer %s:%d%s",
                    YELLOW_COLOR,
                    host,
                    port,
                    RESET_COLOR,
                )

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

    def check_p2p_data(self, user_id):
        """Check for P2P data across all connected peers."""
        LOGGER.info("Checking peers for user_id: %s", user_id)
        deferreds = []
        for proto in self.protocol_instances:
            deferred = defer.Deferred()
            proto.transport.write(
                json.dumps({"type": "check_p2p_data", "user_id": user_id}).encode(
                    "utf-8"
                )
            )
            peer = proto.get_peer()
            LOGGER.debug(
                "%s Sent check_p2p_data request to peer %s:%d",
                user_id,
                peer.host,
                peer.port,
            )
            proto.deferred = deferred
            deferreds.append(deferred)

        def handle_peer_responses(responses):
            for success, response in responses:
                if success and response:
                    return json.loads(response)
            return None

        return defer.gatherResults(deferreds).addCallback(handle_peer_responses)


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
