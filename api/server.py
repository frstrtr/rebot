"""API server runner script for the Rebot project.
This script is designed to run the FastAPI application defined in `external_api.py`.
It uses Uvicorn as the ASGI server and allows for configuration via environment variables.
"""
import os
import logging
import uvicorn

# This runner script assumes it's being run from the project root directory.
from external_api import app

if __name__ == "__main__":
    # Use environment variables for host and port, with defaults
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", 8000))
    
    # Configure logging to include a timestamp
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # To run this, you would execute `python -m api.server` from the /home/user0/rebot/ directory.
    # You will need to install fastapi and uvicorn: pip install fastapi "uvicorn[standard]"
    # Pass log_config=None to prevent uvicorn from overriding the root logger configuration.
    uvicorn.run("api.external_api:app", host=host, port=port, reload=True, log_config=None)