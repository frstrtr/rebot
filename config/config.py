# config.py

from aiogram.enums import ParseMode
import os
import logging  # Add this import

class Config:
    PARSE_MODE = ParseMode.HTML
    MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, using a buffer
    LOG_FOLDER = "logs"  # Define the log folder name
    LOG_LEVEL = logging.INFO  # Define the global log level

    # Groups of chains where addresses can have the same format,
    # potentially leading to ambiguity if the network isn't specified.
    # If an address is detected and could belong to multiple chains in a group,
    # the bot should ask for clarification.
    # Keys are group names (for internal reference), values are sets of lowercase chain identifiers.
    AMBIGUOUS_CHAIN_GROUPS = {
        "evm_compatible": {  # Ethereum Virtual Machine compatible chains
            "ethereum",
            "bsc",       # BNB Smart Chain
            "polygon",
            "avalanche", # Avalanche C-Chain
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
        "ton": {"name": "TONScan", "url_template": "https://tonscan.org/address/{address}"},
        "bitcoin": {
            "name": "Blockchair (Bitcoin)",
            "url_template": "https://blockchair.com/bitcoin/address/{address}",
        },
        "ethereum": { # EVM
            "name": "Etherscan",
            "url_template": "https://etherscan.io/address/{address}",
        },
        "bsc": { # EVM - BNB Smart Chain (formerly Binance Smart Chain)
            "name": "BscScan",
            "url_template": "https://bscscan.com/address/{address}",
        },
        "polygon": { # EVM
            "name": "PolygonScan",
            "url_template": "https://polygonscan.com/address/{address}",
        },
        "solana": {
            "name": "Solscan",
            "url_template": "https://solscan.io/account/{address}", # Note: /account for Solscan
        },
        "avalanche": { # EVM - Avalanche C-Chain
            "name": "Snowtrace",
            "url_template": "https://snowtrace.io/address/{address}",
        },
        "arbitrum": { # EVM - Arbitrum One
            "name": "Arbiscan",
            "url_template": "https://arbiscan.io/address/{address}",
        },
        "optimism": { # EVM - Optimism
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

    @staticmethod
    def get_log_file_path(filename="bot.log"):
        # Ensure the log folder exists
        if not os.path.exists(Config.LOG_FOLDER):
            os.makedirs(Config.LOG_FOLDER)
        return os.path.join(Config.LOG_FOLDER, filename)