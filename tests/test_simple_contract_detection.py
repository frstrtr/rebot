#!/usr/bin/env python3
"""
Simple test for smart contract detection
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.tronscan import TronScanAPI

def test_contract_detection():
    client = TronScanAPI()
    
    # Test cases
    addresses = [
        ("TLyqzVGLV1srkB7dToTAEqgDSfPtXRJZYH", "Super Representative - should be wallet"),
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "USDT Contract - should be contract"),
    ]
    
    for address, description in addresses:
        print(f"\nTesting: {description}")
        print(f"Address: {address}")
        
        try:
            is_contract = client.is_smart_contract(address)
            print(f"Detected as: {'Smart Contract' if is_contract else 'Wallet'}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_contract_detection()
