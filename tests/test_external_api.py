"""
Test suite for the external API endpoints.
Tests various scenarios including address validation, risk scoring, and memo retrieval.
"""

import asyncio
import json
import requests
from datetime import datetime
from typing import Dict, Any

# Configuration - Update these values based on your setup
API_BASE_URL = "http://localhost:8000"  # Adjust port if different

# Function to read API key from config file
def get_api_key():
    """Read API key from config file."""
    import os
    from pathlib import Path
    
    # Try to read from config file first
    config_file = Path(__file__).parent.parent / "config" / "external_api_secret.txt"
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                api_key = f.read().strip()
                if api_key:
                    return api_key
        except Exception as e:
            print(f"Warning: Could not read API key from {config_file}: {e}")
    
    # Fallback to environment variable
    api_key = os.getenv("EXTERNAL_API_SECRET")
    if api_key:
        return api_key
    
    # Last resort: try to import from config
    try:
        import sys
        sys.path.append(str(Path(__file__).parent.parent))
        from config.config import Config
        if hasattr(Config, 'EXTERNAL_API_SECRET') and Config.EXTERNAL_API_SECRET:
            return Config.EXTERNAL_API_SECRET
    except Exception as e:
        print(f"Warning: Could not import API key from config: {e}")
    
    # If all else fails, return None
    return None

# Get API key
API_KEY = get_api_key()
if not API_KEY:
    print("❌ ERROR: Could not find API key!")
    print("   Please ensure one of the following:")
    print("   1. config/external_api_secret.txt exists and contains the API key")
    print("   2. EXTERNAL_API_SECRET environment variable is set")
    print("   3. Config.EXTERNAL_API_SECRET is properly configured")
    exit(1)

print(f"✅ API key loaded: {API_KEY[:10]}...")

HEADERS = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

