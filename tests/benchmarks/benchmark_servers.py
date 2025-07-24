#!/usr/bin/env python3
"""
Performance comparison script for different API server configurations.
This script tests resource usage and response times for each server option.
"""
import os
import sys
import time
import psutil
import requests
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def get_process_stats(pid):
    """Get CPU and memory stats for a process."""
    try:
        process = psutil.Process(pid)
        return {
            'cpu_percent': process.cpu_percent(),
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'threads': process.num_threads()
        }
    except psutil.NoSuchProcess:
        return None

def test_server_performance(server_script, test_duration=30):
    """Test server performance for a given script."""
    print(f"\n{'='*60}")
    print(f"Testing: {server_script}")
    print(f"{'='*60}")
    
    # Start server
    env = os.environ.copy()
    env['SERVER_MODE'] = 'production'
    
    try:
        process = subprocess.Popen([
            sys.executable, server_script
        ], cwd=project_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait for server to start
        time.sleep(3)
        
        # Check if server is running
        try:
            response = requests.get("http://localhost:8000/docs", timeout=5)
            if response.status_code != 200:
                print("❌ Server not responding properly")
                return None
        except requests.RequestException:
            print("❌ Server not accessible")
            return None
        
        print("✅ Server started successfully")
        
        # Test API key (replace with your actual API key)
        api_key = "your_api_key_here"
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        
        # Performance test
        start_time = time.time()
        request_count = 0
        error_count = 0
        response_times = []
        
        cpu_samples = []
        memory_samples = []
        
        while time.time() - start_time < test_duration:
            try:
                # Sample system resources
                stats = get_process_stats(process.pid)
                if stats:
                    cpu_samples.append(stats['cpu_percent'])
                    memory_samples.append(stats['memory_mb'])
                
                # Make API request
                req_start = time.time()
                response = requests.post(
                    "http://localhost:8000/check-address",
                    headers=headers,
                    json={
                        "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                        "request_by_telegram_id": 123456789,
                        "provided_by_telegram_id": 123456789,
                        "blockchain_type": "tron"
                    },
                    timeout=5
                )
                req_time = time.time() - req_start
                response_times.append(req_time)
                
                if response.status_code != 200:
                    error_count += 1
                
                request_count += 1
                
                # Small delay between requests
                time.sleep(0.1)
                
            except requests.RequestException:
                error_count += 1
                time.sleep(0.1)
        
        # Calculate statistics
        avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
        avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        results = {
            'server': server_script,
            'duration': test_duration,
            'requests': request_count,
            'errors': error_count,
            'avg_cpu_percent': avg_cpu,
            'avg_memory_mb': avg_memory,
            'avg_response_time_ms': avg_response_time * 1000,
            'requests_per_second': request_count / test_duration
        }
        
        print(f"📊 Results:")
        print(f"   Requests: {request_count}")
        print(f"   Errors: {error_count}")
        print(f"   RPS: {results['requests_per_second']:.2f}")
        print(f"   Avg CPU: {avg_cpu:.2f}%")
        print(f"   Avg Memory: {avg_memory:.2f} MB")
        print(f"   Avg Response Time: {avg_response_time*1000:.2f} ms")
        
        return results
        
    except Exception as e:
        print(f"❌ Error testing server: {e}")
        return None
    
    finally:
        # Clean up
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            process.kill()

def main():
    """Run performance comparison for all server options."""
    print("🧪 API Server Performance Comparison")
    print("This will test different server configurations for resource usage.")
    
    # Test only if we have the config files
    servers_to_test = [
        "api/server_minimal.py",
        "api/server_lightweight.py",
        "api/server.py"  # Original
    ]
    
    results = []
    
    for server in servers_to_test:
        server_path = project_root / server
        if server_path.exists():
            result = test_server_performance(str(server_path))
            if result:
                results.append(result)
        else:
            print(f"⚠️  Server script not found: {server}")
    
    # Summary
    if results:
        print(f"\n{'='*80}")
        print("📈 PERFORMANCE SUMMARY")
        print(f"{'='*80}")
        print(f"{'Server':<25} {'CPU %':<10} {'Memory MB':<12} {'RPS':<8} {'Resp Time ms':<12}")
        print("-" * 80)
        
        for result in results:
            server_name = result['server'].split('/')[-1]
            print(f"{server_name:<25} {result['avg_cpu_percent']:<10.2f} {result['avg_memory_mb']:<12.2f} {result['requests_per_second']:<8.2f} {result['avg_response_time_ms']:<12.2f}")

if __name__ == "__main__":
    main()
