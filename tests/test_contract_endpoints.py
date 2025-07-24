#!/usr/bin/env python3
"""
Test script to check TronScan contract-specific endpoints
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tronscan import TronScanAPI
import json

def test_contract_endpoints():
    """Test contract-specific endpoints"""
    client = TronScanAPI()
    
    # Test with known USDT contract
    usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    print(f"Testing contract-specific endpoint for USDT contract: {usdt_contract}")
    print(f"{'='*80}")
    
    # Test get_contract_info
    contract_info = client.get_contract_info(usdt_contract)
    if contract_info:
        print(f"Contract info found:")
        for key, value in contract_info.items():
            print(f"  - {key}: {value}")
    else:
        print("No contract info found")
    
    print(f"\n{'='*80}")
    print("Testing direct contract endpoint...")
    
    # Test direct API call to contract endpoint
    contract_endpoint = f"{client.base_url}/contract"
    contract_params = {"contract": usdt_contract}
    
    try:
        import requests
        response = requests.get(contract_endpoint, params=contract_params, timeout=10)
        response.raise_for_status()
        
        contract_data = response.json()
        print(f"Direct contract endpoint response:")
        print(f"Response type: {type(contract_data)}")
        if isinstance(contract_data, dict):
            print(f"Keys: {list(contract_data.keys())}")
            for key, value in contract_data.items():
                print(f"  - {key}: {value}")
        else:
            print(f"Response: {contract_data}")
    except Exception as e:
        print(f"Error calling contract endpoint: {e}")
    
    print(f"\n{'='*80}")
    print("Testing token_trc20 endpoint...")
    
    # Test token endpoint
    token_endpoint = f"{client.base_url}/token_trc20"
    token_params = {"contract": usdt_contract}
    
    try:
        response = requests.get(token_endpoint, params=token_params, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        print(f"Token endpoint response:")
        print(f"Response type: {type(token_data)}")
        if isinstance(token_data, dict):
            print(f"Keys: {list(token_data.keys())}")
            if "data" in token_data and token_data["data"]:
                token_info = token_data["data"][0]
                print(f"Token info keys: {list(token_info.keys())}")
                for key, value in token_info.items():
                    print(f"  - {key}: {value}")
        else:
            print(f"Response: {token_data}")
    except Exception as e:
        print(f"Error calling token endpoint: {e}")

if __name__ == "__main__":
    test_contract_endpoints()
