"""
Minimal API server runner using Python's built-in capabilities.
Extremely lightweight but suitable only for development/testing.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_minimal_server():
    """Run a minimal server using built-in Python capabilities."""
    try:
        # Try to use uvicorn with minimal configuration
        import uvicorn
        from api.external_api import app
        
        host = os.environ.get("API_HOST", "127.0.0.1")
        port = int(os.environ.get("API_PORT", 8000))
        
        print(f"🔧 Starting minimal server on {host}:{port}")
        print("⚠️  This is for development/testing only!")
        
        # Absolute minimal uvicorn configuration
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,
            log_level="error",  # Only errors
            access_log=False,
            server_header=False,
            date_header=False,
        )
        
    except ImportError:
        print("❌ Uvicorn not available. Cannot run minimal server.")
        sys.exit(1)

if __name__ == "__main__":
    run_minimal_server()
