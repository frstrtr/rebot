#!/usr/bin/env python3
"""
Simple script to run the External API server for testing.
"""

import sys
import os
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    """Run the FastAPI server."""
    print("🚀 Starting External API Server for Testing")
    print("=" * 50)
    print("Server will run at: http://localhost:8000")
    print("API docs available at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Import after path setup
    from api.external_api import app
    
    # Run the server
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=False  # Disable reload for testing
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n💥 Failed to start server: {e}")
        sys.exit(1)
