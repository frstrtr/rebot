#!/usr/bin/env python3
"""
Test script to directly check TronScan API responses for different address types
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tronscan import TronScanAPI
import json

def test_tronscan_api():
    """Test TronScan API responses for different address types"""
    client = TronScanAPI()
    
    # Test addresses
    test_addresses = [
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "USDT TRC20 Contract"),
        ("TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", "Regular wallet address"),
        ("TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7", "Another test address"),
        ("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", "Another test address")
    ]
    
    for address, description in test_addresses:
        print(f"\n{'='*80}")
        print(f"Testing: {description}")
        print(f"Address: {address}")
        print(f"{'='*80}")
        
        # Test get_account_info
        account_info = client.get_account_info(address)
        if account_info:
            print(f"Account info found:")
            print(f"  - Type: {account_info.get('type', 'Not found')}")
            print(f"  - AccountType: {account_info.get('accountType', 'Not found')}")
            print(f"  - Balance: {account_info.get('balance', 'Not found')}")
            print(f"  - TotalTransactionCount: {account_info.get('totalTransactionCount', 'Not found')}")
            print(f"  - Date Created: {account_info.get('date_created', 'Not found')}")
            
            # Check for contract-specific fields
            contract_fields = ['contractInfo', 'bytecode', 'abi', 'code', 'codeHash']
            found_contract_fields = [field for field in contract_fields if field in account_info]
            if found_contract_fields:
                print(f"  - Contract-specific fields found: {found_contract_fields}")
            else:
                print(f"  - No contract-specific fields found")
            
            # Show first few keys of the response
            print(f"  - All keys in response: {list(account_info.keys())}")
        else:
            print("No account info found")
        
        # Test smart contract detection
        is_contract = client.is_smart_contract(address)
        print(f"Smart contract detection result: {is_contract}")
        
        # Test get_basic_account_info 
        basic_info = client.get_basic_account_info(address)
        if basic_info:
            print(f"Basic account info found:")
            print(f"  - Address: {basic_info.get('address', 'Not found')}")
            print(f"  - Balance: {basic_info.get('balance', 'Not found')}")
            print(f"  - CreateTime: {basic_info.get('createTime', 'Not found')}")
            print(f"  - TotalTransactionCount: {basic_info.get('totalTransactionCount', 'Not found')}")
            print(f"  - Token balances count: {len(basic_info.get('tokenBalances', []))}")
        else:
            print("No basic account info found")
        
        print(f"{'='*80}")

if __name__ == "__main__":
    test_tronscan_api()
