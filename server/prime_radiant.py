"""Prime Radiant - p2p antispam server."""

# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
# server/prime_radiant.py

# TODO each node signature with spam markup criteria - to choose the best node for spam checking condition
# TODO if no peers or bootsrap available node stops reconnecting
# XXX how the node itself can understand that it is a bootstrap node?
# TODO prevent data mutation during rebroadcast cas messages

import sys
import uuid
import os  # Import the os module
from twisted.internet import reactor, endpoints
from twisted.internet.error import CannotListenError
from twisted.web import resource, server
from twisted.internet import task

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from server.p2p.factory import P2PFactory
from server.p2p.utils import find_available_port
from server.websocket import SpammerCheckFactory
from server.api import SpammerCheckResource, ReportIdResource, RemoveIdResource
from server.database import initialize_database
from server.server_config import (
    LOGGER,
    DEFAULT_P2P_PORT,
    WEBSOCKET_PORT,
    HTTP_API_PORT,
    BOOTSTRAP_ADDRESSES,
)


def main():
    """Main function to start the server."""

    # Initialize the database
    initialize_database()

    if len(sys.argv) < 2:
        port = DEFAULT_P2P_PORT
    else:
        port = int(sys.argv[1])

    peers = sys.argv[2:]

    node_uuid = str(uuid.uuid4())

    LOGGER.info("\033[95mStarting P2P server on port: %d\033[0m", port)
    LOGGER.info("Server UUID: \033[30;47m%s\033[0m", node_uuid)

    # Find an available port if the default port is not available
    # port = find_available_port(port)
    # LOGGER.debug("Using port %d for P2P server", port)

    ws_factory = SpammerCheckFactory()
    ws_endpoint = endpoints.TCP4ServerEndpoint(reactor, WEBSOCKET_PORT)
    ws_endpoint.listen(ws_factory)
    LOGGER.info("\033[92mWebSocket server listening on port %d\033[0m", WEBSOCKET_PORT)

    p2p_factory = P2PFactory(node_uuid)

    root = resource.Resource()
    root.putChild(b"check", SpammerCheckResource(p2p_factory))
    root.putChild(b"report_id", ReportIdResource(p2p_factory))
    http_factory = server.Site(root)
    http_endpoint = endpoints.TCP4ServerEndpoint(reactor, HTTP_API_PORT)
    http_endpoint.listen(http_factory)
    LOGGER.info("\033[92mHTTP server listening on port %d\033[0m", HTTP_API_PORT)

    remove_resource = RemoveIdResource(p2p_factory)
    root.putChild(b"remove_id", remove_resource)

    # p2p_endpoint = endpoints.TCP4ServerEndpoint(reactor, port, interface="0.0.0.0")
    p2p_endpoint = endpoints.TCP4ServerEndpoint(reactor, port)

    while True:
        try:
            p2p_endpoint.listen(p2p_factory)
            LOGGER.info("\033[92mP2P server listening on port %d\033[0m", port)
            break
        except CannotListenError as e:
            LOGGER.error("Cannot listen on port %d: %s", port, e)
            port = find_available_port(port + 1)
            LOGGER.info("Retrying with port %d", port)
            p2p_endpoint = endpoints.TCP4ServerEndpoint(
                reactor, port, interface="0.0.0.0"
            )

    def log_peer_info():
        """Logs the details of connected peers."""
        LOGGER.info("\033[30;47mConnected bootstrap peers:\033[0m")
        for proto in p2p_factory.protocol_instances:
            if hasattr(proto, "peer_uuid"):
                peer = proto.transport.getPeer()
                LOGGER.info(
                    "\033[92m  %s:%d - UUID: %s\033[0m",
                    peer.host,
                    peer.port,
                    proto.peer_uuid,
                )
            else:
                peer = proto.transport.getPeer()
                LOGGER.warning(
                    "Peer %s:%d has not completed handshake.", peer.host, peer.port
                )

    p2p_factory.connect_to_bootstrap_peers(BOOTSTRAP_ADDRESSES).addCallback(
        lambda _: LOGGER.info("\033[95mFinished connecting to bootstrap peers\033[0m")
    ).addCallback(lambda _: task.deferLater(reactor, 5, log_peer_info))

    for peer in peers:
        peer_host, peer_port = peer.split(":")
        peer_port = int(peer_port)
        peer_endpoint = endpoints.TCP4ClientEndpoint(reactor, peer_host, peer_port)
        peer_endpoint.connect(p2p_factory).addCallback(
            lambda _, host=peer_host, port=peer_port: LOGGER.info(
                "Connected to peer %s:%d", host, port
            )
        ).addErrback(
            lambda err, host=peer_host, port=peer_port: LOGGER.error(
                "Failed to connect to peer %s:%d: %s", host, port, err
            )
        )
        LOGGER.info("Connecting to peer %s:%d", peer_host, peer_port)

    reactor.run()  # pylint: disable=no-member


if __name__ == "__main__":
    main()
