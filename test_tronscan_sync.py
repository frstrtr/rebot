#!/usr/bin/env python3
"""
Simple sync test of TronScan API
"""
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_tronscan_sync():
    """Test TronScan API synchronously"""
    address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT contract
    
    print(f"Testing TronScan API for {address}")
    
    try:
        # Create client with shorter timeout
        tron_client = TronScanAPI(timeout=5)
        
        print("Step 1: Testing smart contract detection...")
        is_contract = tron_client.is_smart_contract(address)
        print(f"Is contract: {is_contract}")
        
        if is_contract:
            print("Step 2: Testing contract info...")
            contract_data = tron_client.get_contract_info(address)
            if contract_data:
                print("Contract data retrieved:")
                for key, value in contract_data.items():
                    print(f"  {key}: {value}")
            else:
                print("No contract data returned")
        else:
            print("Step 2: Testing basic account info...")
            account_data = tron_client.get_basic_account_info(address)
            if account_data:
                print("Account data retrieved:")
                for key, value in account_data.items():
                    print(f"  {key}: {value}")
            else:
                print("No account data returned")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tronscan_sync()
