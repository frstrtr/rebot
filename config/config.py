# config.py

from aiogram.enums import ParseMode
import os
import logging  # Add this import

class Config:
    PARSE_MODE = ParseMode.HTML
    MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, using a buffer
    LOG_FOLDER = "logs"  # Define the log folder name
    LOG_LEVEL = logging.INFO  # Define the global log level
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
        "ethereum": {
            "name": "Etherscan",
            "url_template": "https://etherscan.io/address/{address}",
        },
        "solana": {
            "name": "Solscan",
            "url_template": "https://solscan.io/account/{address}",
        },
        "ripple": {
            "name": "XRPSscan",
            "url_template": "https://xrpscan.com/account/{address}",
        },
        "stellar": {
            "name": "Stellar.Expert",
            "url_template": "https://stellar.expert/explorer/public/account/{address}",
        },
        "cosmos": {
            "name": "Mintscan",
            "url_template": "https://www.mintscan.io/cosmos/account/{address}",
        },
        "polkadot": {
            "name": "Subscan",
            "url_template": "https://polkadot.subscan.io/account/{address}",
        },
        "algorand": {
            "name": "AlgoExplorer",
            "url_template": "https://algoexplorer.io/address/{address}",
        },
    }

    @staticmethod
    def get_log_file_path(filename="bot.log"):
        # Ensure the log folder exists
        if not os.path.exists(Config.LOG_FOLDER):
            os.makedirs(Config.LOG_FOLDER)
        return os.path.join(Config.LOG_FOLDER, filename)