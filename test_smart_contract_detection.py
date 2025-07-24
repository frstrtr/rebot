#!/usr/bin/env python3
"""
Test script to specifically test smart contract vs wallet address detection
"""
import requests
import json
import time

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"

def test_smart_contract_detection():
    """Test the smart contract detection logic"""
    print("Testing smart contract vs wallet address detection...")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Test cases: [address, expected_type, description]
    test_cases = [
        # Known TRON smart contract addresses
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "smart_contract", "USDT TRC20 Contract"),
        ("TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7", "smart_contract", "Another known contract"),
        ("TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", "smart_contract", "SunswapV2Router02 Contract"),
        # Known Super Representative addresses (should be treated as wallets)
        ("TLyqzVGLV1srkB7dToTAEqgDSfPtXRJZYH", "wallet", "Super Representative address"),
        ("TGj1Ej1qRzL9feLTLhjwgxXF4Ct6GTWg2U", "wallet", "Another Super Representative"),
        # Regular wallet addresses
        ("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", "wallet", "Regular wallet address"),
        ("TGzz8gjYiYRqpfmDwnLxfgPuLVNmpCswVp", "wallet", "Another regular wallet"),
    ]
    
    results = []
    
    for address, expected_type, description in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {description}")
        print(f"Address: {address}")
        print(f"Expected Type: {expected_type}")
        print(f"{'='*60}")
        
        data = {
            "crypto_address": address,
            "request_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/analyze-scam", headers=headers, json=data, timeout=90)
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Check the scam report for smart contract vs wallet indication
                scam_report = response_data.get("scam_report", "")
                if scam_report:
                    print(f"Status: {response_data.get('status', 'Unknown')}")
                    print(f"Risk Score: {response_data.get('risk_score', 'N/A')}")
                    print(f"Analysis Date: {response_data.get('analysis_date', 'N/A')}")
                    
                    # Check if the report clearly states wallet or smart contract
                    if "SMART CONTRACT" in scam_report.upper():
                        detected_type = "smart_contract"
                        print("✅ DETECTED: Smart Contract")
                    elif "WALLET" in scam_report.upper():
                        detected_type = "wallet"
                        print("✅ DETECTED: Wallet Address")
                    else:
                        detected_type = "unknown"
                        print("❌ UNCLEAR: Type not clearly stated in report")
                    
                    # Check if detection matches expectation
                    if detected_type == expected_type:
                        print("✅ SUCCESS: Detection matches expected type")
                        results.append({"address": address, "expected": expected_type, "detected": detected_type, "success": True})
                    else:
                        print(f"❌ MISMATCH: Expected {expected_type}, detected {detected_type}")
                        results.append({"address": address, "expected": expected_type, "detected": detected_type, "success": False})
                    
                    # Show relevant parts of the scam report
                    print(f"\nScam Report Preview:")
                    print(f"{'='*40}")
                    report_lines = scam_report.split('\n')
                    for line in report_lines[:8]:  # Show first 8 lines
                        print(line)
                    if len(report_lines) > 8:
                        print("... (truncated)")
                    print(f"{'='*40}")
                    
                else:
                    print("❌ ERROR: No scam report found in response")
                    results.append({"address": address, "expected": expected_type, "detected": "no_report", "success": False})
                    
            else:
                print(f"❌ HTTP Error {response.status_code}: {response.text}")
                results.append({"address": address, "expected": expected_type, "detected": "error", "success": False})
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out - AI analysis may take time")
            results.append({"address": address, "expected": expected_type, "detected": "timeout", "success": False})
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({"address": address, "expected": expected_type, "detected": "exception", "success": False})
        
        # Wait between requests to avoid rate limiting
        time.sleep(2)
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    successful_tests = sum(1 for r in results if r["success"])
    total_tests = len(results)
    
    print(f"Tests passed: {successful_tests}/{total_tests}")
    
    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status} {result['address']}: Expected {result['expected']}, Got {result['detected']}")
    
    if successful_tests == total_tests:
        print("\n🎉 All tests passed! Smart contract detection is working correctly.")
    else:
        print(f"\n⚠️  {total_tests - successful_tests} tests failed. Check the implementation.")

if __name__ == "__main__":
    test_smart_contract_detection()
