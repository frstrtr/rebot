"""
client.py
Module for interacting with the TronScan API.
"""
import logging
import aiohttp
from typing import Optional, Dict, Any

# Adjust the import path for Config based on the new structure
# Assuming 'config' is a top-level directory relative to where the bot runs,
# or it's in PYTHONPATH.
# If extapi and config are sibling directories under rebot:
from config.config import Config


TRONSCAN_API_BASE_URL = "https://apilist.tronscan.org/api/"

class TronScanAPI:
    """
    A simple client for interacting with the TronScan API.
    """

    def __init__(self, api_key: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        """
        Initializes the TronScanAPI client.

        Args:
            api_key: The TronScan API key. Defaults to Config.TRONSCAN_API_KEY.
            session: An optional aiohttp.ClientSession to use for requests.
        """
        self.api_key = api_key if api_key is not None else Config.TRONSCAN_API_KEY
        self._session = session
        self.base_url = TRONSCAN_API_BASE_URL

        if not self.api_key:
            logging.warning(
                "TronScanAPI initialized without an API key. Some endpoints may not work or be rate-limited."
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Returns the existing session or creates a new one if none exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self):
        """Closes the aiohttp session if it was created by this instance."""
        if self._session and not self._session.closed:
            await self._session.close()
            logging.info("TronScanAPI session closed.")

    async def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                       data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Makes an asynchronous HTTP request to the TronScan API.
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = {}
        if self.api_key:
            headers["TRON-PRO-API-KEY"] = self.api_key

        try:
            async with session.request(method, url, params=params, json=data, headers=headers, timeout=10) as response:
                response.raise_for_status()
                logging.debug(f"TronScan API request to {url} successful ({response.status})") # pylint: disable=logging-fstring-interpolation
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logging.error(f"TronScan API HTTP error: {e.status} {e.message} for URL {url}") # pylint: disable=logging-fstring-interpolation
            # The ClientResponseError 'e' does not have a 'response' attribute.
            # Accessing e.response.text() would cause an AttributeError.
            # e.message contains the HTTP reason phrase (e.g., "Not Found").
            # For full error response body, _request logic would need adjustment
            # to read response.text() before response.raise_for_status().
        except aiohttp.ClientError as e:
            logging.error(f"TronScan API client error: {e} for URL {url}") # pylint: disable=logging-fstring-interpolation
        except Exception as e:
            logging.error(f"An unexpected error occurred during TronScan API request to {url}: {e}", exc_info=True) # pylint: disable=logging-fstring-interpolation

        return None

    async def get_account_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches account information for a given TRON address.
        Endpoint example: /api/account?address={address}
        """
        if not address:
            logging.warning("get_account_info called with empty address.")
            return None
        endpoint = "account"
        params = {"address": address}
        logging.info(f"Fetching TronScan account info for address: {address}") # pylint: disable=logging-fstring-interpolation
        return await self._request("GET", endpoint, params=params)

    async def get_account_trc20_balances(self, address: str, limit: int = 50, start: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fetches TRC20 token balances for a given TRON address.
        Endpoint example: /api/account/tokens?address={address}&start={start}&limit={limit}&show=0
        """
        if not address:
            logging.warning("get_account_trc20_balances called with empty address.")
            return None
        endpoint = "account/tokens"
        params = {
            "address": address,
            "start": start,
            "limit": limit,
            "show": 0
        }
        logging.info(f"Fetching TRC20 balances for address: {address}") # pylint: disable=logging-fstring-interpolation
        return await self._request("GET", endpoint, params=params)

# Example usage (optional, for testing the module directly)
if __name__ == "__main__":
    import asyncio

    async def main_test():
        # This test assumes it's run from the 'rebot' directory,
        # or that 'rebot' is in PYTHONPATH for 'from config.config import Config' to work.
        api_client = TronScanAPI()

        if not api_client.api_key:
            print("TRONSCAN_API_KEY not found in config. Please set it up.")

        test_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

        print(f"\n--- Testing get_account_info for {test_address} ---")
        account_info = await api_client.get_account_info(test_address)
        if account_info:
            print("Account Info Received:")
            print(f"  Address: {account_info.get('address')}")
            print(f"  Balance (SUN): {account_info.get('balance')}")
            print(f"  Name: {account_info.get('name')}")
            print(f"  Total Transactions: {account_info.get('totalTransactionCount')}")
        else:
            print("Failed to get account info or address not found.")

        print(f"\n--- Testing get_account_trc20_balances for {test_address} ---")
        trc20_balances = await api_client.get_account_trc20_balances(test_address, limit=5)
        if trc20_balances and 'data' in trc20_balances:
            print("TRC20 Balances Received (first 5):")
            for token in trc20_balances['data'][:5]:
                print(f"  Token: {token.get('tokenName')} ({token.get('tokenAbbr')}), Balance: {token.get('balance')}, Decimals: {token.get('tokenDecimal')}")
        elif trc20_balances:
             print(f"TRC20 Balances response (structure might vary): {trc20_balances}")
        else:
            print("Failed to get TRC20 balances.")

        await api_client.close_session()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # To run this test directly:
    # Ensure you are in the /home/user0/rebot/ directory
    # Then run: python -m extapi.tronscan.client
    asyncio.run(main_test())
    