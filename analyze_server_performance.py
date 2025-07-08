#!/usr/bin/env python3
"""
Simple server performance analysis.
Analyzes why uvicorn might be causing heavy server load.
"""
import time
import requests
import subprocess
import sys
from pathlib import Path

def analyze_server_config(config_file):
    """Analyze server configuration for performance issues."""
    print(f"📋 Analyzing: {config_file}")
    
    if not Path(config_file).exists():
        print("   ❌ File not found")
        return
    
    with open(config_file, 'r') as f:
        content = f.read()
    
    issues = []
    optimizations = []
    
    # Check for performance issues
    if 'reload=True' in content:
        issues.append("🔴 reload=True - Causes high CPU usage monitoring file changes")
        optimizations.append("Set reload=False for production")
    
    if 'log_config=' in content or 'LOGGING_CONFIG' in content:
        issues.append("🟡 Complex logging configuration - Adds overhead")
        optimizations.append("Use simple log_level parameter instead")
    
    if 'access_log=True' in content or 'access_log' not in content:
        issues.append("🟡 Access logging enabled - Increases I/O")
        optimizations.append("Set access_log=False for production")
    
    if 'workers=' not in content:
        issues.append("🟡 Default worker configuration - May not be optimal")
        optimizations.append("Consider setting workers=1 for simple APIs")
    
    if '"uvicorn[standard]"' in content:
        issues.append("🟡 Standard uvicorn includes extra dependencies")
        optimizations.append("Use basic uvicorn for lighter footprint")
    
    # Print analysis
    if issues:
        print("   ⚠️  Performance Issues Found:")
        for issue in issues:
            print(f"      {issue}")
    else:
        print("   ✅ No obvious performance issues found")
    
    if optimizations:
        print("   💡 Suggested Optimizations:")
        for opt in optimizations:
            print(f"      • {opt}")
    
    print()

def test_server_responsiveness(server_name, test_requests=5):
    """Test server responsiveness with simple requests."""
    print(f"🧪 Testing responsiveness: {server_name}")
    
    api_key = "test_key"  # Replace with actual key for real testing
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    
    payload = {
        "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "request_by_telegram_id": 123456789,
        "provided_by_telegram_id": 123456789,
        "blockchain_type": "tron"
    }
    
    response_times = []
    
    for i in range(test_requests):
        try:
            start_time = time.time()
            response = requests.post(
                "http://localhost:8000/check-address",
                headers=headers,
                json=payload,
                timeout=10
            )
            response_time = time.time() - start_time
            response_times.append(response_time)
            
            print(f"   Request {i+1}: {response_time*1000:.2f}ms (Status: {response.status_code})")
            
        except requests.RequestException as e:
            print(f"   Request {i+1}: FAILED - {e}")
    
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        print(f"   📊 Average Response Time: {avg_time*1000:.2f}ms")
        
        if avg_time > 1.0:
            print("   ⚠️  Response time > 1 second - potential performance issue")
        elif avg_time > 0.5:
            print("   🟡 Response time > 500ms - could be optimized")
        else:
            print("   ✅ Good response times")
    
    print()

def main():
    """Analyze server configurations and provide recommendations."""
    print("🔍 Uvicorn Performance Analysis")
    print("="*50)
    
    # Analyze different server configurations
    configs = [
        'api/server.py',
        'api/server_lightweight.py', 
        'api/server_minimal.py',
        'run_api_server.py'
    ]
    
    for config in configs:
        analyze_server_config(config)
    
    # Test current server if running
    try:
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("🌐 Testing current running server...")
            test_server_responsiveness("Current Server")
    except:
        print("ℹ️  No server currently running on port 8000")
    
    # Provide general recommendations
    print("📋 GENERAL RECOMMENDATIONS FOR PRODUCTION:")
    print("=" * 50)
    print("1. 🚀 Use lightweight server configuration:")
    print("   - Set reload=False")
    print("   - Disable access logging")
    print("   - Use minimal log level (warning/error)")
    print("   - Pass app object directly instead of string")
    print()
    print("2. 🔧 Consider alternatives for high traffic:")
    print("   - Gunicorn with uvicorn workers")
    print("   - Hypercorn (alternative ASGI server)")
    print("   - nginx reverse proxy for static content")
    print()
    print("3. 📊 Monitor these metrics:")
    print("   - CPU usage (should be low when idle)")
    print("   - Memory usage (should be stable)")
    print("   - Response times (should be consistent)")
    print()
    print("4. 🛠️  Development vs Production:")
    print("   - Development: Use reload=True for convenience")
    print("   - Production: Use reload=False for performance")
    print("   - Testing: Use minimal configuration")

if __name__ == "__main__":
    main()
