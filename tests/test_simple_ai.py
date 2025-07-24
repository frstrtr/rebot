#!/usr/bin/env python3
"""
Simple test to trigger AI analysis
"""
import requests
import json

def test_simple_analyze():
    """Test analyze-scam with a simple TRON address"""
    
    # Use a different TRON address for testing
    test_address = "TLsV52sRDL79HXGGm9yzwKiVAvnpZXAeEA"  # Different TRON address
    
    response = requests.post(
        "http://127.0.0.1:8000/analyze-scam",
        headers={
            "X-API-Key": "a_very_secret_and_long_api_key_for_external_access",
            "Content-Type": "application/json"
        },
        json={
            "crypto_address": test_address,
            "request_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        },
        timeout=60  # Longer timeout for AI analysis
    )
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
        
        # Check the scam report
        if result.get("scam_report"):
            print("\n" + "="*60)
            print("SCAM REPORT WITH BASIC AI ANALYSIS MARK:")
            print("="*60)
            print(result["scam_report"])
            print("="*60)
            
            if "🤖 **Basic AI Analysis**" in result["scam_report"]:
                print("\n✅ SUCCESS: AI analysis report contains the Basic AI Analysis mark!")
            else:
                print("\n❌ MISSING: Basic AI Analysis mark not found")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_simple_analyze()
