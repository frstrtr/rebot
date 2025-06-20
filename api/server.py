import uvicorn
import os
import logging

# This runner script assumes it's being run from the project root directory.
from api.external_api import app

if __name__ == "__main__":
    # Use environment variables for host and port, with defaults
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", 8000))
    
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Starting Rebot External API server on http://{host}:{port}")
    
    # To run this, you would execute `python -m api.server` from the /home/user0/rebot/ directory.
    # You will need to install fastapi and uvicorn: pip install fastapi "uvicorn[standard]"
    uvicorn.run("api.external_api:app", host=host, port=port, reload=True)