class TestExternalAPI:
    """Test suite for external API functionality."""

    def test_api_health(self):
        """Test if the API is running and accessible."""
        try:
            response = requests.get(f"{API_BASE_URL}/docs")
            assert response.status_code == 200, "API docs should be accessible"
            print("✅ API is running and accessible")
        except requests.ConnectionError:
            raise ConnectionError("❌ API is not running or not accessible at the configured URL")

    def test_valid_tron_address(self):
        """Test with a valid TRON address."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",  # USDT on TRON
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["status"] == "OK", f"Expected OK status, got {data.get('status')}"
        assert data["blockchain_explorer_link"] is not None, "Should have explorer link"
        assert data["bot_deeplink"] is not None, "Should have bot deeplink"
        
        print(f"✅ Valid TRON address test passed")
        print(f"   Risk Score: {data.get('risk_score', 'N/A')}")
        print(f"   Public Memos: {len(data.get('public_memos', []))}")

    def test_valid_ethereum_address(self):
        """Test with a valid Ethereum address."""
        payload = {
            "crypto_address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",  # Real Ethereum address
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789,
            "blockchain_type": "ethereum"
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["status"] == "OK", f"Expected OK status, got {data.get('status')}"
        assert "etherscan" in data["blockchain_explorer_link"].lower(), "Should have Ethereum explorer link"
        
        print(f"✅ Valid Ethereum address test passed")

    def test_ambiguous_address_without_blockchain_hint(self):
        """Test address that could belong to multiple blockchains without hint."""
        payload = {
            "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Bitcoin Genesis address format
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789
            # No blockchain_type specified
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        data = response.json()
        
        if data["status"] == "CLARIFICATION_NEEDED":
            assert "possible_blockchains" in data, "Should include possible blockchains"
            assert len(data["possible_blockchains"]) > 1, "Should have multiple blockchain options"
            print(f"✅ Ambiguous address test passed - needs clarification")
            print(f"   Possible blockchains: {data['possible_blockchains']}")
        else:
            # Address might not be ambiguous in your implementation
            print(f"ℹ️  Address resolved to single blockchain: {data.get('status')}")

    def test_invalid_address_format(self):
        """Test with an invalid address format."""
        payload = {
            "crypto_address": "invalid_address_123",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        assert response.status_code == 200, "Should return 200 even for invalid addresses"
        
        data = response.json()
        assert data["status"] == "ERROR", f"Expected ERROR status, got {data.get('status')}"
        assert "not a valid" in data["message"].lower(), "Error message should mention invalid format"
        
        print(f"✅ Invalid address format test passed")

    def test_unauthorized_request(self):
        """Test request without API key."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789
        }
        
        # Request without API key
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers={"Content-Type": "application/json"}, 
                               json=payload)
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"✅ Unauthorized request test passed")

    def test_invalid_api_key(self):
        """Test request with invalid API key."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789
        }
        
        invalid_headers = {
            "X-API-KEY": "invalid-key",
            "Content-Type": "application/json"
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=invalid_headers, 
                               json=payload)
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"✅ Invalid API key test passed")

    def test_invalid_telegram_ids(self):
        """Test with invalid Telegram IDs."""
        # Test with Telegram ID too large
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 99999999999,  # Too large (over 10 billion)
            "provided_by_telegram_id": 123456789
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        assert response.status_code == 422, f"Expected 422 validation error, got {response.status_code}"
        
        print(f"✅ Invalid Telegram ID test passed")

    def test_wrong_blockchain_hint(self):
        """Test with wrong blockchain hint for an address."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",  # TRON address
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789,
            "blockchain_type": "bitcoin"  # Wrong blockchain
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        data = response.json()
        
        if data["status"] == "ERROR":
            assert "not a valid option" in data["message"], "Should indicate invalid blockchain option"
            print(f"✅ Wrong blockchain hint test passed")
        else:
            print(f"ℹ️  Address accepted with blockchain hint: {data.get('status')}")

    def test_response_structure(self):
        """Test that the response has all expected fields."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        }
        
        response = requests.post(f"{API_BASE_URL}/check-address", 
                               headers=HEADERS, 
                               json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        required_fields = [
            "status", "request_datetime", "bot_deeplink", 
            "blockchain_explorer_link", "public_memos"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check optional fields exist (even if None)
        optional_fields = ["message", "possible_blockchains", "risk_score", "risk_score_updated_at"]
        for field in optional_fields:
            assert field in data, f"Missing optional field: {field}"
        
        # Validate datetime format
        request_datetime = data["request_datetime"]
        datetime.fromisoformat(request_datetime.replace('Z', '+00:00'))  # Should not raise exception
        
        print(f"✅ Response structure test passed")

    def test_risk_score_consistency(self):
        """Test that risk scores are consistent across multiple requests."""
        payload = {
            "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "request_by_telegram_id": 123456789,
            "provided_by_telegram_id": 123456789,
            "blockchain_type": "tron"
        }
        
        # Make two requests
        response1 = requests.post(f"{API_BASE_URL}/check-address", 
                                headers=HEADERS, 
                                json=payload)
        
        response2 = requests.post(f"{API_BASE_URL}/check-address", 
                                headers=HEADERS, 
                                json=payload)
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Risk scores should be the same (cached)
        if data1.get("risk_score") is not None and data2.get("risk_score") is not None:
            assert data1["risk_score"] == data2["risk_score"], "Risk scores should be consistent"
            assert data1["risk_score_updated_at"] == data2["risk_score_updated_at"], "Update times should be the same"
            print(f"✅ Risk score consistency test passed")
        else:
            print(f"ℹ️  No risk score available for consistency test")

def run_tests():
    """Run all tests with proper error handling."""
    test_instance = TestExternalAPI()
    
    tests = [
        ("API Health Check", test_instance.test_api_health),
        ("Valid TRON Address", test_instance.test_valid_tron_address),
        ("Valid Ethereum Address", test_instance.test_valid_ethereum_address),
        ("Ambiguous Address", test_instance.test_ambiguous_address_without_blockchain_hint),
        ("Invalid Address Format", test_instance.test_invalid_address_format),
        ("Unauthorized Request", test_instance.test_unauthorized_request),
        ("Invalid API Key", test_instance.test_invalid_api_key),
        ("Invalid Telegram IDs", test_instance.test_invalid_telegram_ids),
        ("Wrong Blockchain Hint", test_instance.test_wrong_blockchain_hint),
        ("Response Structure", test_instance.test_response_structure),
        ("Risk Score Consistency", test_instance.test_risk_score_consistency),
    ]
    
    passed = 0
    failed = 0
    
    print("🧪 Starting External API Tests")
    print("=" * 50)
    
    for test_name, test_func in tests:
        try:
            print(f"\n🔄 Running: {test_name}")
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ Failed: {test_name}")
            print(f"   Error: {str(e)}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed. Check the configuration and API setup.")

if __name__ == "__main__":
    print("External API Test Suite")
    print("Make sure to:")
    print("1. Start your FastAPI server before running tests")
    print("2. Ensure your database and services are running")
    print("3. Check that config/external_api_secret.txt contains your API key")
    print()
    
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
