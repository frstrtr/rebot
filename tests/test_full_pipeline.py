#!/usr/bin/env python3
"""
Comprehensive test of all API endpoints with smart contract address
"""
import requests
import json
import time

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"

# Test address - USDT TRC20 smart contract
SMART_CONTRACT_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

def test_endpoint(endpoint_name, url, method="GET", data=None, timeout=120):
    """Test a single endpoint and return the result"""
    print(f"\n{'='*80}")
    print(f"🔍 TESTING {endpoint_name}")
    print(f"{'='*80}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    if data:
        print(f"Data: {json.dumps(data, indent=2)}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    start_time = time.time()
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        
        elapsed_time = time.time() - start_time
        
        print(f"\n📊 RESPONSE:")
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed_time:.2f} seconds")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"\n📋 RESPONSE DATA:")
            print(json.dumps(response_data, indent=2))
            
            # Check for smart contract specific analysis
            if "scam_report" in response_data and response_data["scam_report"]:
                scam_report = response_data["scam_report"]
                
                # Check if it correctly identifies as smart contract
                if "SMART CONTRACT" in scam_report.upper():
                    print(f"\n✅ SUCCESS: Correctly identified as SMART CONTRACT")
                elif "WALLET" in scam_report.upper():
                    print(f"\n❌ ERROR: Incorrectly identified as WALLET")
                else:
                    print(f"\n⚠️  WARNING: Address type not clearly stated in report")
                
                # Check for AI analysis mark
                if "🤖 **Basic AI Analysis**" in scam_report:
                    print(f"✅ SUCCESS: Contains 'Basic AI Analysis' mark")
                else:
                    print(f"❌ MISSING: 'Basic AI Analysis' mark not found")
                
                # Show relevant parts of the report
                print(f"\n📝 SCAM REPORT PREVIEW:")
                print(f"{'='*60}")
                report_lines = scam_report.split('\n')
                for i, line in enumerate(report_lines[:10]):
                    print(f"{i+1:2}: {line}")
                if len(report_lines) > 10:
                    print("    ... (truncated)")
                print(f"{'='*60}")
            
            return True, response_data
            
        else:
            print(f"\n❌ ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False, None
            
    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        print(f"\n⏱️  TIMEOUT: Request timed out after {elapsed_time:.2f} seconds")
        return False, None
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n💥 EXCEPTION: {e} (after {elapsed_time:.2f} seconds)")
        return False, None

def main():
    """Run comprehensive test of all endpoints"""
    print(f"🚀 COMPREHENSIVE API TESTING WITH SMART CONTRACT")
    print(f"{'='*80}")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    print(f"Smart Contract Address: {SMART_CONTRACT_ADDRESS}")
    print(f"Test Description: USDT TRC20 Token Contract")
    
    results = []
    
    # Test 1: Check Address endpoint
    success, data = test_endpoint(
        "CHECK ADDRESS ENDPOINT",
        f"{BASE_URL}/check-address",
        "POST",
        {
            "crypto_address": SMART_CONTRACT_ADDRESS,
            "request_by_telegram_id": 100000001,
            "provided_by_telegram_id": 100000002,
            "blockchain_type": "tron"
        }
    )
    results.append(("check-address", success, data))
    
    # Test 2: Get Scam Analysis endpoint (should be empty initially)
    success, data = test_endpoint(
        "GET SCAM ANALYSIS ENDPOINT (Initial Check)",
        f"{BASE_URL}/get-scam-analysis",
        "POST",
        {
            "crypto_address": SMART_CONTRACT_ADDRESS,
            "request_by_telegram_id": 100000003,
            "blockchain_type": "tron"
        }
    )
    results.append(("get-scam-analysis-initial", success, data))
    
    # Test 3: Analyze Scam endpoint (this should trigger smart contract analysis)
    success, data = test_endpoint(
        "ANALYZE SCAM ENDPOINT (Fresh Analysis)",
        f"{BASE_URL}/analyze-scam",
        "POST",
        {
            "crypto_address": SMART_CONTRACT_ADDRESS,
            "request_by_telegram_id": 100000004,
            "blockchain_type": "tron"
        },
        timeout=180  # Longer timeout for AI analysis
    )
    results.append(("analyze-scam", success, data))
    
    # Test 4: Get Scam Analysis endpoint again (should now have cached results)
    time.sleep(2)  # Brief pause
    success, data = test_endpoint(
        "GET SCAM ANALYSIS ENDPOINT (After Analysis)",
        f"{BASE_URL}/get-scam-analysis",
        "POST",
        {
            "crypto_address": SMART_CONTRACT_ADDRESS,
            "request_by_telegram_id": 100000005,
            "blockchain_type": "tron"
        }
    )
    results.append(("get-scam-analysis-cached", success, data))
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*80}")
    
    for test_name, success, data in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        
        if success and data:
            # Check for smart contract specific indicators
            if "scam_report" in data and data["scam_report"]:
                if "SMART CONTRACT" in data["scam_report"].upper():
                    print(f"    📋 Smart contract correctly identified")
                elif "WALLET" in data["scam_report"].upper():
                    print(f"    ⚠️  Incorrectly identified as wallet")
                else:
                    print(f"    🤔 Address type unclear")
            
            if "risk_score" in data and data["risk_score"] is not None:
                print(f"    🎯 Risk score: {data['risk_score']}")
    
    # Final verification
    successful_tests = sum(1 for _, success, _ in results if success)
    total_tests = len(results)
    
    print(f"\n{'='*80}")
    if successful_tests == total_tests:
        print(f"🎉 ALL TESTS PASSED! ({successful_tests}/{total_tests})")
        print(f"✅ Smart contract detection and analysis pipeline is working correctly!")
    else:
        print(f"⚠️  {total_tests - successful_tests} tests failed out of {total_tests}")
        print(f"❌ Some issues detected in the pipeline")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
