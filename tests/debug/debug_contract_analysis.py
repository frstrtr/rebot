#!/usr/bin/env python3
"""
Debug smart contract detection step by step
"""
import sys
import os
import asyncio
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI
from genai.vertex_ai_client import VertexAIClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def debug_smart_contract_analysis():
    """Debug the smart contract analysis step by step"""
    address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT contract
    
    print(f"=== Debugging Smart Contract Analysis for {address} ===\n")
    
    try:
        # Step 1: Initialize clients
        print("Step 1: Initializing TronScan and AI clients...")
        tron_client = TronScanAPI()
        vertex_client = VertexAIClient()
        print("✅ Clients initialized\n")
        
        # Step 2: Check if it's a smart contract
        print("Step 2: Checking if address is a smart contract...")
        loop = asyncio.get_running_loop()
        is_contract = await loop.run_in_executor(
            None, tron_client.is_smart_contract, address
        )
        print(f"✅ Smart contract detection result: {is_contract}\n")
        
        if is_contract:
            # Step 3: Fetch contract data
            print("Step 3: Fetching contract-specific data...")
            contract_data = await loop.run_in_executor(
                None, tron_client.get_contract_info, address
            )
            
            if contract_data:
                print("✅ Contract data fetched successfully:")
                print(f"   - Address: {contract_data.get('address')}")
                print(f"   - Name: {contract_data.get('name')}")
                print(f"   - Tag: {contract_data.get('tag1')}")
                print(f"   - Creator: {contract_data.get('creator')}")
                print(f"   - Verified: {contract_data.get('verified')}")
                print(f"   - Balance: {contract_data.get('balance', 0) / 1_000_000:.6f} TRX")
                print(f"   - Transactions: {contract_data.get('totalTransactionCount', 0)}")
                print(f"   - Token Info: {contract_data.get('tokenInfo', {})}")
                print()
                
                # Step 4: Generate AI prompt
                print("Step 4: Generating AI prompt...")
                balance_trx = contract_data.get('balance', 0) / 1_000_000
                tx_count = contract_data.get('totalTransactionCount', 0)
                create_time = contract_data.get('date_created')
                contract_type = contract_data.get('contractType', 'Unknown')
                creator = contract_data.get('creator', 'Unknown')
                verified = contract_data.get('verified', False)
                
                token_info = contract_data.get('tokenInfo')
                token_details = ""
                if token_info:
                    symbol = token_info.get('symbol', 'Unknown')
                    name = token_info.get('name', 'Unknown')
                    total_supply = token_info.get('totalSupply', 'Unknown')
                    holder_count = token_info.get('holderCount', 'Unknown')
                    transfer_count = token_info.get('transferCount', 'Unknown')
                    vip = token_info.get('vip', False)
                    
                    token_details = (f", Token: {name} ({symbol}), "
                                   f"Total Supply: {total_supply}, "
                                   f"Holders: {holder_count}, "
                                   f"Transfers: {transfer_count}, "
                                   f"VIP Status: {vip}")
                
                prompt = (
                    f"Analyze this TRON SMART CONTRACT for scam potential. "
                    f"Contract Address: {address}, "
                    f"Contract Type: {contract_type}, "
                    f"Creator: {creator}, "
                    f"Verified: {verified}, "
                    f"Balance: {balance_trx:.6f} TRX, "
                    f"Total transactions: {tx_count}, "
                    f"Creation time: {create_time}{token_details}. "
                    f"Provide a risk score (0.0-1.0) and brief scam analysis. "
                    f"Focus on: contract verification status, creator reputation, "
                    f"token economics (if applicable), transaction patterns, "
                    f"unusual contract behavior. Consider: unverified contracts are higher risk, "
                    f"contracts with excessive permissions are suspicious, "
                    f"tokens with unfair distribution may be scams. "
                    f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                    f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                )
                
                print("✅ AI prompt generated:")
                print(f"   Length: {len(prompt)} characters")
                print(f"   Preview: {prompt[:200]}...")
                print()
                
                # Step 5: Get AI analysis
                print("Step 5: Getting AI analysis...")
                ai_response = await vertex_client.generate_text(prompt)
                
                if ai_response:
                    print("✅ AI response received:")
                    print(f"   Length: {len(ai_response)} characters")
                    print(f"   Response: {ai_response}")
                    print()
                    
                    # Step 6: Parse AI response
                    print("Step 6: Parsing AI response...")
                    try:
                        # Clean the AI response
                        cleaned_response = ai_response.strip()
                        if cleaned_response.startswith('```json'):
                            cleaned_response = cleaned_response[7:]
                        if cleaned_response.endswith('```'):
                            cleaned_response = cleaned_response[:-3]
                        cleaned_response = cleaned_response.strip()
                        
                        import json
                        ai_response_json = json.loads(cleaned_response)
                        risk_score = ai_response_json.get("risk_score")
                        scam_report = ai_response_json.get("report")
                        
                        print("✅ AI response parsed successfully:")
                        print(f"   Risk Score: {risk_score}")
                        print(f"   Report: {scam_report}")
                        
                        # Check if report starts with correct identifier
                        if scam_report and "This is a SMART CONTRACT address" in scam_report:
                            print("✅ Report correctly identifies as SMART CONTRACT")
                        else:
                            print("❌ Report does NOT identify as SMART CONTRACT")
                            
                    except Exception as parse_err:
                        print(f"❌ Error parsing AI response: {parse_err}")
                        print(f"   Raw response: {ai_response}")
                        
                else:
                    print("❌ No AI response received")
                    
            else:
                print("❌ Failed to fetch contract data")
                
        else:
            print("❌ Address was not detected as a smart contract")
            
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_smart_contract_analysis())
