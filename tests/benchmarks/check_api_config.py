"""
Configuration helper for API testing.
Updates the test configuration based on your actual setup.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_configuration():
    """Check and display current configuration for testing."""
    print("🔧 API Testing Configuration Check")
    print("=" * 50)
    
    try:
        from config.config import Config
        
        # Check required configuration
        checks = [
            ("EXTERNAL_API_SECRET", Config.EXTERNAL_API_SECRET, "API Key for authentication"),
            ("BOT_USERNAME", Config.BOT_USERNAME, "Bot username for deeplinks"),
            ("GCP_PROJECT_ID", Config.GCP_PROJECT_ID, "Google Cloud Project ID"),
            ("GCP_LOCATION", Config.GCP_LOCATION, "Google Cloud Location"),
            ("VERTEX_AI_MODEL_NAME", Config.VERTEX_AI_MODEL_NAME, "Vertex AI Model Name"),
        ]
        
        print("📋 Configuration Status:")
        all_good = True
        
        for name, value, description in checks:
            status = "✅" if value else "❌"
            display_value = value if value else "NOT SET"
            if name == "EXTERNAL_API_SECRET" and value:
                display_value = f"{value[:8]}..." if len(value) > 8 else value
            print(f"   {status} {name}: {display_value}")
            print(f"      └─ {description}")
            if not value:
                all_good = False
        
        print(f"\n📊 Configuration Status: {'✅ Ready' if all_good else '❌ Needs attention'}")
        
        if Config.EXTERNAL_API_SECRET:
            print(f"\n🔑 Use this API key in your tests:")
            print(f"   API_KEY = \"{Config.EXTERNAL_API_SECRET}\"")
        
        # Check explorer configuration
        if hasattr(Config, 'EXPLORER_CONFIG') and Config.EXPLORER_CONFIG:
            print(f"\n🔍 Supported blockchains for explorer links:")
            for blockchain in Config.EXPLORER_CONFIG.keys():
                print(f"   • {blockchain}")
        
        return all_good
        
    except ImportError as e:
        print(f"❌ Failed to import configuration: {e}")
        return False
    except Exception as e:
        print(f"❌ Error checking configuration: {e}")
        return False

def generate_test_config():
    """Generate a test configuration file."""
    config_content = '''"""
Test configuration for external API tests.
Update these values based on your actual setup.
"""

# Update these values before running tests
API_BASE_URL = "http://localhost:8000"
API_KEY = "your-api-key-here"  # Replace with your actual API key

# Test addresses for different blockchains
TEST_ADDRESSES = {
    "tron": {
        "valid": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",  # USDT on TRON
        "description": "USDT contract on TRON"
    },
    "ethereum": {
        "valid": "0xA0b86a33E6411FfA6ef5EAaAa4FbC6eE8FE1a5E7",
        "description": "Example Ethereum address"
    },
    "bitcoin": {
        "valid": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "description": "Bitcoin Genesis address"
    }
}

# Test user IDs
TEST_TELEGRAM_IDS = {
    "valid": 123456789,
    "invalid_too_large": 999999999999,
    "invalid_too_small": 0
}
'''
    
    config_path = project_root / "tests" / "test_config.py"
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    print(f"📝 Generated test configuration at: {config_path}")
    print("   Edit this file to customize test parameters")

def main():
    """Main configuration check function."""
    print("External API Testing Configuration Helper")
    print()
    
    config_ok = check_configuration()
    
    print("\n" + "=" * 50)
    print("📝 Next Steps:")
    
    if config_ok:
        print("1. ✅ Configuration looks good!")
        print("2. 🚀 Start the API server: python run_api_server.py")
        print("3. 🧪 Run tests: python tests/test_external_api.py")
    else:
        print("1. ❌ Fix configuration issues above")
        print("2. 📝 Update config files with missing values")
        print("3. 🔄 Run this script again to verify")
    
    print("4. 📖 Check API docs at: http://localhost:8000/docs (when server is running)")
    
    # Optionally generate test config
    generate_test_config()

if __name__ == "__main__":
    main()
