#!/usr/bin/env python3
"""
Test just the smart contract detection and prompt generation
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI

def test_contract_analysis():
    """Test just the TronScan part of smart contract analysis"""
    address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    print(f"🔍 TESTING SMART CONTRACT DETECTION AND PROMPT GENERATION")
    print(f"Address: {address}")
    print("=" * 60)
    
    try:
        # Step 1: Initialize client
        print("1. Initializing TronScan client...")
        tron_client = TronScanAPI(timeout=10)
        print("✅ TronScan client initialized")
        
        # Step 2: Check if it's a smart contract
        print("\n2. Checking if address is a smart contract...")
        is_contract = tron_client.is_smart_contract(address)
        print(f"✅ Is smart contract: {is_contract}")
        
        if is_contract:
            # Step 3: Get contract data
            print("\n3. Fetching contract data...")
            contract_data = tron_client.get_contract_info(address)
            
            if contract_data:
                print(f"✅ Contract data fetched successfully")
                print(f"   Name: {contract_data.get('name')}")
                print(f"   Tag: {contract_data.get('tag1')}")
                print(f"   Verified: {contract_data.get('verified')}")
                print(f"   Balance: {contract_data.get('balance', 0) / 1_000_000:.6f} TRX")
                print(f"   Total transactions: {contract_data.get('totalTransactionCount', 0)}")
                
                # Step 4: Create the prompt
                print("\n4. Creating AI prompt...")
                balance_trx = contract_data.get('balance', 0) / 1_000_000
                tx_count = contract_data.get('totalTransactionCount', 0)
                create_time = contract_data.get('date_created')
                contract_type = contract_data.get('contractType', 'Unknown')
                creator = contract_data.get('creator', 'Unknown')
                verified = contract_data.get('verified', False)
                
                # Token-specific info if available
                token_info = contract_data.get('tokenInfo')
                token_details = ""
                if token_info:
                    symbol = token_info.get('symbol', 'Unknown')
                    name = token_info.get('name', 'Unknown')
                    token_details = f", Token: {name} ({symbol})"
                
                prompt = (
                    f"Analyze this TRON SMART CONTRACT for scam potential. "
                    f"Contract Address: {address}, "
                    f"Contract Type: {contract_type}, "
                    f"Creator: {creator}, "
                    f"Verified: {verified}, "
                    f"Balance: {balance_trx:.6f} TRX, "
                    f"Total transactions: {tx_count}, "
                    f"Creation time: {create_time}{token_details}. "
                    f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                    f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                )
                
                print("✅ Prompt created successfully")
                print(f"   Prompt length: {len(prompt)} characters")
                print("\n" + "=" * 60)
                print("GENERATED PROMPT:")
                print("=" * 60)
                print(prompt)
                print("=" * 60)
                
                print("\n🎉 SUCCESS! Smart contract detection and prompt generation working!")
                
            else:
                print("❌ No contract data received")
        else:
            print("❌ Address is not detected as a smart contract")
            # Let's also test with a wallet address
            print("\nTesting with wallet address for comparison...")
            wallet_data = tron_client.get_basic_account_info(address)
            if wallet_data:
                print(f"   Got wallet data: balance={wallet_data.get('balance', 0) / 1_000_000:.6f} TRX")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_contract_analysis()
