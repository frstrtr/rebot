"""API server runner script for the Rebot project.
This script is designed to run the FastAPI application defined in `external_api.py`.
It uses Uvicorn as the ASGI server and allows for configuration via environment variables.
"""
import os
# import logging
# import sys
import uvicorn

# This runner script assumes it's being run from the project root directory.
# from external_api import app

# Define a standard logging configuration dictionary for Uvicorn
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        # Configure the root logger to capture logs from other libraries
        "": {"handlers": ["default"], "level": "INFO"},
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


if __name__ == "__main__":
    # Use environment variables for host and port, with defaults
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", 8000))
    
    # To run this, you would execute `python -m api.server` from the /home/user0/rebot/ directory.
    # You will need to install fastapi and uvicorn: pip install fastapi "uvicorn[standard]"
    # Pass the custom logging configuration dictionary to uvicorn.
    uvicorn.run(
        "api.external_api:app", 
        host=host, 
        port=port, 
        reload=True, 
        log_config=LOGGING_CONFIG
    )