"""
Lightweight API server runner for production use.
Optimized for minimal resource usage while maintaining functionality.
"""
import os
import uvicorn

# Import the FastAPI app
from external_api import app

def run_production_server():
    """Run the server with production-optimized settings."""
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", 8000))
    
    # Production-optimized uvicorn settings
    uvicorn.run(
        app,  # Pass app directly instead of string (slight performance gain)
        host=host,
        port=port,
        reload=False,  # Disable reload for production (saves CPU)
        access_log=False,  # Disable access logging (saves I/O)
        log_level="warning",  # Only log warnings and errors
        workers=1,  # Single worker for simple API
        loop="asyncio",  # Use asyncio event loop (default, but explicit)
        # http="httptools",  # Use httptools for better performance (commented out - optional dependency)
    )

def run_development_server():
    """Run the server with development-friendly settings."""
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", 8000))
    
    # Development settings with minimal logging
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=True,  # Enable reload for development
        reload_dirs=["./api", "./handlers", "./database"],  # Limit reload scope
        log_level="info",
        access_log=True,
    )

if __name__ == "__main__":
    # Choose mode based on environment variable
    mode = os.environ.get("SERVER_MODE", "production").lower()
    
    if mode == "development":
        print("🛠️  Starting development server with auto-reload...")
        run_development_server()
    else:
        print("🚀 Starting production server (lightweight)...")
        run_production_server()
