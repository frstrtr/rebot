"""Lightweight protocol for handling initial handshake."""

import json
from twisted.internet import protocol
from server.server_config import LOGGER
from .config import HANDSHAKE_INIT


class InitiationProtocol(protocol.Protocol):
    """Lightweight protocol to handle initial handshake and UUID check."""

    def __init__(self, factory, addr):
        self.factory = factory
        self.addr = addr  # Store the address
        self.buffer = b""
        self.peer_uuid = None  # Initialize peer_uuid

    def dataReceived(self, data):
        """Handle received data."""
        self.buffer += data
        try:
            message = json.loads(self.buffer.decode("utf-8"))
            message_type = message.get("type")

            if message_type == HANDSHAKE_INIT:
                peer_uuid = message.get("uuid")
                self.peer_uuid = peer_uuid  # Store the peer_uuid
                if peer_uuid == self.factory.node_uuid:
                    LOGGER.warning("Detected self-connection, dropping connection.")
                    self.transport.loseConnection()
                else:
                    # Check for duplicate connections based on host and port
                    for proto in self.factory.protocol_instances:
                        peer = proto.get_peer()
                        if peer.host == self.addr.host and peer.port == self.addr.port:
                            LOGGER.info(
                                "Closing duplicate incoming connection from %s:%d",
                                self.addr.host,
                                self.addr.port,
                            )
                            self.transport.loseConnection()
                            return  # Reject the new connection

                    # Upgrade to P2PProtocol
                    p2p_protocol = self.factory.protocol()
                    p2p_protocol.factory = self.factory
                    p2p_protocol.transport = self.transport
                    self.factory.protocol_instances.append(p2p_protocol)
                    self.factory.remove_initiation_protocol(self)
                    self.factory.handle_peer_uuid(p2p_protocol, peer_uuid)
                    self.transport.protocol = (
                        p2p_protocol  # Update transport's protocol
                    )
                    p2p_protocol.makeConnection(
                        self.transport
                    )  # Manually call makeConnection
            else:
                LOGGER.warning("Received unexpected message type: %s", message_type)
                self.transport.loseConnection()
        except json.JSONDecodeError:
            # Incomplete JSON, wait for more data
            pass
        except Exception as e:
            LOGGER.error("Error processing initial message: %s", e)
            self.transport.loseConnection()

    def connectionLost(self, reason=protocol.connectionDone):
        """Handle lost connection."""
        if self in self.factory.initiation_protocols:
            self.factory.remove_initiation_protocol(self)
