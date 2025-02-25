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
from twisted.internet.task import deferLater
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
            LOGGER.info("\033[7m%s received HTTP request\033[0m", user_id)

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
            self.check_database(user_id, response_data)

            # Check P2P network
            p2p_deferred = self.check_p2p_data(user_id)

            # Check static APIs
            api_deferred = self.check_static_apis(user_id)

            # Combine results with a timeout
            combined_deferred = defer.DeferredList(
                [p2p_deferred, api_deferred],
                fireOnOneCallback=True,
                fireOnOneErrback=True,
            )

            def handle_combined_results(results):
                result, _index = results
                success, data = result
                if success and data:
                    response_data.update(data)
                    if data.get("is_spammer", False):
                        response_data["is_spammer"] = True

                # Store the data in the database
                store_spammer_data(
                    user_id,
                    json.dumps(response_data["lols_bot"]),
                    json.dumps(response_data["cas_chat"]),
                    json.dumps(response_data["p2p"]),
                )

                # Propagate P2P data over peer network if they don't have such records
                self.p2p_factory.broadcast_spammer_info(user_id)

                LOGGER.info("\033[7m%s sending HTTP request response\033[0m", user_id)
                request.setHeader(b"content-type", b"application/json")
                request.write(json.dumps(response_data).encode("utf-8"))
                request.finish()
                LOGGER.debug("HTTP GET response sent: %s", response_data)

            def handle_combined_error(failure):
                LOGGER.error("Error combining results: %s", failure)
                response = {
                    "ok": False,
                    "user_id": user_id,
                    "error": str(failure),
                }
                request.setHeader(b"content-type", b"application/json")
                request.write(json.dumps(response).encode("utf-8"))
                request.finish()
                LOGGER.info("Error response sent: %s", response)

            combined_deferred.addCallback(handle_combined_results)
            combined_deferred.addErrback(handle_combined_error)

            return server.NOT_DONE_YET
        else:
            request.setResponseCode(400)
            return b"Missing user_id parameter"

    def check_database(self, user_id, response_data):
        """Check the database for spammer data."""
        LOGGER.debug("%s Checking database", user_id)
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
                json.loads(spammer_data["p2p_data"]) if spammer_data["p2p_data"] else {}
            )
            response_data["is_spammer"] = self.is_spammer(response_data)
            LOGGER.info("%s Data found in database: %s", user_id, response_data)

    def check_p2p_data(self, user_id):
        """Check P2P network for spammer data."""
        p2p_deferred = self.p2p_factory.check_p2p_data(user_id)
        timeout_deferred = deferLater(reactor, 1, lambda: None)
        return defer.DeferredList(
            [p2p_deferred, timeout_deferred],
            fireOnOneCallback=True,
            fireOnOneErrback=True,
        )

    def check_static_apis(self, user_id):
        """Check static APIs for spammer data."""
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

            return {
                "lols_bot": lols_bot_data,
                "cas_chat": cas_chat_data,
                "is_spammer": self.is_spammer(
                    {
                        "lols_bot": lols_bot_data,
                        "cas_chat": cas_chat_data,
                        "p2p": {},
                    }
                ),
            }

        def handle_API_error(failure):
            LOGGER.error("Error querying APIs: %s", failure)
            return None

        api_deferred = defer.gatherResults([d1, d2])
        api_deferred.addCallback(handle_response)
        api_deferred.addErrback(handle_API_error)

        timeout_deferred = deferLater(reactor, 1, lambda: None)
        return defer.DeferredList(
            [api_deferred, timeout_deferred],
            fireOnOneCallback=True,
            fireOnOneErrback=True,
        )

    def is_spammer(self, data) -> bool:
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
