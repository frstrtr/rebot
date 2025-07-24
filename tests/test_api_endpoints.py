#!/usr/bin/env python3
"""
Test script for the External API endpoints
"""
import requests
import json
import time

# API configuration
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "a_very_secret_and_long_api_key_for_external_access"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_endpoint(endpoint, method="GET", data=None, description=""):
    """Test a single endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing {method} {endpoint}")
    print(f"Description: {description}")
    print(f"{'='*60}")
    
    try:
        url = f"{BASE_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, headers=HEADERS)
        elif method == "POST":
            response = requests.post(url, headers=HEADERS, json=data)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        try:
            response_json = response.json()
            print(f"Response JSON:\n{json.dumps(response_json, indent=2)}")
        except:
            print(f"Response Text: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("Testing Rebot External API Endpoints")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    
    # Test 1: Check Address - Bitcoin address (should work)
    test_endpoint(
        "/check-address",
        method="POST",
        data={
            "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 987654321
        },
        description="Check Bitcoin address (Genesis block)"
    )
    
    # Test 2: Check Address - Ethereum address
    test_endpoint(
        "/check-address",
        method="POST",
        data={
            "crypto_address": "0x742d35Cc6634C0532925a3b8D91B7a7a1a4f5b0A",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 987654321
        },
        description="Check Ethereum address"
    )
    
    # Test 3: Check Address - TRON address
    test_endpoint(
        "/check-address",
        method="POST",
        data={
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 987654321
        },
        description="Check TRON address (USDT contract)"
    )
    
    # Test 4: Get Scam Analysis - should return 404 for non-existent analysis
    test_endpoint(
        "/get-scam-analysis",
        method="POST",
        data={
            "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "request_by_telegram_id": 123456789
        },
        description="Get scam analysis for Bitcoin address (should return 404)"
    )
    
    # Test 5: Analyze Scam - should trigger new analysis
    test_endpoint(
        "/analyze-scam",
        method="POST",
        data={
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789
        },
        description="Analyze TRON address for scam (should trigger AI analysis)"
    )
    
    # Test 6: Test without API key (should return 401)
    print(f"\n{'='*60}")
    print("Testing without API key (should return 401)")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/check-address",
            headers={"Content-Type": "application/json"},
            json={
                "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "request_by_telegram_id": 123456789,
                "provided_by_telegram_id": 987654321
            }
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
