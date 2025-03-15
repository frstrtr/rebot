import json
import sys
import os

from twisted.internet.error import ConnectionLost
from twisted.web import server, resource
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.internet import defer, reactor
from twisted.web.iweb import IPolicyForHTTPS
from twisted.internet.ssl import CertificateOptions
from twisted.internet._sslverify import ClientTLSOptions
from twisted.web.server import Request

from zope.interface import implementer

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from server.database import retrieve_spammer_data_from_db, store_spammer_data
from server.p2p import P2PFactory

from server.server_config import LOGGER


@implementer(IPolicyForHTTPS)
class NoVerifyContextFactory:
    """A context factory that does not verify SSL certificates."""

    def __init__(self, hostname):
        self.hostname = hostname
        self.options = CertificateOptions(verify=False)

    def creatorForNetloc(self, hostname, port):
        """Function description here"""
        LOGGER.debug("Creating context for %s: %s", hostname, port)
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
            LOGGER.debug("%s Checking database", user_id)
            self.check_database(user_id, response_data)

            # Check P2P network
            LOGGER.debug("%s Checking P2P network", user_id)
            p2p_deferred = self.check_p2p_data(user_id)

            # Check static APIs
            LOGGER.debug("%s Checking static APIs", user_id)
            api_deferred = self.check_static_apis(user_id)

            # Combine results
            combined_deferred = defer.DeferredList(
                [p2p_deferred, api_deferred],
                fireOnOneCallback=False,
                fireOnOneErrback=True,
            )

            # Add a timeout
            timeout_deferred = combined_deferred.addTimeout(5, reactor)

            # Create a deferred that fires when the connection is lost
            client_disconnected = defer.Deferred()
            request.notifyFinish().addErrback(
                lambda err: client_disconnected.callback(None)
            )

            def send_response(response_data):
                """Helper function to send the HTTP response."""
                try:
                    # if not request.connectionLost:
                    request.setHeader(b"content-type", b"application/json")
                    request.write(json.dumps(response_data).encode("utf-8"))
                    LOGGER.debug("HTTP GET response sent: %s", response_data)
                    request.finish()
                    LOGGER.debug("Request finished successfully.")
                    # else:
                    #     LOGGER.warning("Connection lost before finishing response.")
                except ConnectionLost as e:
                    LOGGER.error("Error sending response: %s", e)

            def handle_combined_results(results):
                LOGGER.debug("Handling combined results: %s", results)
                p2p_result, api_result = results

                # Check if results are tuples before unpacking
                if isinstance(p2p_result, tuple):
                    p2p_success, p2p_data = p2p_result
                else:
                    p2p_success, p2p_data = False, {}

                if isinstance(api_result, tuple):
                    api_success, api_data = api_result
                else:
                    api_success, api_data = False, {}

                if p2p_success and p2p_data and p2p_data.get("p2p_data") != "{}":
                    LOGGER.debug("%s P2P data found: %s", user_id, p2p_data)
                    # rename keys in p2p_data dict and convert str value to dict
                    lols_bot_data = p2p_data.get("lols_bot_data", {})
                    cas_chat_data = p2p_data.get("cas_chat_data", {})
                    p2p_section = p2p_data.get("p2p_data", {})
                    p2p_data = {
                        "lols_bot": lols_bot_data,
                        "cas_chat": cas_chat_data,
                        "p2p": p2p_section,
                        "user_id": int(p2p_data.get("user_id", user_id)),
                        "is_spammer": p2p_data.get("is_spammer", False),
                    }
                    response_data.update(p2p_data)
                else:
                    LOGGER.debug("%s no P2P data found", user_id)
                    # Reconstruct p2p data if it's not available
                    lols_bot_data = response_data.get("lols_bot", {})
                    cas_chat_data = response_data.get("cas_chat", {})
                    # local_report_data =
                    is_spammer = bool(
                        lols_bot_data.get("banned", False)
                        or cas_chat_data.get("result", {}).get("offenses", 0) > 0
                        or response_data.get("is_spammer", False)
                    )
                    response_data["lols_bot"] = lols_bot_data
                    response_data["cas_chat"] = cas_chat_data
                    response_data["p2p"] = {
                        "ok": True,
                        "user_id": user_id,
                        "is_spammer": is_spammer,
                    }
                    response_data["is_spammer"] = bool(
                        is_spammer  # Update overall is_spammer status
                    )

                if api_success and api_data:
                    LOGGER.debug("%s API data found: %s", user_id, api_data)
                    if response_data[
                        "is_spammer"
                    ]:  # if not already marked as spammer by local endpoint report
                        api_data.pop(
                            "is_spammer", None
                        )  # ignore is_spammer from API data
                    # Update response data with API data
                    response_data.update(api_data)
                    # Check if the API data indicates the user is a spammer
                    if api_data.get("is_spammer", False):
                        response_data["is_spammer"] = True

                # Update the overall is_spammer status for the p2p section
                response_data["p2p"]["is_spammer"] = response_data["is_spammer"]

                # Store the data in the database
                LOGGER.debug("%s Storing data in database", user_id)
                store_spammer_data(
                    user_id,
                    json.dumps(response_data["lols_bot"]),
                    json.dumps(response_data["cas_chat"]),
                    json.dumps(response_data["p2p"]),
                    response_data["is_spammer"],
                )

                # Propagate P2P data over peer network if they don't have such records
                LOGGER.debug("%s Broadcasting data over P2P network", user_id)
                self.p2p_factory.broadcast_spammer_info(user_id)

                LOGGER.info("\033[7m%s sending HTTP request response\033[0m", user_id)
                send_response(response_data)

            def handle_combined_error(failure):
                LOGGER.error("Error combining results: %s", failure)
                if failure.check(defer.TimeoutError):
                    LOGGER.error("Request timed out.")
                elif failure.check(defer.CancelledError):
                    LOGGER.error("Request cancelled.")

                response = {
                    "ok": False,
                    "user_id": user_id,
                    "error": str(failure),
                }
                send_response(response)
                LOGGER.info("Error response sent: %s", response)

            timeout_deferred.addCallback(handle_combined_results)
            timeout_deferred.addErrback(handle_combined_error)

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
            response_data["is_spammer"] = spammer_data["is_spammer"]
            LOGGER.info("%s Data found in database: %s", user_id, response_data)

    def check_p2p_data(self, user_id):
        """Check P2P network for spammer data."""
        return self.p2p_factory.check_p2p_data(user_id)

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
            LOGGER.info("LOLS bot response: %s", lols_bot_response)
            LOGGER.info("CAS chat response: %s", cas_chat_response)
            lols_bot_data = (
                json.loads(lols_bot_response.decode("utf-8"))
                if lols_bot_response
                else {}
            )
            cas_chat_data = (
                json.loads(cas_chat_response.decode("utf-8"))
                if cas_chat_response
                else {}
            )

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
            """Handle errors from API requests."""
            LOGGER.warning("Error querying APIs: %s", failure)
            return ""  # Return an empty string to be handled as a missing response

        api_deferred = (
            defer.gatherResults([d1, d2], consumeErrors=True)
            .addCallback(handle_response)
            .addErrback(handle_API_error)
        )

        return api_deferred

    def is_spammer(self, data) -> bool:
        """Determine if the user is a spammer based on the data."""
        user_id = data.get("user_id", None)
        LOGGER.debug(
            "%s checking if user is a spammer: %s",
            user_id or data.get("lols_bot", {}).get("user_id", "unknown"),
            data,
        )

        lols_bot_data = data.get("lols_bot", {})
        cas_chat_data = data.get("cas_chat", {})
        p2p_data = data.get("p2p", {})

        is_spammer_result = (
            lols_bot_data.get("banned", False)
            or cas_chat_data.get("result", {}).get("offenses", 0) > 0
            or p2p_data.get("is_spammer", False)
        )

        LOGGER.debug("lols_bot_data: %s", lols_bot_data)
        LOGGER.debug("cas_chat_data: %s", cas_chat_data)
        LOGGER.debug("p2p_data: %s", p2p_data)
        LOGGER.debug("is_spammer_result: %s", is_spammer_result)

        return is_spammer_result


