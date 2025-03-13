"""Factory for managing P2P connections and data synchronization."""

# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
# server/p2p/factory.py

import json
import uuid
from twisted.internet import endpoints, defer, protocol
from twisted.internet import reactor, task
from server.database import (
    store_spammer_data,
    retrieve_spammer_data_from_db,
    get_all_spammer_ids,
)
from server.server_config import LOGGER
from .config import YELLOW_COLOR, RESET_COLOR, PURPLE_COLOR, GREEN_COLOR, INVERSE_COLOR
from .protocol import P2PProtocol
from .address import PeerAddress


class P2PFactory(protocol.Factory):
    """Factory to manage P2P connections."""

    protocol = P2PProtocol

    def __init__(self, node_uuid=None, bootstrap_peers=None):
        self.peers = []
        self.node_uuid = node_uuid or str(uuid.uuid4())
        self.bootstrap_peers = bootstrap_peers or []  # Take bootstrap peers as argument
        self.protocol_instances = []
        self.known_uuids = set()  # Keep track of known UUIDs
        self.reconnect_delay = 10  # seconds
        self.max_reconnect_attempts = 5
        self.reconnect_attempts = 0
        self.is_bootstrap = not bootstrap_peers  # True if it's a bootstrap node
        self.PeerAddress = PeerAddress

    def buildProtocol(self, addr):
        """Build and return a protocol instance."""
        proto = self.protocol()
        proto.factory = self
        proto.processed_data = set()
        LOGGER.debug("New connection from address: %s", addr)
        self.protocol_instances.append(proto)
        return proto

    def broadcast_spammer_info(self, user_id):
        """Broadcast spammer information to all connected peers."""
        spammer_data = retrieve_spammer_data_from_db(user_id)
        if spammer_data:
            # Ensure nested JSON data is properly encoded
            LOGGER.debug(
                "%s%s Broadcasting spammer info%s", INVERSE_COLOR, user_id, RESET_COLOR
            )
            message = json.dumps(
                {
                    "type": "spammer_info_broadcast",
                    "user_id": user_id,
                    "is_spammer": spammer_data.get(
                        "is_spammer", False
                    ),  # Add is_spammer field
                    "lols_bot_data": spammer_data["lols_bot_data"],
                    "cas_chat_data": spammer_data["cas_chat_data"],
                    "p2p_data": spammer_data["p2p_data"],
                }
            )
            if not self.protocol_instances:
                LOGGER.warning("No peers to broadcast spammer info to.")
                return

            for proto in self.protocol_instances:
                # Check if the data has been received from the same peer
                if (
                    proto.received_from_peer
                    and proto.received_from_peer.host == proto.get_peer().host
                    and proto.received_from_peer.port == proto.get_peer().port
                ):
                    # Check if the data has changed
                    existing_data = retrieve_spammer_data_from_db(user_id)
                    if existing_data:
                        existing_lols_bot_data = existing_data.get("lols_bot_data", {})
                        if isinstance(existing_lols_bot_data, str):
                            existing_lols_bot_data = json.loads(existing_lols_bot_data)
                        existing_cas_chat_data = existing_data.get("cas_chat_data", {})
                        if isinstance(existing_cas_chat_data, str):
                            existing_cas_chat_data = json.loads(existing_cas_chat_data)
                        existing_p2p_data = existing_data.get("p2p_data", {})
                        if isinstance(existing_p2p_data, str):
                            existing_p2p_data = json.loads(existing_p2p_data)

                        if (
                            spammer_data["lols_bot_data"] == existing_lols_bot_data
                            and spammer_data["cas_chat_data"] == existing_cas_chat_data
                            and spammer_data["p2p_data"] == existing_p2p_data
                        ):
                            continue  # Skip sending if data has not changed
                if proto.peer_uuid != self.node_uuid:
                    proto.transport.write(message.encode("utf-8"))
                    LOGGER.debug(
                        "%s Sent updated spammer info to peer %s:%d",
                        user_id,
                        proto.get_peer().host,
                        proto.get_peer().port,
                    )
            LOGGER.debug(
                "%s%s Broadcasted spammer info: %s%s",
                INVERSE_COLOR,
                user_id,
                RESET_COLOR,
                message,
            )
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
        return defer.gatherResults(deferreds, consumeErrors=True)

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
        self.reconnect_attempts = 0  # Reset attempts on success

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
            "Failed to connect to bootstrap peer %s: %s",
            address,
            failure,
        )
        self.reconnect_attempts += 1
        if self.reconnect_attempts < self.max_reconnect_attempts:
            LOGGER.info(
                "Scheduling reconnection attempt %d to bootstrap peers in %d seconds...",
                self.reconnect_attempts,
                self.reconnect_delay,
            )
            # pylint: disable=no-member
            reactor.callLater(self.reconnect_delay, self.reconnect_to_bootstrap)
        else:
            LOGGER.warning(
                "Max reconnection attempts (%d) reached. Giving up on bootstrap peers.",
                self.max_reconnect_attempts,
            )
            # Stop further reconnection attempts
            self.bootstrap_peers = []

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
                        "Failed to connect to new peer %s:%d: %s",
                        h,
                        p,
                        err,
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
        active_protocols = list(self.protocol_instances)  # Iterate over a copy

        for proto in active_protocols:
            deferred = defer.Deferred()
            proto.deferred = deferred
            peer = proto.get_peer()
            host = peer.host
            port = peer.port

            def handle_timeout(proto=proto, user_id=user_id, host=host, port=port):
                """Handle timeout for P2P data check."""
                if hasattr(proto, "deferred"):
                    if hasattr(proto, "transport"):  # Check if transport exists
                        try:
                            LOGGER.warning(
                                "%s Timeout occurred while checking P2P data from peer %s:%d",
                                user_id,
                                proto.transport.getPeer().host,  # Access host from peer
                                proto.transport.getPeer().port,  # Access port from peer
                            )
                        except Exception as e:
                            LOGGER.error("Error accessing peer info in timeout: %s", e)
                    else:
                        LOGGER.warning(
                            "%s Timeout occurred, but connection was already lost for peer",
                            user_id,
                        )
                    # Only callback if the deferred hasn't already been called
                    if hasattr(proto, "deferred"):
                        proto.deferred.callback(None)
                        del proto.deferred
                    self.remove_peer(proto)

            # Add a timeout to the deferred
            proto.timeout_call = task.deferLater(reactor, 5, handle_timeout)

            try:
                proto.transport.write(
                    json.dumps({"type": "check_p2p_data", "user_id": user_id}).encode(
                        "utf-8"
                    )
                )

                LOGGER.debug(
                    "%s Sending check_p2p_data request to peer %s:%d",
                    user_id,
                    host,
                    port,
                )

                def handle_response(result):
                    """Handle the response from the peer."""
                    if (
                        hasattr(proto, "timeout_call")
                        and isinstance(proto.timeout_call, task.DelayedCall)
                        and proto.timeout_call.active()
                    ):
                        proto.timeout_call.cancel()
                    return result

                def handle_error(failure):
                    """Handle an error from the peer."""
                    if hasattr(proto, "timeout_call"):
                        if (
                            isinstance(proto.timeout_call, task.DelayedCall)
                            and proto.timeout_call.active()
                        ):
                            proto.timeout_call.cancel()
                    # Log the error, but don't remove the peer here
                    LOGGER.error(
                        "Error checking P2P data from peer %s:%d: %s",
                        host,
                        port,
                        failure,
                    )
                    return failure

                deferred.addCallback(handle_response)
                deferred.addErrback(handle_error)
                deferreds.append(deferred)

            except Exception as e:
                LOGGER.error(
                    "Error sending check_p2p_data request to peer %s:%d: %s",
                    host,
                    port,
                    e,
                )
                if proto.timeout_call and proto.timeout_call.active():
                    proto.timeout_call.cancel()
                self.remove_peer(proto)
                continue

        def handle_peer_responses(responses):
            valid_responses = [response for response in responses if response]
            if valid_responses:
                return json.loads(valid_responses[0])
            return None

        def handle_peer_resp_error(failure):
            """Handle errors during the P2P data check."""
            LOGGER.error("Error checking P2P data: %s", failure)
            return None  # Ensure a None value is returned on error

        return (
            defer.gatherResults(deferreds, consumeErrors=True)
            .addCallback(handle_peer_responses)
            .addErrback(handle_peer_resp_error)
        )

    def remove_peer(self, proto):
        """Remove a peer from the active peer list and schedule a reconnection."""
        peer = proto.get_peer()
        if peer.node_uuid == self.node_uuid:
            LOGGER.warning("Skipping reconnection attempt to self (UUID match): %s:%d", peer.host, peer.port)
            return
        if peer in self.peers:
            self.peers.remove(peer)
        if proto in self.protocol_instances:
            self.protocol_instances.remove(proto)
        LOGGER.info("Removed peer %s:%d from active peer list", peer.host, peer.port)
        self.schedule_reconnection(peer.host, peer.port)

    def schedule_reconnection(self, host, port):
        """Schedule a reconnection attempt to a peer."""
        LOGGER.info("Scheduling reconnection to peer %s:%d in %d seconds", host, port, self.reconnect_delay)
        # pylint: disable=no-member
        reactor.callLater(self.reconnect_delay, self.attempt_reconnection, host, port)

    def attempt_reconnection(self, host, port):
        """Attempt to reconnect to a peer."""
        LOGGER.info("Attempting reconnection to peer %s:%d", host, port)
        endpoint = endpoints.TCP4ClientEndpoint(reactor, host, port)
        endpoint.connect(self).addCallback(
            lambda _, h=host, p=port: LOGGER.info("Reconnected to peer %s:%d", h, p)
        ).addErrback(
            lambda err, h=host, p=port: LOGGER.error("Failed to reconnect to peer %s:%d: %s", h, p, err)
        )

    def is_duplicate_uuid(self, peer_uuid, current_proto):
        """Check if a peer with the same UUID already exists."""
        for proto in self.protocol_instances:
            if proto != current_proto and proto.peer_uuid == peer_uuid:
                return True
        return False

    def reconnect_to_bootstrap(self):
        """Reconnect to bootstrap peers."""
        if self.peers or self.is_bootstrap:
            return  # Don't reconnect if we already have peers or it's a bootstrap node

        if not self.bootstrap_peers:
            LOGGER.warning("No bootstrap peers available. Skipping reconnection.")
            return

        LOGGER.info("Attempting to reconnect to bootstrap peers...")
        bootstrap_addresses = [f"{p.host}:{p.port}" for p in self.bootstrap_peers]
        self.connect_to_bootstrap_peers(bootstrap_addresses)

    def store_spammer_data(
        self, user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer
    ):
        """Store spammer data in the database."""
        store_spammer_data(user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer)
