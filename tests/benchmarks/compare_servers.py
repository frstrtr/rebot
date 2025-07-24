#!/usr/bin/env python3
"""
Simple server performance comparison script.
Compares resource usage between different server configurations.
"""
import time
import psutil
import requests
import subprocess
import sys
import os
from pathlib import Path

def monitor_server_performance(server_cmd, test_duration=10):
    """Monitor server performance for given duration."""
    print(f"Testing: {' '.join(server_cmd)}")
    
    # Start server
    process = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    time.sleep(3)
    
    # Check if server is responding
    try:
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code != 200:
            print("❌ Server not responding")
            process.terminate()
            return None
    except:
        print("❌ Server not accessible")
        process.terminate()
        return None
    
    print("✅ Server started, monitoring...")
    
    # Monitor performance
    start_time = time.time()
    cpu_readings = []
    memory_readings = []
    
    try:
        while time.time() - start_time < test_duration:
            try:
                proc = psutil.Process(process.pid)
                cpu_readings.append(proc.cpu_percent())
                memory_readings.append(proc.memory_info().rss / 1024 / 1024)  # MB
                time.sleep(0.5)
            except psutil.NoSuchProcess:
                break
    except KeyboardInterrupt:
        pass
    
    # Calculate averages
    avg_cpu = sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0
    avg_memory = sum(memory_readings) / len(memory_readings) if memory_readings else 0
    
    # Cleanup
    process.terminate()
    process.wait()
    
    return {
        'avg_cpu': avg_cpu,
        'avg_memory': avg_memory,
        'max_memory': max(memory_readings) if memory_readings else 0
    }

def main():
    """Compare different server configurations."""
    print("🔍 Server Performance Comparison")
    print("="*50)
    
    # Test configurations
    configs = [
        {
            'name': 'Original Server (with reload)',
            'cmd': [sys.executable, 'run_api_server.py'],
            'description': 'Original uvicorn with reload=True'
        },
        {
            'name': 'Lightweight Server',
            'cmd': [sys.executable, 'api/server_lightweight.py'],
            'description': 'Optimized uvicorn with reload=False'
        },
        {
            'name': 'Minimal Server',
            'cmd': [sys.executable, 'api/server_minimal.py'],
            'description': 'Minimal uvicorn configuration'
        }
    ]
    
    results = []
    
    for config in configs:
        print(f"\n🧪 Testing: {config['name']}")
        print(f"   {config['description']}")
        
        # Skip if file doesn't exist
        if not Path(config['cmd'][1]).exists():
            print("   ⚠️  File not found, skipping")
            continue
        
        result = monitor_server_performance(config['cmd'], test_duration=10)
        
        if result:
            result['name'] = config['name']
            results.append(result)
            print(f"   📊 CPU: {result['avg_cpu']:.2f}%")
            print(f"   📊 Memory: {result['avg_memory']:.2f} MB")
            print(f"   📊 Peak Memory: {result['max_memory']:.2f} MB")
        else:
            print("   ❌ Test failed")
    
    # Summary
    if results:
        print(f"\n{'='*60}")
        print("📈 PERFORMANCE SUMMARY")
        print(f"{'='*60}")
        print(f"{'Server':<25} {'CPU %':<10} {'Memory MB':<12} {'Peak MB':<10}")
        print("-" * 60)
        
        for result in results:
            name = result['name'][:24]
            print(f"{name:<25} {result['avg_cpu']:<10.2f} {result['avg_memory']:<12.2f} {result['max_memory']:<10.2f}")
        
        # Find best performer
        best_cpu = min(results, key=lambda x: x['avg_cpu'])
        best_memory = min(results, key=lambda x: x['avg_memory'])
        
        print(f"\n🏆 Best CPU Performance: {best_cpu['name']} ({best_cpu['avg_cpu']:.2f}%)")
        print(f"🏆 Best Memory Performance: {best_memory['name']} ({best_memory['avg_memory']:.2f} MB)")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print("   • For production: Use lightweight server (reload=False)")
        print("   • For development: Use original server (reload=True)")
        print("   • For testing: Use minimal server")
        print("   • Consider gunicorn for high-traffic production")

if __name__ == "__main__":
    main()
