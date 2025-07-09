#!/usr/bin/env python3
"""
Test AI analysis directly
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from genai.vertex_ai_client import VertexAIClient

async def test_ai():
    vertex_client = VertexAIClient()
    
    prompt = (
        "Analyze this TRON SMART CONTRACT for scam potential. "
        "Contract Address: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t, "
        "Contract Type: Unknown, "
        "Creator: Unknown, "
        "Verified: True, "
        "Balance: 1036894.68 TRX, "
        "Total transactions: 264000000000, "
        "Creation time: None, Token: Tether USD (USDT), "
        "Total Supply: Unknown, "
        "Holders: Unknown, "
        "Transfers: Unknown, "
        "VIP Status: True. "
        "IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
        "Respond in JSON format: {\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}"
    )
    
    print("Testing AI analysis...")
    try:
        result = await vertex_client.generate_text(prompt)
        print("AI Response:", result)
    except Exception as e:
        print("AI Error:", e)

if __name__ == "__main__":
    asyncio.run(test_ai())
