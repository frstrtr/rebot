#!/usr/bin/env python3
"""
Comprehensive test of all API endpoints with USDT smart contract
Tests the full pipeline: smart contract detection, data fetching, AI analysis
"""
import requests
import json
import time

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"

# USDT contract address for testing
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

def test_endpoint(endpoint, data, description):
    """Helper function to test an endpoint"""
    print(f"\n{'='*60}")
    print(f"TESTING: {description}")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*60}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        start_time = time.time()
        response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=data, timeout=120)
        elapsed_time = time.time() - start_time
        
        print(f"⏱️  Response time: {elapsed_time:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"✅ SUCCESS: {response_data.get('message', 'OK')}")
            
            # Print key information
            print(f"📋 Address analyzed: {response_data.get('address_analyzed', 'N/A')}")
            print(f"🎯 Risk score: {response_data.get('risk_score', 'N/A')}")
            
            # Check for smart contract detection
            scam_report = response_data.get('scam_report', '')
            if scam_report:
                if "SMART CONTRACT" in scam_report.upper():
                    print("🤖 ✅ Smart contract correctly detected!")
                elif "WALLET" in scam_report.upper():
                    print("💳 ❌ Incorrectly detected as wallet")
                else:
                    print("❓ Address type not clearly stated")
                
                # Show report preview
                print(f"\n📝 Report preview:")
                report_lines = scam_report.split('\n')
                for line in report_lines[:5]:  # Show first 5 lines
                    print(f"   {line}")
                if len(report_lines) > 5:
                    print("   ... (truncated)")
            else:
                print("❌ No scam report in response")
                
            return response_data
        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out")
        return None
    except Exception as e:
        print(f"💥 Exception: {e}")
        return None

def main():
    print("🚀 COMPREHENSIVE SMART CONTRACT API TEST")
    print(f"🎯 Testing with USDT contract: {USDT_CONTRACT}")
    print(f"🌐 API Base URL: {BASE_URL}")
    print(f"🔑 Using API key: {API_KEY[:20]}...")
    
    # Test data for all endpoints
    request_id = int(time.time())  # Unique request ID to avoid cache
    
    # Test 1: /check-address endpoint
    check_data = {
        "crypto_address": USDT_CONTRACT,
        "request_by_telegram_id": request_id,
        "provided_by_telegram_id": request_id,
        "blockchain_type": "tron"
    }
    
    check_result = test_endpoint("/check-address", check_data, "Check Address Endpoint")
    
    # Test 2: /get-scam-analysis endpoint (should find nothing initially)
    get_data = {
        "crypto_address": USDT_CONTRACT,
        "request_by_telegram_id": request_id + 1,
        "blockchain_type": "tron"
    }
    
    get_result = test_endpoint("/get-scam-analysis", get_data, "Get Scam Analysis Endpoint (before analysis)")
    
    # Test 3: /analyze-scam endpoint (should perform fresh analysis)
    analyze_data = {
        "crypto_address": USDT_CONTRACT,
        "request_by_telegram_id": request_id + 2,
        "blockchain_type": "tron"
    }
    
    analyze_result = test_endpoint("/analyze-scam", analyze_data, "Analyze Scam Endpoint (fresh analysis)")
    
    # Test 4: /get-scam-analysis endpoint (should find the analysis now)
    get_data2 = {
        "crypto_address": USDT_CONTRACT,
        "request_by_telegram_id": request_id + 3,
        "blockchain_type": "tron"
    }
    
    get_result2 = test_endpoint("/get-scam-analysis", get_data2, "Get Scam Analysis Endpoint (after analysis)")
    
    # Test 5: /analyze-scam endpoint again (should return cached result)
    analyze_data2 = {
        "crypto_address": USDT_CONTRACT,
        "request_by_telegram_id": request_id + 4,
        "blockchain_type": "tron"
    }
    
    analyze_result2 = test_endpoint("/analyze-scam", analyze_data2, "Analyze Scam Endpoint (cached result)")
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 TEST SUMMARY")
    print(f"{'='*80}")
    
    tests = [
        ("✅ /check-address", check_result is not None),
        ("✅ /get-scam-analysis (before)", get_result is not None),
        ("✅ /analyze-scam (fresh)", analyze_result is not None),
        ("✅ /get-scam-analysis (after)", get_result2 is not None),
        ("✅ /analyze-scam (cached)", analyze_result2 is not None)
    ]
    
    passed = sum(1 for _, success in tests if success)
    total = len(tests)
    
    for test_name, success in tests:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Overall Result: {passed}/{total} tests passed")
    
    # Check smart contract detection specifically
    smart_contract_detected = False
    if analyze_result and analyze_result.get('scam_report'):
        if "SMART CONTRACT" in analyze_result['scam_report'].upper():
            smart_contract_detected = True
    
    print(f"🤖 Smart Contract Detection: {'✅ SUCCESS' if smart_contract_detected else '❌ FAILED'}")
    
    if passed == total and smart_contract_detected:
        print("\n🎉 ALL TESTS PASSED! Smart contract analysis is working correctly!")
    else:
        print(f"\n⚠️  Some tests failed. Please check the results above.")

if __name__ == "__main__":
    main()
