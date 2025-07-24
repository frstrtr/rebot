#!/usr/bin/env python3
"""
Debug the smart contract analysis flow step by step
"""
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI
from genai.vertex_ai_client import VertexAIClient
import json

async def test_full_flow():
    """Test the complete smart contract analysis flow"""
    address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    print(f"🔍 TESTING FULL SMART CONTRACT ANALYSIS FLOW")
    print(f"Address: {address}")
    print("=" * 60)
    
    try:
        # Step 1: Initialize clients
        print("1. Initializing clients...")
        tron_client = TronScanAPI(timeout=10)
        vertex_client = VertexAIClient()
        print("✅ Clients initialized")
        
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
                print(f"   Creator: {contract_data.get('creator')}")
                print(f"   Token Info: {contract_data.get('tokenInfo')}")
                
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
                
                print("✅ Prompt created")
                print(f"   Prompt length: {len(prompt)} characters")
                print(f"   Prompt preview: {prompt[:200]}...")
                
                # Step 5: Get AI analysis
                print("\n5. Getting AI analysis...")
                ai_response = await vertex_client.generate_text(prompt)
                
                if ai_response:
                    print(f"✅ AI response received")
                    print(f"   Response length: {len(ai_response)} characters")
                    print(f"   Response preview: {ai_response[:200]}...")
                    
                    # Step 6: Parse AI response
                    print("\n6. Parsing AI response...")
                    try:
                        # Clean the AI response to handle markdown code blocks
                        cleaned_response = ai_response.strip()
                        if cleaned_response.startswith('```json'):
                            cleaned_response = cleaned_response[7:]  # Remove ```json
                        if cleaned_response.endswith('```'):
                            cleaned_response = cleaned_response[:-3]  # Remove ```
                        cleaned_response = cleaned_response.strip()
                        
                        print(f"   Cleaned response: {cleaned_response}")
                        
                        # Parse the AI's response
                        ai_response_json = json.loads(cleaned_response)
                        risk_score = ai_response_json.get("risk_score")
                        scam_report = ai_response_json.get("report")
                        
                        print(f"✅ AI response parsed successfully")
                        print(f"   Risk score: {risk_score}")
                        print(f"   Report preview: {scam_report[:200] if scam_report else 'None'}...")
                        
                        # Step 7: Add the analysis mark
                        if scam_report:
                            final_report = f"🤖 **Basic AI Analysis**\n\n{scam_report}"
                            print(f"✅ Final report created")
                            print(f"   Final report preview: {final_report[:200]}...")
                            
                            print("\n" + "=" * 60)
                            print("🎉 SUCCESS! Full analysis flow completed successfully!")
                            print("=" * 60)
                            print(f"FINAL ANALYSIS:")
                            print(f"Risk Score: {risk_score}")
                            print(f"Report:\n{final_report}")
                            
                        else:
                            print("❌ No report in AI response")
                            
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON parsing error: {e}")
                        print(f"   Raw response: {ai_response}")
                    except Exception as e:
                        print(f"❌ Error parsing AI response: {e}")
                else:
                    print("❌ No AI response received")
            else:
                print("❌ No contract data received")
        else:
            print("❌ Address is not a smart contract")
            
    except Exception as e:
        print(f"❌ Error in full flow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full_flow())
