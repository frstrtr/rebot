"""
client.py
Module for interacting with the TronScan API.
"""
import logging
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime

# Adjust the import path for Config based on the new structure
# Assuming 'config' is a top-level directory relative to where the bot runs,
# or it's in PYTHONPATH.
# If extapi and config are sibling directories under rebot:
from config.config import Config


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
        if self.api_key:
            logging.info(f"TronScanAPI initialized with API key (first 5 chars): {self.api_key[:5]}..., Length: {len(self.api_key)}") # pylint: disable=logging-fstring-interpolation
        else:
            logging.info("TronScanAPI initialized with No API Key")
        self._session = session
        self.base_url = Config.TRONSCAN_API_BASE_URL  # Use Config value

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
                # Check for HTTP errors first
                if not response.ok: # response.ok is False if status is 400 or higher
                    error_body = await response.text() # Read the error body
                    logging.error(
                        f"TronScan API HTTP error: {response.status} {response.reason} for URL {url}. " # pylint: disable=logging-fstring-interpolation
                        f"Response: {error_body}"
                    )
                    return None # Return None as per original behavior for ClientResponseError

                # If response is OK, proceed to get JSON
                logging.debug(f"TronScan API request to {url} successful ({response.status})") # pylint: disable=logging-fstring-interpolation
                # It's possible for response.json() to fail if content type is wrong, even on 2xx.
                # This will be caught by the general ClientError or Exception below.
                return await response.json()
        except aiohttp.ClientResponseError as e:
            # This block is less likely to be hit for typical HTTP status errors now,
            # as they are handled by the `if not response.ok:` check above.
            # However, it's kept as a fallback or for other ClientResponseError scenarios
            # (e.g., if response.json() itself could raise it under certain conditions,
            # or if other parts of aiohttp middleware raise it).
            logging.error(f"TronScan API HTTP error (ClientResponseError): {e.status} {e.message} for URL {url}") # pylint: disable=logging-fstring-interpolation
            # Log available details from the exception object. Do not attempt e.text().
            logging.error(f"TronScan API error details (from exception): status={e.status}, message='{e.message}', headers='{e.headers}'")
        except aiohttp.ClientError as e:
            logging.error(f"TronScan API client error: {e} for URL {url}") # pylint: disable=logging-fstring-interpolation
        except Exception as e:
            logging.error(f"An unexpected error occurred during TronScan API request to {url}: {e}", exc_info=True) # pylint: disable=logging-fstring-interpolation

        return None

    async def get_account_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches account information for a given TRON address.
        Endpoint: /api/accountv2
        """
        if not address:
            logging.warning("get_account_info called with empty address.")
            return None
        endpoint = "accountv2"  # Ensure this is the correct endpoint
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
        endpoint = "account/tokens" # This endpoint might be /api/account/tokens or similar for balances
        params = {
            "address": address,
            "start": start,
            "limit": limit,
            "show": 0 # Often used to specify TRC20, check API docs
        }
        logging.info(f"Fetching TRC20 balances for address: {address}") # pylint: disable=logging-fstring-interpolation
        return await self._request("GET", endpoint, params=params)

    async def get_trc20_transaction_history(
        self,
        address: str,
        contract_address: Optional[str] = None,
        limit: int = 50,
        start: int = 0,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches TRC20 token transaction history for a given address.
        Endpoint example: /api/token_trc20/transfers
        Common parameters:
        - relatedAddress or address: The account address.
        - contract_address: Filter by a specific TRC20 token contract.
        - limit, start: For pagination.
        - start_timestamp, end_timestamp: For time range filtering (in milliseconds).
        """
        if not address:
            logging.warning("get_trc20_transaction_history called with empty address.")
            return None

        # The exact endpoint and parameter names can vary slightly.
        # Common variations for address parameter: 'address', 'relatedAddress', 'account_address'
        # Check TronScan's official API documentation for the most accurate details.
        endpoint = "token_trc20/transfers"
        params = {
            "relatedAddress": address, # Using 'relatedAddress' as it's common for transfers
            "limit": limit,
            "start": start,
        }
        if contract_address:
            params["contract_address"] = contract_address
        if start_timestamp is not None:
            params["start_timestamp"] = start_timestamp
        if end_timestamp is not None:
            params["end_timestamp"] = end_timestamp

        logging.info(
            f"Fetching TRC20 transaction history for address: {address}, contract: {contract_address}" # pylint: disable=logging-fstring-interpolation
        )
        return await self._request("GET", endpoint, params=params)

    async def get_account_related_accounts(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches account data with transaction records with the current account.
        Endpoint: /api/deep/account/relatedAccount
        """
        if not address:
            logging.warning("get_account_related_accounts called with empty address.")
            return None
        endpoint = "deep/account/relatedAccount"
        params = {"address": address}
        logging.info(f"Fetching related accounts for address: {address}")
        return await self._request("GET", endpoint, params=params)

    async def get_account_tags(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches all tags of an account.
        Endpoint: /api/account/tag
        Note: The actual structure of the response for tags should be verified.
              Sometimes tags are part of the main account info response.
        """
        if not address:
            logging.warning("get_account_tags called with empty address.")
            return None
        endpoint = "account/tag" # As specified by user
        params = {"address": address}
        logging.info(f"Fetching account tags for address: {address}")
        # This might return a list of tags or a more complex object.
        # Example: {"address":"TR...","tags":[{"tag":"Whale","tag_id":1}]}
        return await self._request("GET", endpoint, params=params)

    async def get_stablecoin_blacklist(self, limit: int = 50, start: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fetches a list of all blacklist transactions/addresses for stablecoins.
        Endpoint: /api/stableCoin/blackList
        """
        endpoint = "stableCoin/blackList"
        params = {
            "limit": limit,
            "start": start
        }
        logging.info(f"Fetching stablecoin blacklist (limit: {limit}, start: {start})")
        return await self._request("GET", endpoint, params=params)

    async def get_account_transfer_amounts(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Obtains account transfer-in and transfer-out fund distribution.
        Endpoint: /api/deep/account/transferAmount
        """
        if not address:
            logging.warning("get_account_transfer_amounts called with empty address.")
            return None
        endpoint = "deep/account/transferAmount"
        params = {"address": address}
        logging.info(f"Fetching account transfer amounts for address: {address}")
        return await self._request("GET", endpoint, params=params)

    async def get_account_token_big_amounts(
        self,
        address: str,
        contract_address: Optional[str] = None,
        limit: int = 10,
        start: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches large token transactions for a given account.
        Endpoint: /api/deep/account/token/bigAmount
        """
        if not address:
            logging.warning("get_account_token_big_amounts called with empty address.")
            return None
        endpoint = "deep/account/token/bigAmount"
        params = {
            "address": address,
            "limit": limit,
            "start": start
        }
        if contract_address:
            params["contractAddress"] = contract_address # API might use 'contract_address' or 'token_address'
        
        logging.info(f"Fetching big token amounts for address: {address}, contract: {contract_address} (limit: {limit})")
        return await self._request("GET", endpoint, params=params)

    async def get_stablecoin_key_events(self, limit: int = 50, start: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fetches key events of TRON stablecoins (e.g., AddedBlackList, LogSetOwner).
        Endpoint: /api/stableCoin/totalSupply/keyEvents
        """
        endpoint = "stableCoin/totalSupply/keyEvents"
        params = {
            "limit": limit,
            "start": start
        }
        logging.info(f"Fetching stablecoin key events (limit: {limit}, start: {start})")
        return await self._request("GET", endpoint, params=params)


# Example usage (optional, for testing the module directly)
if __name__ == "__main__":
    import asyncio
    import time
    from datetime import datetime # Ensure datetime is imported here if not already at the top level

    async def main_test():
        # This test assumes it's run from the 'rebot' directory,
        # or that 'rebot' is in PYTHONPATH for 'from config.config import Config' to work.
        api_client = TronScanAPI()

        if not api_client.api_key:
            print("TRONSCAN_API_KEY not found in config. Please set it up. This endpoint might require it.")
            # return # Optionally exit if no API key for testing

        test_user_address = "TRnoPh9n4ea1QKbaTK9u3ocoQgFhNPSzRk" # Example: Scammer address
        # test_user_address = "TLa2f6VPqDgRE67v1736s7gWVaG1Dbte4c" # Example: TRON Foundation
        usdt_trc20_contract_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" # This is Tether (USDT) on TRON, for testing specific token

        print(f"\n\033[93m--- Testing get_account_info for {test_user_address} ---\033[0m")
        account_info = await api_client.get_account_info(test_user_address)
        if account_info:
            print("Account Info Received:")
            print(f"  Address: {account_info.get('address')}")
            # The 'balance' field in /api/account/info is usually the TRX balance in SUN
            trx_balance_sun = account_info.get('balance', 0)
            trx_balance = trx_balance_sun / 1_000_000  # Convert SUN to TRX
            print(f"  TRX Balance: {trx_balance} TRX ({trx_balance_sun} SUN)")
            print(f"  Account Name: {account_info.get('account_name')}") # Field name might vary, check response
            print(f"  Total transaction count: {account_info.get('total_transaction_count')}")
            # print(f"  Full account_info: {account_info}")
        else:
            print(f"Failed to get account info for {test_user_address} or address not found.")

        print(f"\n\033[93m--- Testing get_account_trc20_balances for {test_user_address} ---\033[0m")
        trc20_balances = await api_client.get_account_trc20_balances(test_user_address, limit=5)
        if trc20_balances and trc20_balances.get('trc20token_balances'): # Structure might be different
            print("TRC20 Balances Received (first 5):")
            for token in trc20_balances['trc20token_balances'][:5]:
                print(f"  Token: {token.get('tokenName')} ({token.get('tokenAbbr')}), Balance: {token.get('balanceWithTask')}, Decimals: {token.get('tokenDecimal')}")
        elif trc20_balances:
             print(f"TRC20 Balances response (structure might vary): {trc20_balances}")
        else:
            print("Failed to get TRC20 balances.")

        print(f"\n\033[93m--- Testing get_trc20_transaction_history for {test_user_address} (all tokens, last 5) ---\033[0m")
        # history_all = await api_client.get_trc20_transaction_history(test_user_address, limit=5)
        history_all = await api_client.get_trc20_transaction_history(test_user_address)
        if history_all and history_all.get("token_transfers"):
            print("TRC20 Transaction History (All Tokens, first 5):")
            # for tx in history_all["token_transfers"][:5]:
            for tx in history_all["token_transfers"]:
                # Assuming tx is a dictionary-like object and 'block_ts' contains a Unix timestamp
                raw_timestamp_ms = tx.get('block_ts')
                human_readable_timestamp = "N/A" # Default value

                if raw_timestamp_ms is not None:
                    try:
                        # Convert the Unix timestamp (milliseconds since epoch) to seconds
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        datetime_object = datetime.fromtimestamp(timestamp_seconds)
                        # Format the datetime object into a human-readable string
                        # Example format: "2023-10-26 14:35:00"
                        human_readable_timestamp = datetime_object.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError) as e:
                        # Handle cases where raw_timestamp is not a valid number for a timestamp
                        logging.debug(f"Could not parse timestamp {raw_timestamp_ms}: {e}")
                        human_readable_timestamp = "Invalid timestamp"
                else:
                    # Handle cases where 'block_ts' is not found or is None
                    human_readable_timestamp = "N/A"

                print(
                    f"  Timestamp: {raw_timestamp_ms}  "
                    f"From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
                    # f"  TxID: {tx.get('transaction_id')[:10]}..., From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
                    f"Token: {tx.get('tokenInfo', {}).get('tokenAbbr', 'N/A')}, Amount: {tx.get('quant')}, Confirmed: {tx.get('confirmed')}, "
                    # f"Timestamp: {human_readable_timestamp}"
                )
        elif history_all:
            print(f"TRC20 History (All) response (structure might vary): {history_all}")
        else:
            print("Failed to get TRC20 transaction history (all tokens).")

        print(f"\n\033[93m--- Testing get_trc20_transaction_history for {test_user_address} (USDT only, last 3) ---\033[0m")
        history_usdt = await api_client.get_trc20_transaction_history(
            test_user_address, contract_address=usdt_trc20_contract_address, limit=3
        )
        if history_usdt and history_usdt.get("token_transfers"):
            print("TRC20 Transaction History (USDT, first 3):")
            for tx in history_usdt["token_transfers"][:3]:
                # Assuming tx is a dictionary-like object and 'block_ts' contains a Unix timestamp
                raw_timestamp_ms = tx.get('block_ts')
                human_readable_timestamp = "N/A" # Default value

                if raw_timestamp_ms is not None:
                    try:
                        # Convert the Unix timestamp (milliseconds since epoch) to seconds
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        datetime_object = datetime.fromtimestamp(timestamp_seconds)
                        # Format the datetime object into a human-readable string
                        # Example format: "2023-10-26 14:35:00"
                        human_readable_timestamp = datetime_object.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError) as e:
                        # Handle cases where raw_timestamp is not a valid number for a timestamp
                        logging.debug(f"Could not parse timestamp {raw_timestamp_ms}: {e}")
                        human_readable_timestamp = "Invalid timestamp"
                else:
                    # Handle cases where 'block_ts' is not found or is None
                    human_readable_timestamp = "N/A"

                print(
                    f"  TxID: {tx.get('transaction_id')[:10]}..., From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
                    f"Token: {tx.get('tokenInfo', {}).get('tokenAbbr', 'N/A')}, Amount: {tx.get('quant')}, Confirmed: {tx.get('confirmed')}, "
                    f"Timestamp: {human_readable_timestamp}"
                )
        elif history_usdt:
            print(f"TRC20 History (USDT) response (structure might vary): {history_usdt}")
        else:
            print("Failed to get TRC20 transaction history (USDT).")

        print(f"\n\033[93m--- Testing get_account_related_accounts for {test_user_address} ---\033[0m")
        related_accounts = await api_client.get_account_related_accounts(test_user_address)
        if related_accounts:
            print(f"Related Accounts data received (first few entries if list):")
            if isinstance(related_accounts.get('data'), list): # Assuming 'data' holds the list
                for acc_data in related_accounts['data'][:3]:
                    print(f"  Related Address: {acc_data.get('related_address')}, Tag: {acc_data.get('addressTag')}, In: {acc_data.get('inAmountUsd')}, Out: {acc_data.get('outAmountUsd')}")
            else: # Print raw if structure is different
                print(related_accounts)
        else:
            print(f"Failed to get related accounts for {test_user_address}.")

        print(f"\n\033[93m--- Testing get_account_tags for {test_user_address} ---\033[0m")
        account_tags = await api_client.get_account_tags(test_user_address)
        if account_tags:
            print(f"Account Tags received for {test_user_address}:")
            # Assuming tags might be in a list under a 'tags' key or similar
            if isinstance(account_tags.get('tags'), list):
                 for tag_info in account_tags['tags']:
                    print(f"  Tag: {tag_info.get('tag')}, Tag ID: {tag_info.get('tag_id')}")
            elif isinstance(account_tags, list): # If the response itself is a list of tags
                for tag_info in account_tags[:5]:
                    print(f"  Tag: {tag_info}") # Adjust based on actual tag structure
            else:
                print(account_tags) # Print raw if structure is different
        else:
            print(f"Failed to get account tags for {test_user_address}.")

        print(f"\n\033[93m--- Testing get_stablecoin_blacklist (first 5) ---\033[0m")
        blacklist = await api_client.get_stablecoin_blacklist(limit=5)
        if blacklist and blacklist.get('data'): # Assuming data is in 'data' key
            print("Stablecoin Blacklist (first 5):")
            for item in blacklist['data'][:5]: # Iterate through items in 'data'
                print(f"  Address: {item.get('address')}, Token: {item.get('tokenSymbol')}, Reason: {item.get('reason')}")
        elif blacklist:
            print(f"Stablecoin Blacklist response (structure might vary): {blacklist}")
        else:
            print("Failed to get stablecoin blacklist.")

        print(f"\n\033[93m--- Testing get_account_transfer_amounts for {test_user_address} ---\033[0m")
        transfer_amounts = await api_client.get_account_transfer_amounts(test_user_address)
        if transfer_amounts:
            print(f"Account Transfer Amounts for {test_user_address}:")
            # Example: print top 2 incoming and outgoing if available
            if transfer_amounts.get('receiveList'):
                print("  Top Incoming:")
                for tx_info in transfer_amounts['receiveList'][:2]:
                    print(f"    From: {tx_info.get('address')}, Amount USD: {tx_info.get('amountUsd')}, Tag: {tx_info.get('tag')}")
            if transfer_amounts.get('sendList'):
                print("  Top Outgoing:")
                for tx_info in transfer_amounts['sendList'][:2]:
                    print(f"    To: {tx_info.get('address')}, Amount USD: {tx_info.get('amountUsd')}, Tag: {tx_info.get('tag')}")
            # print(transfer_amounts) # Or print raw for full details
        else:
            print(f"Failed to get account transfer amounts for {test_user_address}.")

        print(f"\n\033[93m--- Testing get_account_token_big_amounts for {test_user_address} (USDT, limit 3) ---\033[0m")
        big_amounts_usdt = await api_client.get_account_token_big_amounts(test_user_address, contract_address=usdt_trc20_contract_address, limit=3)
        if big_amounts_usdt and big_amounts_usdt.get('data'):
            print(f"Big USDT Token Amounts for {test_user_address} (first 3):")
            for tx_info in big_amounts_usdt['data'][:3]:
                print(f"  TxID: {tx_info.get('transaction_id')}, Amount: {tx_info.get('amount')}, To: {tx_info.get('to_address')}, From: {tx_info.get('from_address')}")
        elif big_amounts_usdt:
            print(f"Big USDT Token Amounts response (structure might vary): {big_amounts_usdt}")
        else:
            print(f"Failed to get big USDT token amounts for {test_user_address}.")

        print(f"\n\033[93m--- Testing get_stablecoin_key_events (first 5) ---\033[0m")
        key_events = await api_client.get_stablecoin_key_events(limit=5)
        if key_events and key_events.get('data'):
            print("Stablecoin Key Events (first 5):")
            for event in key_events['data'][:5]:
                print(f"  Event Type: {event.get('eventType')}, Token: {event.get('tokenSymbol')}, Address: {event.get('address')}, Timestamp: {event.get('block_ts')}")
        elif key_events:
            print(f"Stablecoin Key Events response (structure might vary): {key_events}")
        else:
            print("Failed to get stablecoin key events.")


        # Example with timestamp (transactions in the last 24 hours)
        # current_time_ms = int(time.time() * 1000)
        # one_day_ago_ms = current_time_ms - (24 * 60 * 60 * 1000)
        # print(f"\n--- Testing get_trc20_transaction_history for {test_user_address} (last 24 hours, limit 5) ---")
        # history_timed = await api_client.get_trc20_transaction_history(
        #     test_user_address, limit=5, start_timestamp=one_day_ago_ms, end_timestamp=current_time_ms
        # )
        # if history_timed and history_timed.get("token_transfers"):
        #     print("TRC20 Transaction History (Last 24h, first 5):")
        #     for tx in history_timed["token_transfers"][:5]:
        #         print(
        #             f"  TxID: {tx.get('transaction_id')[:10]}..., From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
        #             f"Token: {tx.get('tokenInfo', {}).get('tokenAbbr', 'N/A')}, Amount: {tx.get('quant')}, Timestamp: {tx.get('block_ts')}"
        #         )
        # elif history_timed:
        #      print(f"TRC20 History (Timed) response (structure might vary): {history_timed}")
        # else:
        #     print("Failed to get TRC20 transaction history (timed).")

        await api_client.close_session()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # To run this test directly:
    # Ensure you are in the /home/user0/rebot/ directory
    # Then run: python -m extapi.tronscan.client
    asyncio.run(main_test())
