import asyncio
import json
import websockets

async def subscribe_to_websocket():
    """Subscribe to a WebSocket server and send a message."""
    uri = "ws://localhost:9000"  # Replace with your WebSocket server URI
    async with websockets.connect(uri) as websocket:
        # Send a message to the WebSocket server
        user_id = "7690064207"  # Replace with the actual user_id you want to check
        message = json.dumps({"user_id": user_id})
        await websocket.send(message)
        print(f"Sent: {message}")

        # Wait for a response from the server
        response = await websocket.recv()
        print(f"Received: {response}")

# Run the async function
asyncio.get_event_loop().run_until_complete(subscribe_to_websocket())
