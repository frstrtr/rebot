#!/usr/bin/env python3
"""
Debug script to test AI analysis step by step
"""
import os
import sys
import json
import requests
import asyncio
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/home/user0/Documents/GitHub/rebot')

def test_step_by_step():
    """Test each component step by step"""
    print("🔍 DEBUGGING AI ANALYSIS STEP BY STEP")
    print("=" * 60)
    
    # Step 1: Test basic imports
    print("\n1. Testing imports...")
    try:
        from genai.vertex_ai_client import VertexAIClient
        from utils.tronscan import TronScanAPI
        from database import SessionLocal
        from database.models import CryptoAddress
        print("✅ All imports successful")
    except Exception as e:
        print(f"❌ Import error: {e}")
        return
    
    # Step 2: Test database connection
    print("\n2. Testing database connection...")
    try:
        db = SessionLocal()
        # Test query
        count = db.query(CryptoAddress).count()
        print(f"✅ Database connected. Found {count} addresses")
        db.close()
    except Exception as e:
        print(f"❌ Database error: {e}")
        return
    
    # Step 3: Test TronScan API
    print("\n3. Testing TronScan API...")
    try:
        client = TronScanAPI()
        data = client.get_basic_account_info('TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t')
        print(f"✅ TronScan API working. Got data: {data}")
    except Exception as e:
        print(f"❌ TronScan API error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 4: Test Vertex AI client
    print("\n4. Testing Vertex AI client...")
    try:
        # Check environment variables first
        print(f"GOOGLE_APPLICATION_CREDENTIALS: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'Not set')}")
        
        client = VertexAIClient()
        print("✅ Vertex AI client created successfully")
        
        # Test async generation
        async def test_ai():
            try:
                response = await client.generate_text("Hello, this is a test")
                print(f"✅ AI Response: {response}")
                return response
            except Exception as e:
                print(f"❌ AI generation error: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        # Run the async test
        result = asyncio.run(test_ai())
        
    except Exception as e:
        print(f"❌ Vertex AI client error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 5: Test the actual API endpoint with verbose error handling
    print("\n5. Testing API endpoint with detailed error info...")
    
    # Create a simple test that mimics the endpoint logic
    try:
        from api.external_api import app
        print("✅ FastAPI app imported successfully")
        
        # Test the endpoint manually with more details
        headers = {
            "X-API-Key": "a_very_secret_and_long_api_key_for_external_access",
            "Content-Type": "application/json"
        }
        
        data = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        }
        
        print(f"Making request to: http://127.0.0.1:8000/analyze-scam")
        print(f"Headers: {headers}")
        print(f"Data: {data}")
        
        response = requests.post(
            "http://127.0.0.1:8000/analyze-scam",
            headers=headers,
            json=data,
            timeout=60
        )
        
        print(f"Status: {response.status_code}")
        print(f"Headers: {response.headers}")
        print(f"Response: {response.text}")
        
    except Exception as e:
        print(f"❌ API test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_step_by_step()
