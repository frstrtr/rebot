#!/usr/bin/env python3
"""
Debug the contract endpoint for wallet addresses
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json

def test_contract_endpoint_for_wallet():
    """Test contract endpoint for wallet addresses"""
    base_url = "https://apilist.tronscan.org/api"
    
    # Test both a known contract and a wallet
    test_cases = [
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "USDT Contract"),
        ("TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", "Wallet Address")
    ]
    
    for address, description in test_cases:
        print(f"\n{'='*80}")
        print(f"Testing: {description}")
        print(f"Address: {address}")
        print(f"{'='*80}")
        
        contract_endpoint = f"{base_url}/contract"
        contract_params = {"contract": address}
        
        try:
            response = requests.get(contract_endpoint, params=contract_params, timeout=10)
            response.raise_for_status()
            
            contract_data = response.json()
            
            print(f"Response structure:")
            print(f"  Type: {type(contract_data)}")
            print(f"  Keys: {list(contract_data.keys())}")
            
            if "data" in contract_data:
                data_list = contract_data["data"]
                print(f"  Data type: {type(data_list)}")
                print(f"  Data length: {len(data_list) if isinstance(data_list, list) else 'N/A'}")
                
                if isinstance(data_list, list) and len(data_list) > 0:
                    contract_info = data_list[0]
                    print(f"  Contract info keys: {list(contract_info.keys())}")
                    
                    # Check specific fields
                    indicators = {
                        'name': contract_info.get('name'),
                        'tag1': contract_info.get('tag1'),
                        'creator': contract_info.get('creator'),
                        'tokenInfo': contract_info.get('tokenInfo'),
                        'methodMap': contract_info.get('methodMap'),
                        'description': contract_info.get('description'),
                        'verify_status': contract_info.get('verify_status')
                    }
                    
                    print(f"  Contract indicators:")
                    for key, value in indicators.items():
                        has_value = value is not None and value != "" and value != []
                        print(f"    {key}: {value} (has_value: {has_value})")
                    
                    # Test our logic
                    contract_indicators = [
                        contract_info.get('name'),
                        contract_info.get('tag1'),
                        contract_info.get('creator'),
                        contract_info.get('tokenInfo'),
                        contract_info.get('methodMap'),
                        contract_info.get('description'),
                    ]
                    
                    meaningful_indicators = [ind for ind in contract_indicators if ind]
                    print(f"  Meaningful indicators: {len(meaningful_indicators)}")
                    print(f"  Has verify_status: {'verify_status' in contract_info}")
                    
                    is_contract = bool(meaningful_indicators) or 'verify_status' in contract_info
                    print(f"  Would be classified as contract: {is_contract}")
                    
                else:
                    print(f"  No data in response or empty data list")
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_contract_endpoint_for_wallet()
