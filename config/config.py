# config.py
"""Loads configuration settings for the bot, including admin IDs, API tokens, and explorer configurations."""

# standard library imports
import os
import logging
from typing import Optional, List
# third-party imports
from dotenv import load_dotenv
from aiogram.enums import ParseMode

load_dotenv()

class Config:
    PARSE_MODE = ParseMode.HTML
    MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, using a buffer
    LOG_FOLDER = "logs"  # Define the log folder name
    LOG_LEVEL = logging.DEBUG  # Define the global log level

    # ANSI Color Codes
    PURPLE = "\033[95m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RESET_COLOR = "\033[0m"  # Standardized name for reset

    # Bot identity
    BOT_USERNAME: Optional[str] = os.environ.get("BOT_USERNAME", "cryptoscamreportbot") # Load from .env or fallback

    ETH_USDC_CONTRACT_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    ETH_USDT_CONTRACT_ADDRESS = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    BSC_USDC_CONTRACT_ADDRESS = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
    BSC_USDT_CONTRACT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
    POLYGON_USDC_CONTRACT_ADDRESS = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359" # (POS) USDC
    POLYGON_USDT_CONTRACT_ADDRESS = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F" # (POS) USDT
    # ... add other contracts and chains

    @staticmethod
    def _load_admins(filename="admins.txt") -> List[int]:
        """Loads admin Telegram user IDs from a file."""
        admin_ids = []
        script_dir = os.path.dirname(__file__)
        file_path = os.path.join(script_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped_line = line.strip()
                    # Skip empty lines and lines that start with # (comments)
                    if not stripped_line or stripped_line.startswith("#"):
                        continue
                    if stripped_line.isdigit():
                        admin_ids.append(int(stripped_line))
                    else:
                        logging.warning(
                            f"Invalid entry in '{filename}': '{line}' is not a valid integer ID. Skipping."
                        )  # pylint: disable=logging-fstring-interpolation
        except FileNotFoundError:
            logging.warning(
                f"Admin file '{filename}' not found in {script_dir}. No admins will be loaded."
            )  # pylint: disable=logging-fstring-interpolation
        except OSError as e:
            logging.error(
                f"Error reading admin file '{filename}': {e}"
            )  # pylint: disable=logging-fstring-interpolation
        return admin_ids

    ADMINS = _load_admins()  # Load admin IDs when the class is defined

    @staticmethod
    def _load_api_token(env_var_name: str) -> Optional[str]:
        """Loads an API token from environment variable or .env file (via python-dotenv)."""
        token = os.environ.get(env_var_name)
        if not token:
            logging.warning(f"API token environment variable '{env_var_name}' not set. Token not loaded.")
        return token

    # External API Configurations
    EXTERNAL_API_SECRET = _load_api_token("EXTERNAL_API_SECRET")

    ETHERSCAN_API_KEY = _load_api_token("ETHERSCAN_API_KEY")  # Optional, can be None if not set
    # If targeting Etherscan API v2 specifically, it might be:
    ETHERSCAN_API_BASE_URL = "https://api.etherscan.io/v2/api"
    ETHERSCAN_CHAIN_ID = (
        "1"  # Chain ID for Ethereum Mainnet (default for EtherscanAPI client)
    )
    BSC_CHAIN_ID = "56"  # Chain ID for Binance Smart Chain

    ETHERSCAN_RATE_LIMIT_CALLS = 5  # Max calls
    ETHERSCAN_RATE_LIMIT_PERIOD = 1.0  # Per X seconds
    ETHERSCAN_REQUEST_RETRIES = 3  # Default number of retries on rate limit
    ETHERSCAN_REQUEST_BACKOFF_FACTOR = 0.5  # Default backoff factor for retries

    # Example for Sepolia Testnet:
    # ETHERSCAN_API_BASE_URL_SEPOLIA = "https://api-sepolia.etherscan.io/api"
    # ETHERSCAN_CHAIN_ID_SEPOLIA = "11155111"

    TRONSCAN_API_KEY = _load_api_token("TRONSCAN_API_KEY")
    TRONSCAN_API_BASE_URL = "https://apilist.tronscan.org/api/"

    # Groups of chains where addresses can have the same format,
    # potentially leading to ambiguity if the network isn't specified.
    # If an address is detected and could belong to multiple chains in a group,
    # the bot should ask for clarification.
    # Keys are group names (for internal reference), values are sets of lowercase chain identifiers.
    AMBIGUOUS_CHAIN_GROUPS = {
        "evm_compatible": {  # Ethereum Virtual Machine compatible chains
            "ethereum",
            "bsc",  # BNB Smart Chain
            "polygon",
            "avalanche",  # Avalanche C-Chain
            "arbitrum",  # Arbitrum One
            "optimism",
            # Add other EVM-compatible chains here if their addresses are identical
            # e.g., Fantom, Cronos, Harmony, Moonbeam, etc.
        }
        # You could add other groups if other address formats are shared, e.g.:
        # "cosmos_sdk_chains": {"cosmos", "osmosis", "juno"} # If their bech32 prefixes are sometimes ambiguous
    }

    EXPLORER_CONFIG = {
        "tron": {
            "name": "TronScan",
            "url_template": "https://tronscan.org/#/address/{address}",
            "api_base_url": TRONSCAN_API_BASE_URL,  # Assuming you have this defined
            "api_key_name_in_config": "TRONSCAN_API_KEY",  # Name of the attribute in Config
        },
        "ton": {
            "name": "TONScan",
            "url_template": "https://tonscan.org/address/{address}",
            # Add api_base_url and api_key_name_in_config if applicable
        },
        "bitcoin": {
            "name": "Blockchair (Bitcoin)",
            "url_template": "https://blockchair.com/bitcoin/address/{address}",
        },
        "ethereum": {  # EVM
            "name": "Etherscan",
            "url_template": "https://etherscan.io/address/{address}",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",
            "chain_id": 1,
        },
        "bsc": {  # EVM - BNB Smart Chain
            "name": "BscScan",
            "url_template": "https://bscscan.com/address/{address}",
            # "api_base_url": "https://api.bscscan.com/api",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",  # Assuming BscScan uses same key type or you have a specific one
            "chain_id": 56,
        },
        "polygon": {  # EVM
            "name": "PolygonScan",
            "url_template": "https://polygonscan.com/address/{address}",
            # "api_base_url": "https://api.polygonscan.com/api",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",  # Assuming PolygonScan uses same key type
            "chain_id": 137,
        },
        "avalanche": {  # EVM - Avalanche C-Chain
            "name": "Snowtrace",
            "url_template": "https://snowtrace.io/address/{address}",
            # "api_base_url": "https://api.snowtrace.io/api",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",  # Assuming Snowtrace uses same key type
            "chain_id": 43114,
        },
        "arbitrum": {  # EVM - Arbitrum One
            "name": "Arbiscan",
            "url_template": "https://arbiscan.io/address/{address}",
            # "api_base_url": "https://api.arbiscan.io/api",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",
            "chain_id": 42161,
        },
        "optimism": {  # EVM - Optimism
            "name": "Optimistic Etherscan",
            "url_template": "https://optimistic.etherscan.io/address/{address}",
            # "api_base_url": "https://api-optimistic.etherscan.io/api",
            "api_base_url": "https://api.etherscan.io/v2/api",  # Standard Etherscan API v2 base
            "api_key_name_in_config": "ETHERSCAN_API_KEY",
            "chain_id": 10,
        },
        "ripple": {
            "name": "XRPL Explorer (xrpscan)",
            "url_template": "https://xrpscan.com/account/{address}",
        },
        "stellar": {
            "name": "Stellar.Expert",
            "url_template": "https://stellar.expert/explorer/public/account/{address}",
        },
        "cosmos": {
            "name": "Mintscan (Cosmos Hub)",
            "url_template": "https://www.mintscan.io/cosmos/account/{address}",
        },
        "polkadot": {
            "name": "Subscan (Polkadot)",
            "url_template": "https://polkadot.subscan.io/account/{address}",
        },
        "algorand": {
            "name": "AlgoExplorer",
            "url_template": "https://algoexplorer.io/address/{address}",
        },
        # ... other chains
    }

    @staticmethod
    def _initialize_gcp_credentials(filename="gcp_credentials.txt"):
        """
        Initializes Google Cloud credentials.
        Tries to load a service account key path from a file.
        If the file exists, it sets the GOOGLE_APPLICATION_CREDENTIALS environment variable.
        Otherwise, it relies on the environment or Application Default Credentials (ADC).
        """
        script_dir = os.path.dirname(__file__)
        file_path = os.path.join(script_dir, filename)
        
        # First, check if the environment variable is already set. If so, respect it.
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            logging.info("Using existing GOOGLE_APPLICATION_CREDENTIALS environment variable.")
            return

        # If not set, try to load from the specified file.
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                credential_path = f.readline().strip()
            if credential_path:
                # Check if the path is valid before setting it
                if os.path.exists(credential_path):
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
                    logging.info(f"Loaded GCP credentials from '{filename}' and set environment variable.")
                else:
                    logging.error(f"GCP credential file path '{credential_path}' found in '{filename}' does not exist.")
            else:
                logging.warning(f"GCP credentials file '{filename}' is empty. Relying on other ADC methods.")
        except FileNotFoundError:
            logging.info(f"'{filename}' not found. Relying on environment or gcloud ADC for GCP authentication.")
        except OSError as e:
            logging.error(f"Error reading GCP credentials file '{filename}': {e}")

    # --- Consolidated Google Cloud Platform Configuration ---
    # These variables are used to initialize the Vertex AI SDK.
    GCP_PROJECT_ID: Optional[str] = os.environ.get(
        "GCP_PROJECT_ID", "multichat-bot-396516"
    )
    # Use 'global' for preview models, or a specific region like 'us-central1' for stable models.
    GCP_LOCATION: Optional[str] = os.environ.get(
        "GCP_LOCATION", "global"
    )
    VERTEX_AI_MODEL_NAME: Optional[str] = os.environ.get(
        "VERTEX_AI_MODEL_NAME", "gemini-2.5-flash-lite-preview-06-17"  # Default model name
    )

    # Run the GCP credential initialization when the Config class is loaded.
    _initialize_gcp_credentials()

    @staticmethod
    def get_log_file_path(filename="bot.log"):
        # Ensure the log folder exists
        log_folder_path = os.path.join(
            os.path.dirname(__file__), Config.LOG_FOLDER
        )  # Ensure log folder is relative to config.py
        if not os.path.exists(log_folder_path):
            os.makedirs(log_folder_path)
        return os.path.join(log_folder_path, filename)
