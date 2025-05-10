from twisted.web import server, resource
from twisted.internet import endpoints
from twisted.internet import reactor  # type: ignore
from twisted.internet.defer import Deferred
from twisted.web.server import Request
import json
from server.server_config import LOGGER

class SpammerDataResource(resource.Resource):
    isLeaf = True

    def __init__(self, p2p_factory):
        resource.Resource.__init__(self)
        self.p2p_factory = p2p_factory

    def render_POST(self, request: Request):
        """Handle POST requests to receive spammer data."""
        try:
            content = request.content.read()
            data = json.loads(content.decode('utf-8'))

            # Basic data validation
            if not data or 'user_id' not in data:
                request.setResponseCode(400)
                return b"Invalid data: Missing user_id"

            # Process the data asynchronously
            d = self.process_spammer_data(data)

            def on_success(result):
                request.setHeader(b"content-type", b"application/json")
                request.write(json.dumps({"status": "success", "message": "Data processed"}).encode('utf-8'))
                request.finish()

            def on_error(failure):
                LOGGER.error("Error processing spammer data: %s", failure)
                request.setResponseCode(500)
                request.write(b"Error processing data")
                request.finish()

            d.addCallbacks(on_success, on_error)
            return server.NOT_DONE_YET

        except json.JSONDecodeError:
            request.setResponseCode(400)
            return b"Invalid JSON data"
        except Exception as e:
            LOGGER.error("Error receiving spammer data: %s", e)
            request.setResponseCode(500)
            return b"Internal server error"

    def process_spammer_data(self, data):
        """Process spammer data and send to P2P network."""
        d = Deferred()
        # Asynchronous call 
        reactor.callLater(0, self.send_data_to_p2p, data, d)  # pylint: disable=no-member
        return d

    def send_data_to_p2p(self, data, deferred):
        """Send data to the P2P network."""
        try:
            # Serialize data
            serialized_data = json.dumps(data).encode('utf-8')

            # P2P sending logic (replace with your actual implementation)
            self.p2p_factory.broadcast_spammer_info(serialized_data)  # Assuming this method exists

            deferred.callback("Data sent to P2P network")  # Resolve the Deferred
        except Exception as e:
            LOGGER.error("Error sending data to P2P network: %s", e)
            deferred.errback(e)  # Reject the Deferred