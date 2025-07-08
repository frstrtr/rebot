#!/usr/bin/env python3
"""
Simple test for the analyze-scam endpoint
"""
import requests
import json

API_KEY = "a_very_secret_and_long_api_key_for_external_access"

def test_analyze_scam():
    url = "http://127.0.0.1:8000/analyze-scam"
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "request_by_telegram_id": 123456789
    }
    
    try:
        print(f"Testing {url}")
        print(f"Headers: {headers}")
        print(f"Data: {json.dumps(data, indent=2)}")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                response_json = response.json()
                print(f"Response JSON:\n{json.dumps(response_json, indent=2)}")
            except:
                print(f"Response Text: {response.text}")
        else:
            print(f"Error Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_analyze_scam()
