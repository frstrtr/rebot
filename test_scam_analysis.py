#!/usr/bin/env python3
"""
Test script to check the /analyze-scam endpoint and see the simplified AI analysis reports
"""
import requests
import json

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"

def test_analyze_scam():
    """Test the analyze-scam endpoint"""
    print("Testing /analyze-scam endpoint...")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Test with a new TRON address to see corrected creation time
    data = {
        "crypto_address": "TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax",
        "request_by_telegram_id": 123456789,
        "blockchain_type": "tron"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/analyze-scam", headers=headers, json=data, timeout=60)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"\nResponse JSON:")
            print(json.dumps(response_data, indent=2))
            
            # Check specifically for the scam report
            if "scam_report" in response_data and response_data["scam_report"]:
                print(f"\n" + "="*60)
                print("SCAM REPORT CONTENT:")
                print("="*60)
                print(response_data["scam_report"])
                print("="*60)
                
                # Check if it has the "Basic AI Analysis" mark
                if "🤖 **Basic AI Analysis**" in response_data["scam_report"]:
                    print("\n✅ SUCCESS: Report contains the 'Basic AI Analysis' mark!")
                else:
                    print("\n❌ MISSING: Report does not contain the 'Basic AI Analysis' mark")
            else:
                print("\n❌ No scam report found in response")
                
        else:
            print(f"Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out - AI analysis may take time")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_analyze_scam()
