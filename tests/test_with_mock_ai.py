#!/usr/bin/env python3
"""
Test script to verify AI analysis with mock response (to test the Basic AI Analysis mark)
"""
import requests
import json

def test_mock_ai_analysis():
    """Test by temporarily inserting a mock AI analysis into the database"""
    
    # First, let's insert a mock AI analysis directly into the database
    import sys
    import os
    sys.path.append('/home/user0/Documents/GitHub/rebot')
    
    from database import SessionLocal
    from database.models import CryptoAddress, MemoType
    from datetime import datetime, timezone
    from sqlalchemy import func
    
    # Create a mock AI analysis report with the Basic AI Analysis mark
    mock_report = """🤖 **Basic AI Analysis**

This TRON address shows moderate risk based on account age and transaction patterns. The address has been active for 6 months with 150 transactions and maintains a balance of 1000 TRX. No obvious red flags detected, but standard caution is advised."""
    
    db = SessionLocal()
    
    try:
        # Check if record exists
        test_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        existing_record = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == test_address.lower(),
            func.lower(CryptoAddress.blockchain) == "tron"
        ).first()
        
        if existing_record:
            # Update existing record with mock AI analysis
            existing_record.notes = mock_report
            existing_record.memo_type = MemoType.PUBLIC.value
            existing_record.risk_score = 0.65
            existing_record.updated_at = datetime.now(timezone.utc)
            print(f"✅ Updated existing record for {test_address}")
        else:
            # Create new record with mock AI analysis
            new_record = CryptoAddress(
                address=test_address,
                blockchain="tron",
                notes=mock_report,
                memo_type=MemoType.PUBLIC.value,
                risk_score=0.65,
                status="to_check",
                detected_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(new_record)
            print(f"✅ Created new record for {test_address}")
        
        db.commit()
        print("✅ Mock AI analysis inserted into database")
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        db.rollback()
    finally:
        db.close()
    
    # Now test the API endpoints
    print("\n" + "="*60)
    print("TESTING API ENDPOINTS WITH MOCK DATA")
    print("="*60)
    
    headers = {
        "X-API-Key": "a_very_secret_and_long_api_key_for_external_access",
        "Content-Type": "application/json"
    }
    
    data = {
        "crypto_address": test_address,
        "request_by_telegram_id": 123456789,
        "blockchain_type": "tron"
    }
    
    # Test /get-scam-analysis endpoint
    print("\n1. Testing /get-scam-analysis endpoint:")
    print("-" * 40)
    
    try:
        response = requests.post(
            "http://127.0.0.1:8000/get-scam-analysis",
            headers=headers,
            json=data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Address Analyzed: {result.get('address_analyzed')}")
            print(f"Risk Score: {result.get('risk_score')}")
            
            if result.get('scam_report'):
                print("\nSCAM REPORT:")
                print("-" * 40)
                print(result['scam_report'])
                print("-" * 40)
                
                if "🤖 **Basic AI Analysis**" in result['scam_report']:
                    print("\n✅ SUCCESS: Report contains the 'Basic AI Analysis' mark!")
                else:
                    print("\n❌ MISSING: Report does not contain the 'Basic AI Analysis' mark")
            else:
                print("No scam report found")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test /analyze-scam endpoint (should return existing analysis)
    print("\n2. Testing /analyze-scam endpoint:")
    print("-" * 40)
    
    try:
        response = requests.post(
            "http://127.0.0.1:8000/analyze-scam",
            headers=headers,
            json=data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Address Analyzed: {result.get('address_analyzed')}")
            print(f"Risk Score: {result.get('risk_score')}")
            
            if result.get('scam_report'):
                print("\nSCAM REPORT:")
                print("-" * 40)
                print(result['scam_report'])
                print("-" * 40)
                
                if "🤖 **Basic AI Analysis**" in result['scam_report']:
                    print("\n✅ SUCCESS: Report contains the 'Basic AI Analysis' mark!")
                else:
                    print("\n❌ MISSING: Report does not contain the 'Basic AI Analysis' mark")
            else:
                print("No scam report found")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_mock_ai_analysis()
