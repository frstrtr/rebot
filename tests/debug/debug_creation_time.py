#!/usr/bin/env python3
"""
Debug script to check USDT contract creation time data from TronScan
"""

from utils.tronscan import TronScanAPI
import json

def debug_creation_time():
    tron_client = TronScanAPI()
    address = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'  # USDT contract
    
    print(f"🔍 DEBUGGING CREATION TIME FOR: {address}")
    print("=" * 60)
    
    print("\n📋 1. ACCOUNT INFO:")
    account_info = tron_client.get_account_info(address)
    if account_info:
        print(f"   Raw date_created: {account_info.get('date_created')}")
        print(f"   Type: {type(account_info.get('date_created'))}")
        
        # Check other time-related fields
        for key, value in account_info.items():
            if 'time' in key.lower() or 'date' in key.lower() or 'created' in key.lower():
                print(f"   {key}: {value} (type: {type(value)})")
        
        print(f"\n   Full account info keys: {list(account_info.keys())}")
    else:
        print("   ❌ No account info found")
    
    print("\n📋 2. CONTRACT INFO:")
    contract_info = tron_client.get_contract_info(address)
    if contract_info:
        print(f"   Contract date_created: {contract_info.get('date_created')}")
        print(f"   Type: {type(contract_info.get('date_created'))}")
        
        # Check other time-related fields in contract info
        for key, value in contract_info.items():
            if 'time' in key.lower() or 'date' in key.lower() or 'created' in key.lower():
                print(f"   {key}: {value} (type: {type(value)})")
        
        print(f"\n   Full contract info keys: {list(contract_info.keys())}")
    else:
        print("   ❌ No contract info found")
    
    print("\n📋 3. BASIC ACCOUNT INFO (for scam analysis):")
    basic_info = tron_client.get_basic_account_info(address)
    if basic_info:
        print(f"   createTime: {basic_info.get('createTime')}")
        print(f"   Type: {type(basic_info.get('createTime'))}")
        
        # Check other time-related fields
        for key, value in basic_info.items():
            if 'time' in key.lower() or 'date' in key.lower() or 'created' in key.lower():
                print(f"   {key}: {value} (type: {type(value)})")
    else:
        print("   ❌ No basic info found")
    
    print("\n📋 4. SMART CONTRACT DETECTION:")
    is_contract = tron_client.is_smart_contract(address)
    print(f"   Is smart contract: {is_contract}")

if __name__ == "__main__":
    debug_creation_time()
