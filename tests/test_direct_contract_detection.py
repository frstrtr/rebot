#!/usr/bin/env python3
"""
Test TronScan API smart contract detection directly
"""
import sys
sys.path.append('/home/user0/Documents/GitHub/rebot')

from utils.tronscan import TronScanAPI

def test_direct_contract_detection():
    """Test the is_smart_contract function directly"""
    print("Testing TronScan API smart contract detection...")
    
    tron_client = TronScanAPI()
    
    # Test cases: [address, expected_type, description]
    test_cases = [
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", True, "USDT TRC20 Contract"),
        ("TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax", False, "Regular wallet address"),
        ("TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7", True, "Another known contract"),
        ("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", False, "Another wallet address"),
    ]
    
    for address, expected_is_contract, description in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {description}")
        print(f"Address: {address}")
        print(f"Expected: {'Contract' if expected_is_contract else 'Wallet'}")
        
        try:
            # Test is_smart_contract
            is_contract = tron_client.is_smart_contract(address)
            print(f"Detected: {'Contract' if is_contract else 'Wallet'}")
            
            # Get account info to see what data is available
            account_info = tron_client.get_account_info(address)
            if account_info:
                print(f"Account Type: {account_info.get('accountType', 'Unknown')}")
                print(f"Has Code: {'code' in account_info}")
                print(f"Has Contract: {'contract' in account_info}")
                print(f"Transaction Count: {account_info.get('totalTransactionCount', 0)}")
                
                # Show relevant fields for contract detection
                relevant_fields = ['accountType', 'code', 'codeHash', 'contract', 'totalTransactionCount']
                for field in relevant_fields:
                    if field in account_info:
                        print(f"  {field}: {account_info[field]}")
                
            else:
                print("No account info found")
                
            # Test contract info if it's supposed to be a contract
            if expected_is_contract:
                contract_info = tron_client.get_contract_info(address)
                if contract_info:
                    print(f"Contract Info Available: Yes")
                    print(f"Contract Type: {contract_info.get('contractType', 'Unknown')}")
                    print(f"Verified: {contract_info.get('verified', False)}")
                else:
                    print("Contract Info Available: No")
                    
            result = "✅ PASS" if is_contract == expected_is_contract else "❌ FAIL"
            print(f"Result: {result}")
            
        except Exception as e:
            print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    test_direct_contract_detection()