class ReportIdResource(resource.Resource):
    """Resource for reporting a spammer by ID."""

    isLeaf = True

    def __init__(self, p2p_factory):
        resource.Resource.__init__(self)
        self.p2p_factory = p2p_factory

    def render_POST(self, request: Request):
        """Handle POST requests to report a spammer by ID."""
        try:
            user_id = request.args.get(b"user_id", [None])[0]

            # Get the client IP address
            client_ip = request.getClientIP()
            if client_ip != "127.0.0.1":
                LOGGER.warning("Unauthorized access attempt from IP: %s", client_ip)
                request.setResponseCode(403)  # Forbidden
                return b"Forbidden: Only localhost can access this endpoint."
            if not user_id:
                LOGGER.error("%s Invalid request. Must include user_id.", "unknown")
                request.setResponseCode(400)
                return b"Invalid request. Must include user_id."

            user_id = user_id.decode("utf-8")
            LOGGER.warning("%s Received POST request to report spammer", user_id)

            # Assuming that if the request reaches here, the user is a spammer
            is_spammer = True

            # Store the data and broadcast
            LOGGER.debug("%s Storing spammer data", user_id)
            store_spammer_data(user_id, "{}", "{}", "{}", is_spammer)
            LOGGER.debug("%s Broadcasting spammer info", user_id)
            self.p2p_factory.broadcast_spammer_info(user_id)

            request.setHeader(b"content-type", b"application/json")
            response = json.dumps(
                {"status": "success", "user_id": user_id, "is_spammer": is_spammer}
            ).encode("utf-8")
            request.write(response)
            request.finish()
            LOGGER.info("%s POST request processed successfully", user_id)
            return server.NOT_DONE_YET
        except (ValueError, KeyError, TypeError) as e:
            LOGGER.error(
                "%s Error processing POST request: %s",
                user_id if "user_id" in locals() else "unknown",
                e,
            )
            return f"Error processing request: {str(e)}".encode("utf-8")
