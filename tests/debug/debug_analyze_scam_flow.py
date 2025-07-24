#!/usr/bin/env python3
"""
Debug script to test the analyze_scam flow and identify the tron_data scope issue.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI
from genai.vertex_ai_client import VertexAIClient

async def debug_analyze_scam_flow():
    """Debug the exact flow that's causing the tron_data error."""
    
    test_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT contract
    
    print(f"🔍 Debugging analyze_scam flow for: {test_address}")
    
    try:
        tron_client = TronScanAPI()
        vertex_client = VertexAIClient()

        # First, check if this is a smart contract or regular address
        loop = asyncio.get_running_loop()
        
        print("1. Checking if smart contract...")
        is_contract = await loop.run_in_executor(
            None, tron_client.is_smart_contract, test_address
        )
        print(f"   Result: {is_contract}")

        prompt = None
        
        if is_contract:
            print("2. Fetching contract-specific data...")
            # Fetch contract-specific data
            contract_data = await loop.run_in_executor(
                None, tron_client.get_contract_info, test_address
            )
            
            if contract_data:
                print("3. Building smart contract prompt...")
                # Create a focused prompt for smart contract analysis
                balance_trx = contract_data.get('balance', 0) / 1_000_000  # Convert SUN to TRX
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
                    f"Contract Address: {test_address}, "
                    f"Contract Type: {contract_type}, "
                    f"Creator: {creator}, "
                    f"Verified: {verified}, "
                    f"Balance: {balance_trx:.6f} TRX, "
                    f"Total transactions: {tx_count}, "
                    f"Creation time: {create_time}{token_details}. "
                    f"Provide a risk score (0.0-1.0) and brief scam analysis. "
                    f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                    f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                )
                print(f"   Generated prompt (length: {len(prompt)})")
            else:
                print("3. Contract data fetch failed, using fallback...")
                # Fall back to basic account info for contracts that don't have contract data
                tron_data = await loop.run_in_executor(
                    None, tron_client.get_basic_account_info, test_address
                )
                if tron_data:
                    balance_trx = tron_data.get('balance', 0) / 1_000_000
                    tx_count = tron_data.get('totalTransactionCount', 0)
                    create_time = tron_data.get('date_created')
                    
                    prompt = (
                        f"Analyze this TRON SMART CONTRACT for scam potential. "
                        f"Contract Address: {test_address}, "
                        f"Balance: {balance_trx:.6f} TRX, "
                        f"Total transactions: {tx_count}, "
                        f"Creation time: {create_time}. "
                        f"Note: Contract-specific data unavailable. "
                        f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                        f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                    )
                    print(f"   Generated fallback prompt (length: {len(prompt)})")
        else:
            print("2. Fetching wallet-specific data...")
            # Fetch wallet-specific data
            tron_data = await loop.run_in_executor(
                None, tron_client.get_basic_account_info, test_address
            )
            
            if tron_data:
                print("3. Building wallet prompt...")
                # Create a focused prompt for wallet address analysis
                balance_trx = tron_data.get('balance', 0) / 1_000_000  # Convert SUN to TRX
                tx_count = tron_data.get('totalTransactionCount', 0)
                create_time = tron_data.get('date_created')
                
                prompt = (
                    f"Analyze this TRON WALLET ADDRESS for scam potential. "
                    f"Address: {test_address}, "
                    f"Balance: {balance_trx:.6f} TRX, "
                    f"Total transactions: {tx_count}, "
                    f"Creation time: {create_time}. "
                    f"IMPORTANT: Start your analysis report with 'This is a WALLET address.' "
                    f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a WALLET address. [analysis here]\"}}"
                )
                print(f"   Generated wallet prompt (length: {len(prompt)})")

        if prompt:
            print("4. Sending prompt to AI...")
            ai_response = await vertex_client.generate_text(prompt)
            print(f"   AI response received (length: {len(ai_response) if ai_response else 0})")
            
            if ai_response:
                print("5. Processing AI response...")
                # Clean the AI response to handle markdown code blocks
                cleaned_response = ai_response.strip()
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]  # Remove ```json
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]  # Remove ```
                cleaned_response = cleaned_response.strip()
                
                print(f"   Cleaned response: {cleaned_response[:200]}...")
                
                try:
                    import json
                    ai_response_json = json.loads(cleaned_response)
                    risk_score = ai_response_json.get("risk_score")
                    scam_report = ai_response_json.get("report")
                    
                    print(f"   ✅ Parsed - Risk score: {risk_score}")
                    print(f"   ✅ Parsed - Report preview: {scam_report[:100]}...")
                    
                    return risk_score, scam_report
                    
                except Exception as e:
                    print(f"   ❌ Error parsing AI response: {e}")
            else:
                print("   ❌ No AI response received")
        else:
            print("   ❌ No prompt generated")
            
    except Exception as e:
        print(f"❌ Error in debug flow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_analyze_scam_flow())
