"""
Optimal API server configuration for production use.
This configuration minimizes resource usage while maintaining full functionality.
"""
import os
import uvicorn
from external_api import app

def run_optimal_server():
    """Run server with optimal production settings."""
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", 8000))
    
    print(f"🚀 Starting optimal production server on {host}:{port}")
    print("   ⚡ Optimized for minimal resource usage")
    print("   📊 Monitoring disabled for performance")
    print("   🔒 Error-level logging only")
    
    # Optimal production configuration
    uvicorn.run(
        app,                    # Direct app object (faster than string import)
        host=host,
        port=port,
        
        # Performance optimizations
        reload=False,           # ✅ Disable file watching (major CPU saver)
        access_log=False,       # ✅ Disable access logging (I/O saver)
        server_header=False,    # ✅ Disable server header (minor optimization)
        date_header=False,      # ✅ Disable date header (minor optimization)
        
        # Logging optimizations
        log_level="error",      # ✅ Only log errors (minimal logging)
        use_colors=False,       # ✅ Disable colors (minor optimization)
        
        # Worker configuration
        workers=1,              # ✅ Single worker for simple API
        
        # Connection optimizations
        backlog=64,            # ✅ Reasonable backlog size
        timeout_keep_alive=2,   # ✅ Short keep-alive timeout
        
        # SSL/TLS (disabled for local development)
        ssl_keyfile=None,
        ssl_certfile=None,
    )

def run_development_server():
    """Run server with development-friendly settings."""
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", 8000))
    
    print(f"🛠️  Starting development server on {host}:{port}")
    print("   🔄 Auto-reload enabled")
    print("   📝 Full logging enabled")
    print("   🔍 File watching enabled")
    
    # Development configuration
    uvicorn.run(
        app,
        host=host,
        port=port,
        
        # Development features
        reload=True,                           # ✅ Enable auto-reload
        reload_dirs=["./api", "./handlers"],   # ✅ Watch specific directories
        access_log=True,                       # ✅ Enable access logging
        log_level="info",                      # ✅ Detailed logging
        use_colors=True,                       # ✅ Colored output
        
        # Development-friendly timeouts
        timeout_keep_alive=5,
    )

if __name__ == "__main__":
    # Choose mode based on environment
    mode = os.environ.get("SERVER_MODE", "production").lower()
    
    if mode in ["dev", "development", "debug"]:
        run_development_server()
    else:
        run_optimal_server()
