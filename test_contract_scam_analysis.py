#!/usr/bin/env python3
"""
Test script specifically for smart contract scam analysis
"""
import requests
import json
import time

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"

def test_smart_contract_analysis():
    """Test smart contract scam analysis with known contract addresses"""
    print("Testing smart contract scam analysis...")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Known smart contract addresses for testing
    smart_contracts = [
        {
            "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "name": "USDT TRC20 Contract",
            "description": "Official Tether USD contract - should be low risk"
        },
        {
            "address": "TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", 
            "name": "SunswapV2Router02",
            "description": "SunSwap DEX router contract - should be low risk"
        },
        {
            "address": "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7",
            "name": "Unknown Contract",
            "description": "Unknown contract - risk level to be determined"
        }
    ]
    
    results = []
    
    for contract in smart_contracts:
        print(f"\n{'='*80}")
        print(f"Testing Smart Contract: {contract['name']}")
        print(f"Address: {contract['address']}")
        print(f"Description: {contract['description']}")
        print(f"{'='*80}")
        
        # Use a unique telegram ID to potentially bypass some caching
        telegram_id = int(time.time()) % 1000000000
        
        data = {
            "crypto_address": contract['address'],
            "request_by_telegram_id": telegram_id,
            "blockchain_type": "tron"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/analyze-scam", headers=headers, json=data, timeout=120)
            
            if response.status_code == 200:
                response_data = response.json()
                
                print(f"✅ SUCCESS: Analysis completed")
                print(f"Status: {response_data.get('status', 'Unknown')}")
                print(f"Risk Score: {response_data.get('risk_score', 'N/A')}")
                print(f"Analysis Date: {response_data.get('analysis_date', 'N/A')}")
                
                # Check the scam report content
                scam_report = response_data.get("scam_report", "")
                if scam_report:
                    print(f"\n📋 SCAM REPORT:")
                    print(f"{'='*60}")
                    
                    # Check if it properly identifies as smart contract
                    if "SMART CONTRACT" in scam_report.upper():
                        print("✅ CORRECTLY IDENTIFIED: Smart Contract")
                    elif "WALLET" in scam_report.upper():
                        print("❌ INCORRECTLY IDENTIFIED: Wallet (should be contract)")
                    else:
                        print("❓ UNCLEAR: Address type not clearly stated")
                    
                    # Show the full report
                    print(f"\n{scam_report}")
                    print(f"{'='*60}")
                    
                    # Store result for summary
                    results.append({
                        "address": contract['address'],
                        "name": contract['name'],
                        "risk_score": response_data.get('risk_score'),
                        "correctly_identified": "SMART CONTRACT" in scam_report.upper(),
                        "success": True
                    })
                    
                else:
                    print("❌ ERROR: No scam report found in response")
                    results.append({
                        "address": contract['address'],
                        "name": contract['name'],
                        "risk_score": None,
                        "correctly_identified": False,
                        "success": False
                    })
                    
            else:
                print(f"❌ HTTP ERROR {response.status_code}: {response.text}")
                results.append({
                    "address": contract['address'],
                    "name": contract['name'],
                    "risk_score": None,
                    "correctly_identified": False,
                    "success": False
                })
                
        except requests.exceptions.Timeout:
            print("⏰ REQUEST TIMEOUT: Analysis taking longer than 2 minutes")
            results.append({
                "address": contract['address'],
                "name": contract['name'],
                "risk_score": None,
                "correctly_identified": False,
                "success": False
            })
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({
                "address": contract['address'],
                "name": contract['name'],
                "risk_score": None,
                "correctly_identified": False,
                "success": False
            })
        
        # Wait between requests to avoid overwhelming the API
        print("\n⏳ Waiting 3 seconds before next test...")
        time.sleep(3)
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 SUMMARY OF SMART CONTRACT ANALYSIS TESTS")
    print(f"{'='*80}")
    
    successful_tests = sum(1 for r in results if r["success"] and r["correctly_identified"])
    total_tests = len(results)
    
    print(f"Tests completed: {total_tests}")
    print(f"Successful analyses: {sum(1 for r in results if r['success'])}")
    print(f"Correctly identified as contracts: {sum(1 for r in results if r['correctly_identified'])}")
    print(f"Overall success rate: {successful_tests}/{total_tests}")
    
    print(f"\n📋 DETAILED RESULTS:")
    for result in results:
        status = "✅ PASS" if result["success"] and result["correctly_identified"] else "❌ FAIL"
        risk = result["risk_score"] if result["risk_score"] is not None else "N/A"
        identified = "✅ Contract" if result["correctly_identified"] else "❌ Not Contract"
        print(f"{status} {result['name'][:30]:30} | Risk: {str(risk):4} | ID: {identified}")
    
    if successful_tests == total_tests:
        print(f"\n🎉 ALL TESTS PASSED! Smart contract analysis is working correctly.")
    else:
        print(f"\n⚠️  Some tests failed. Check the implementation or API connectivity.")

if __name__ == "__main__":
    test_smart_contract_analysis()
