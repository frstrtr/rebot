# filepath: /home/user0/rebot/extapi/etherscan/__init__.py
"""
Etherscan API Client Package
"""
from .client import EtherscanAPI, EtherscanAPIError, EtherscanRateLimitError

__all__ = ["EtherscanAPI", "EtherscanAPIError", "EtherscanRateLimitError"]
