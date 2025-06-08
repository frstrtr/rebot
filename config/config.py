# config.py
"""Loads configuration settings for the bot, including admin IDs, API tokens, and explorer configurations."""


from aiogram.enums import ParseMode
import os
import logging
from typing import Optional


class Config:
    PARSE_MODE = ParseMode.HTML
    MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, using a buffer
    LOG_FOLDER = "logs"  # Define the log folder name
    LOG_LEVEL = logging.INFO  # Define the global log level

    # ANSI Color Codes
    PURPLE = '\033[95m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RESET_COLOR = '\033[0m'  # Standardized name for reset


    @staticmethod
    def _load_admins(filename="admins.txt"):
        """Loads admin IDs from a file, one ID per line."""
        admin_ids = []
        script_dir = os.path.dirname(__file__)
        file_path = os.path.join(script_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.isdigit():
                        admin_ids.append(int(line))
                    elif line:  # If line is not empty and not a digit
                        logging.warning(f"Invalid entry in '{filename}': '{line}' is not a valid integer ID. Skipping.")  # pylint: disable=logging-fstring-interpolation
        except FileNotFoundError:
            logging.warning(f"Admin file '{filename}' not found in {script_dir}. No admins will be loaded.")  # pylint: disable=logging-fstring-interpolation
        except OSError as e:
            logging.error(f"Error reading admin file '{filename}': {e}")  # pylint: disable=logging-fstring-interpolation
        return admin_ids

    ADMINS = _load_admins()  # Load admin IDs when the class is defined

    @staticmethod
    def _load_api_token(filename="tronscan_api_token.txt") -> Optional[str]:
        """Loads an API token from the first line of a file."""
        token = None
        script_dir = os.path.dirname(__file__)
        file_path = os.path.join(script_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                token = f.readline().strip()
            if not token:
                logging.warning(f"Token file '{filename}' found in {script_dir} but is empty.")  # pylint: disable=logging-fstring-interpolation
                return None
        except FileNotFoundError:
            logging.warning(f"API token file '{filename}' not found in {script_dir}. Token not loaded.")  # pylint: disable=logging-fstring-interpolation
        except OSError as e:
            logging.error(f"Error reading API token file '{filename}': {e}")  # pylint: disable=logging-fstring-interpolation
        return token


    # External API Configurations
    ETHERSCAN_API_KEY = _load_api_token("etherscan_api_token.txt")  # Optional, can be None if not set
    ETHERSCAN_API_BASE_URL = "https://api.etherscan.io/api" # For Ethereum Mainnet
    ETHERSCAN_CHAIN_ID = "1" # Chain ID for Ethereum Mainnet

    ETHERSCAN_RATE_LIMIT_CALLS = 5  # Max calls
    ETHERSCAN_RATE_LIMIT_PERIOD = 1.0  # Per X seconds
    ETHERSCAN_REQUEST_RETRIES = 3 # Default number of retries on rate limit
    ETHERSCAN_REQUEST_BACKOFF_FACTOR = 0.5 # Default backoff factor for retries

    # Example for Sepolia Testnet:
    # ETHERSCAN_API_BASE_URL_SEPOLIA = "https://api-sepolia.etherscan.io/api"
    # ETHERSCAN_CHAIN_ID_SEPOLIA = "11155111"

    TRONSCAN_API_KEY = _load_api_token("tronscan_api_token.txt")
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
        },
        "ton": {
            "name": "TONScan",
            "url_template": "https://tonscan.org/address/{address}",
        },
        "bitcoin": {
            "name": "Blockchair (Bitcoin)",
            "url_template": "https://blockchair.com/bitcoin/address/{address}",
        },
        "ethereum": {  # EVM
            "name": "Etherscan",
            "url_template": "https://etherscan.io/address/{address}",
        },
        "bsc": {  # EVM - BNB Smart Chain (formerly Binance Smart Chain)
            "name": "BscScan",
            "url_template": "https://bscscan.com/address/{address}",
        },
        "polygon": {  # EVM
            "name": "PolygonScan",
            "url_template": "https://polygonscan.com/address/{address}",
        },
        "solana": {
            "name": "Solscan",
            "url_template": "https://solscan.io/account/{address}",  # Note: /account for Solscan
        },
        "avalanche": {  # EVM - Avalanche C-Chain
            "name": "Snowtrace",
            "url_template": "https://snowtrace.io/address/{address}",
        },
        "arbitrum": {  # EVM - Arbitrum One
            "name": "Arbiscan",
            "url_template": "https://arbiscan.io/address/{address}",
        },
        "optimism": {  # EVM - Optimism
            "name": "Optimistic Etherscan",
            "url_template": "https://optimistic.etherscan.io/address/{address}",
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
        # Add other explorers as needed
    }

    # Vertex AI Configuration
    VERTEX_AI_PROJECT_ID: Optional[str] = "multichat-bot-396516"  # Replace with your GCP Project ID
    VERTEX_AI_LOCATION: Optional[str] = "us-central1"      # Replace with your GCP region
    VERTEX_AI_MODEL_NAME: Optional[str] = "gemini-2.0-flash-lite-001" # Or other compatible model like gemini-1.5-flash-001

    @staticmethod
    def get_log_file_path(filename="bot.log"):
        # Ensure the log folder exists
        log_folder_path = os.path.join(
            os.path.dirname(__file__), Config.LOG_FOLDER
        )  # Ensure log folder is relative to config.py
        if not os.path.exists(log_folder_path):
            os.makedirs(log_folder_path)
        return os.path.join(log_folder_path, filename)
