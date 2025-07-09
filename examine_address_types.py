#!/usr/bin/env python3
"""
Examine TronScan API responses for different address types
"""
import sys
sys.path.append('/home/user0/Documents/GitHub/rebot')

from utils.tronscan import TronScanAPI
import json

def examine_address_types():
    """Examine the raw API responses for different address types"""
    print("Examining TronScan API responses for different address types...")
    
    tron_client = TronScanAPI()
    
    # Known addresses
    addresses = [
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "USDT TRC20 Contract"),
        ("TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", "Regular wallet address"),
        ("TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7", "Another address"),
        ("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", "Another address"),
    ]
    
    for address, description in addresses:
        print(f"\n{'='*80}")
        print(f"Address: {address}")
        print(f"Description: {description}")
        print(f"{'='*80}")
        
        try:
            # Get account info
            account_info = tron_client.get_account_info(address)
            if account_info:
                print(f"Account Info:")
                print(json.dumps(account_info, indent=2, default=str))
            
            # Try to get contract info
            print(f"\nContract Info:")
            contract_info = tron_client.get_contract_info(address)
            if contract_info:
                print(json.dumps(contract_info, indent=2, default=str))
            else:
                print("No contract info available")
                
            # Try to get token info
            print(f"\nToken Info:")
            token_endpoint = f"{tron_client.base_url}/token_trc20"
            token_params = {"contract": address}
            
            token_response = tron_client.session.get(token_endpoint, params=token_params, timeout=tron_client.timeout)
            if token_response.status_code == 200:
                token_data = token_response.json()
                print(json.dumps(token_data, indent=2, default=str))
            else:
                print(f"No token info (status: {token_response.status_code})")
                
        except Exception as e:
            print(f"Error examining {address}: {e}")

if __name__ == "__main__":
    examine_address_types()
