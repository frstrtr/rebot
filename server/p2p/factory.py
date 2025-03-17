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
        host = addr.host
        port = addr.port
        # Check if there's already a connection to this peer
        for proto in self.protocol_instances:
            peer = proto.get_peer()
            if peer.host == host and peer.port == port:
                LOGGER.info(
                    "Closing duplicate incoming connection from %s:%d", host, port
                )
                return None  # Reject the new connection

        proto = self.protocol()
        proto.factory = self
        proto.processed_data = set()
        LOGGER.debug("New connection from address: %s", addr)
        self.protocol_instances.append(proto)
        return proto

    def remove_duplicate_peers(self, peer_uuid):
        """Remove duplicate peers with the same UUID, keeping only the most recent one."""
        duplicates = []
        most_recent_proto = None
        most_recent_time = 0

        for proto in self.protocol_instances:
            if proto.peer_uuid == peer_uuid:
                duplicates.append(proto)
                # Determine the most recent connection based on connection time
                if proto.transport and proto.transport.connected:
                    current_time = (
                        proto.transport.connector.startTime
                        if hasattr(proto.transport, "connector")
                        and hasattr(proto.transport.connector, "startTime")
                        else 0
                    )
                    if current_time > most_recent_time:
                        most_recent_time = current_time
                        most_recent_proto = proto

        # Remove all duplicates except the most recent one
        for proto in duplicates:
            if proto != most_recent_proto:
                LOGGER.info(
                    "Removing duplicate peer %s:%d with UUID %s",
                    proto.transport.getPeer().host,
                    proto.transport.getPeer().port,
                    peer_uuid,
                )
                proto.transport.loseConnection()  # Close the connection
                self.protocol_instances.remove(proto)  # Remove from the list

    def broadcast_spammer_info(self, user_id):
        """Broadcast spammer information to all connected peers."""
        spammer_data = retrieve_spammer_data_from_db(user_id)
        if spammer_data:
            # Parse nested JSON data
            lols_bot_data = spammer_data.get("lols_bot_data", {})
            if isinstance(lols_bot_data, str):
                lols_bot_data = json.loads(lols_bot_data)
            cas_chat_data = spammer_data.get("cas_chat_data", {})
            if isinstance(cas_chat_data, str):
                cas_chat_data = json.loads(cas_chat_data)
            p2p_data = spammer_data.get("p2p_data", {})
            if isinstance(p2p_data, str):
                p2p_data = json.loads(p2p_data)

            # Ensure nested JSON data is properly encoded
            message = json.dumps(
                {
                    "type": "spammer_info_broadcast",
                    "user_id": user_id,
                    "is_spammer": spammer_data.get(
                        "is_spammer", False
                    ),  # Add is_spammer field
                    "lols_bot_data": lols_bot_data,
                    "cas_chat_data": cas_chat_data,
                    "p2p_data": p2p_data,
                }
            )
            log_message = json.loads(message)
            if (
                "cas_chat_data" in log_message
                and "result" in log_message["cas_chat_data"]
                and "messages" in log_message["cas_chat_data"]["result"]
            ):
                messages = log_message["cas_chat_data"]["result"]["messages"]
                if isinstance(messages, list):  # Add this check
                    decoded_messages = [
                        m.encode("utf-8").decode("unicode_escape") for m in messages
                    ]
                    log_message["cas_chat_data"]["result"][
                        "messages"
                    ] = decoded_messages
                else:
                    LOGGER.warning(
                        "cas_chat_data messages is not a list, skipping decoding"
                    )
            LOGGER.debug(
                "%s%s Broadcasting spammer info:%s\n%s",
                INVERSE_COLOR,
                user_id,
                RESET_COLOR,
                json.dumps(log_message, indent=4),
            )
            if not self.protocol_instances:
                LOGGER.warning("No peers to broadcast spammer info to.")
                return

            sent_uuids = set()  # Keep track of UUIDs we've already sent to

            for proto in self.protocol_instances:
                peer = proto.get_peer()

                # Check if we've already sent to this UUID
                if proto.peer_uuid in sent_uuids:
                    LOGGER.debug(
                        "%s Skipping send to %s (already sent to this UUID)",
                        user_id,
                        proto.peer_uuid,
                    )
                    continue

                # Check if the data has been received from the same peer
                # AND if the data has not changed
                if (
                    proto.received_from_peer
                    and proto.received_from_peer.host == peer.host
                    and proto.received_from_peer.port == peer.port
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
                            lols_bot_data == existing_lols_bot_data
                            and cas_chat_data == existing_cas_chat_data
                            and p2p_data == existing_p2p_data
                        ):
                            LOGGER.debug(
                                "%s Skipping send to %s:%d (%s) (data has not changed)",
                                user_id,
                                peer.host,
                                peer.port,
                                proto.peer_uuid,
                            )
                            continue  # Skip sending if data has not changed
                else:
                    if proto.peer_uuid != self.node_uuid:
                        proto.transport.write(message.encode("utf-8"))
                        LOGGER.debug(
                            "%s Sent updated spammer info to peer %s:%d (%s)",
                            user_id,
                            peer.host,
                            peer.port,
                            proto.get_peer().node_uuid,
                        )
                        sent_uuids.add(
                            proto.peer_uuid
                        )  # Add the UUID to the set of sent UUIDs

            LOGGER.debug(
                "%s%s spammer info broadcasted%s",
                INVERSE_COLOR,
                user_id,
                RESET_COLOR,
            )
        else:
            LOGGER.warning("No spammer data found for user_id in local DB: %s", user_id)
            # TODO check other spam nodes and endpoints

    def broadcast_user_amnesty(self, user_id):
        """Broadcast spammer removal information to all connected peers."""
        message = json.dumps(
            {"type": "spammer_info_removal", "user_id": user_id}
        ).encode("utf-8")

        LOGGER.debug(
            "%s Broadcasting spammer removal info for user_id: %s",
            INVERSE_COLOR,
            user_id,
        )

        for proto in self.protocol_instances:
            proto.transport.write(message)
            LOGGER.debug(
                "%s Sent spammer removal info to peer %s:%d",
                user_id,
                proto.transport.getPeer().host,
                proto.transport.getPeer().port,
            )

    def connect_to_bootstrap_peers(self, bootstrap_addresses):
        """Connect to bootstrap peers and gather available peers."""
        deferreds = []
        for address in bootstrap_addresses:
            host, port = address.split(":")
            port = int(port)
            # Check if there's already a connection to this peer
            if any(p.host == host and p.port == port for p in self.peers):
                LOGGER.info(
                    "Already connected to peer %s:%d, skipping bootstrap connection",
                    host,
                    port,
                )
                continue  # Skip if already connected
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

        # Remove duplicate peers with the same UUID
        self.remove_duplicate_peers(peer_uuid)

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
            peer = proto.get_peer()

            # Check if the peer's UUID is known and is not self
            if not peer.node_uuid:
                LOGGER.warning(
                    "%s skipping check_p2p_data, peer UUID not yet known: %s:%d",
                    user_id,
                    peer.host,
                    peer.port,
                )
                continue

            if peer.node_uuid == self.node_uuid:
                LOGGER.warning(
                    "%s skipping check_p2p_data, is self: %s:%d %s%s%s",
                    user_id,
                    peer.host,
                    peer.port,
                    YELLOW_COLOR,
                    peer.node_uuid,
                    RESET_COLOR,
                )
                continue

            deferred = defer.Deferred()
            proto.deferred = deferred
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
                        except (AttributeError, RuntimeError) as e:
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
            LOGGER.warning(
                "Skipping reconnection attempt to self (UUID match): %s:%d",
                peer.host,
                peer.port,
            )
            LOGGER.warning(
                "Skipping reconnection attempt to self (UUID match): %s:%d",
                peer.host,
                peer.port,
            )
            return
        if peer in self.peers:
            self.peers.remove(peer)
        if proto in self.protocol_instances:
            self.protocol_instances.remove(proto)
        LOGGER.info("Removed peer %s:%d from active peer list", peer.host, peer.port)
        self.schedule_reconnection(peer.host, peer.port)

    def schedule_reconnection(self, host, port):
        """Schedule a reconnection attempt to a peer."""
        LOGGER.info(
            "Scheduling reconnection to peer %s:%d in %d seconds",
            host,
            port,
            self.reconnect_delay,
        )
        LOGGER.info(
            "Scheduling reconnection to peer %s:%d in %d seconds",
            host,
            port,
            self.reconnect_delay,
        )
        # pylint: disable=no-member
        reactor.callLater(self.reconnect_delay, self.attempt_reconnection, host, port)

    def attempt_reconnection(self, host, port):
        """Attempt to reconnect to a peer."""
        LOGGER.info("Attempting reconnection to peer %s:%d", host, port)
        endpoint = endpoints.TCP4ClientEndpoint(reactor, host, port)
        endpoint.connect(self).addCallback(
            lambda _, h=host, p=port: LOGGER.info("Reconnected to peer %s:%d", h, p)
        ).addErrback(
            lambda err, h=host, p=port: LOGGER.error(
                "Failed to reconnect to peer %s:%d: %s", h, p, err
            )
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

    # def log_connected_peers(self):
    #     """Log details of all connected peers."""
    #     LOGGER.info("Logging details of all connected peers:")
    #     for proto in self.protocol_instances:
    #         peer = proto.get_peer()
    #         LOGGER.info(
    #             "  - Host: %s, Port: %s, UUID: %s", peer.host, peer.port, peer.node_uuid
    #         )
