# api.py

"""
This module handles API requests and responses.
"""

import json
import logging

from twisted.web import server, resource
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.internet import defer, reactor
from twisted.web.iweb import IPolicyForHTTPS
from twisted.internet.ssl import CertificateOptions
from twisted.internet._sslverify import ClientTLSOptions

from zope.interface import implementer

from database import retrieve_spammer_data_from_db, store_spammer_data
from p2p import P2PFactory

from server_config import LOGGER


@implementer(IPolicyForHTTPS)
class NoVerifyContextFactory:
    """A context factory that does not verify SSL certificates."""

    def __init__(self, hostname):
        self.hostname = hostname
        self.options = CertificateOptions(verify=False)

    def creatorForNetloc(self, hostname, port):
        """Function description here"""
        LOGGER.info("Creating context for %s: %s", hostname, port)
        return ClientTLSOptions(hostname, self.options.getContext())


class APIClient:
    """A helper class to fetch data from static endpoints using Twisted's Agent."""

    def __init__(self, hostname):
        self.agent = Agent(reactor, contextFactory=NoVerifyContextFactory(hostname))

    def fetch_data(self, url):
        """Fetch data from the given URL."""
        return self.agent.request(
            b"GET",
            url.encode("utf-8"),
            Headers({"User-Agent": ["Twisted P2P spam checker"]}),
            None,
        ).addCallback(readBody)


class SpammerCheckResource(resource.Resource):
    """HTTP resource to handle spammer check requests."""

    isLeaf = True

    def __init__(self, p2p_factory):
        super().__init__()
        self.p2p_factory: P2PFactory = p2p_factory

    def render_GET(self, request):
        """Handle GET requests by fetching data from the database, P2P network, and static APIs."""
        user_id = request.args.get(b"user_id", [None])[0]
        if user_id:
            user_id = user_id.decode("utf-8")
            LOGGER.info("\033[7mReceived HTTP request for user_id: %s\033[0m", user_id)

            # Initialize response data
            response_data = {
                "ok": True,
                "user_id": user_id,
                "is_spammer": False,
                "lols_bot": {},
                "cas_chat": {},
                "p2p": {},
            }

            # Check database first
            spammer_data = retrieve_spammer_data_from_db(user_id)
            if spammer_data:
                response_data["lols_bot"] = (
                    json.loads(spammer_data["lols_bot_data"])
                    if spammer_data["lols_bot_data"]
                    else {}
                )
                response_data["cas_chat"] = (
                    json.loads(spammer_data["cas_chat_data"])
                    if spammer_data["cas_chat_data"]
                    else {}
                )
                response_data["p2p"] = (
                    json.loads(spammer_data["p2p_data"])
                    if spammer_data["p2p_data"]
                    else {}
                )
                response_data["is_spammer"] = self.is_spammer(response_data)

            # Check P2P network secondly
            p2p_data = self.p2p_factory.check_p2p_data(user_id) or {}
            if p2p_data:
                response_data["p2p"] = p2p_data
                response_data["is_spammer"] = self.is_spammer(response_data)

            # Check static APIs finally
            logging.info("Checking static APIs for user_id: %s", user_id)
            api_client_lols = APIClient("api.lols.bot")
            api_client_cas = APIClient("api.cas.chat")
            lols_bot_url = f"https://api.lols.bot/account?id={user_id}"
            cas_chat_url = f"https://api.cas.chat/check?user_id={user_id}"

            d1 = api_client_lols.fetch_data(lols_bot_url)
            d2 = api_client_cas.fetch_data(cas_chat_url)

            def handle_response(responses):
                lols_bot_response, cas_chat_response = responses
                LOGGER.info("LOLS bot response: %s", lols_bot_response.decode("utf-8"))
                LOGGER.info("CAS chat response: %s", cas_chat_response.decode("utf-8"))
                lols_bot_data = json.loads(lols_bot_response.decode("utf-8"))
                cas_chat_data = json.loads(cas_chat_response.decode("utf-8"))

                response_data["lols_bot"] = lols_bot_data
                response_data["cas_chat"] = cas_chat_data
                response_data["is_spammer"] = self.is_spammer(response_data)

                # Construct P2P data based on responses from static APIs
                p2p_data = {
                    "ok": True,
                    "user_id": user_id,
                    "is_spammer": response_data["is_spammer"],
                }
                response_data["p2p"] = p2p_data

                # Store the data in the database
                store_spammer_data(
                    user_id,
                    json.dumps(response_data["lols_bot"]),
                    json.dumps(response_data["cas_chat"]),
                    json.dumps(response_data["p2p"]),
                )

                # Propagate P2P data over peer network if they don't have such records
                self.p2p_factory.broadcast_spammer_info(user_id)

                request.setHeader(b"content-type", b"application/json")
                request.write(json.dumps(response_data).encode("utf-8"))
                request.finish()
                LOGGER.info("Response sent from static APIs: %s", response_data)

            def handle_error(failure):
                LOGGER.error("Error querying APIs: %s", failure)
                response = {
                    "ok": False,
                    "user_id": user_id,
                    "error": str(failure),
                }
                request.setHeader(b"content-type", b"application/json")
                request.write(json.dumps(response).encode("utf-8"))
                request.finish()
                LOGGER.info("Error response sent: %s", response)

            d = defer.gatherResults([d1, d2])
            d.addCallback(handle_response)
            d.addErrback(handle_error)
            return server.NOT_DONE_YET
        else:
            request.setResponseCode(400)
            return b"Missing user_id parameter"

    def is_spammer(self, data):
        """Determine if the user is a spammer based on the data."""
        logging.debug("Checking if user is a spammer: %s", data)

        lols_bot_data = data.get("lols_bot", {})
        cas_chat_data = data.get("cas_chat", {})
        p2p_data = data.get("p2p", {})

        return (
            lols_bot_data.get("banned", False)
            or cas_chat_data.get("result", {}).get("offenses", 0) > 0
            or p2p_data.get("is_spammer", False)
        )
