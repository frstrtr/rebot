"""
client.py
Module for interacting with the TronScan API.
"""
import logging
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime
import json
import os
from pathlib import Path
import asyncio
import re

# Adjust the import path for Config based on the new structure
# Assuming 'config' is a top-level directory relative to where the bot runs,
# or it's in PYTHONPATH.
# If extapi and config are sibling directories under rebot:
from config.config import Config

CACHE_DIR = Path("data/cache")
BLACKLIST_FILENAME = "stablecoin_blacklist.json"
BLACKLIST_FILE_PATH = CACHE_DIR / BLACKLIST_FILENAME


# Define custom exception for rate limiting
class TronScanRateLimitError(Exception):
    """Custom exception for TronScan API rate limit errors."""
    def __init__(self, message: str, status_code: int, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


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
            async with session.request(method, url, params=params, json=data, headers=headers, timeout=30) as response: # Increased timeout to 30 seconds
                if not response.ok: 
                    error_body = await response.text() 
                    logging.error(
                        f"TronScan API HTTP error: {response.status} {response.reason} for URL {url}. " 
                        f"Response: {error_body}"
                    )
                    if response.status == 403:
                        try:
                            error_json = json.loads(error_body)
                            if "Error" in error_json and "exceeds the frequency limit" in error_json["Error"]:
                                retry_seconds = 30  
                                match = re.search(r"suspended for (\d+) s", error_json["Error"])
                                if match:
                                    retry_seconds = int(match.group(1))
                                raise TronScanRateLimitError(
                                    message=f"Rate limit exceeded: {error_json['Error']}",
                                    status_code=response.status,
                                    retry_after=retry_seconds
                                )
                        except json.JSONDecodeError:
                            logging.debug(f"Could not parse 403 error body as JSON or find rate limit message: {error_body}")
                    return None 

                logging.debug(f"TronScan API request to {url} successful ({response.status})") 
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logging.error(f"TronScan API HTTP error (ClientResponseError): {e.status} {e.message} for URL {url}") 
            logging.error(f"TronScan API error details (from exception): status={e.status}, message='{e.message}', headers='{e.headers}'")
        except aiohttp.ClientError as e:
            logging.error(f"TronScan API client error: {e} for URL {url}") 
        except TronScanRateLimitError: 
            raise
        except Exception as e:
            logging.error(f"An unexpected error occurred during TronScan API request to {url}: {e}", exc_info=True) 

        return None

    async def get_account_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches account information for a given TRON address.
        Endpoint: /api/accountv2
        """
        if not address:
            logging.warning("get_account_info called with empty address.")
            return None
        endpoint = "accountv2"
        params = {"address": address}
        logging.info(f"Fetching TronScan account info for address: {address}") 
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
        logging.info(f"Fetching TRC20 balances for address: {address}") 
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
        """
        if not address:
            logging.warning("get_trc20_transaction_history called with empty address.")
            return None
        endpoint = "token_trc20/transfers"
        params = {
            "relatedAddress": address, 
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
            f"Fetching TRC20 transaction history for address: {address}, contract: {contract_address}" 
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
        """
        if not address:
            logging.warning("get_account_tags called with empty address.")
            return None
        endpoint = "account/tag" 
        params = {"address": address}
        logging.info(f"Fetching account tags for address: {address}")
        return await self._request("GET", endpoint, params=params)

    def _ensure_cache_dir_exists(self):
        """Ensures the cache directory exists."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"Could not create cache directory {CACHE_DIR}: {e}")

    def _load_blacklist_from_disk(self) -> list:
        """Loads the blacklist from a local JSON file."""
        self._ensure_cache_dir_exists()
        if BLACKLIST_FILE_PATH.exists():
            try:
                with open(BLACKLIST_FILE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    logging.warning(f"Blacklist cache file {BLACKLIST_FILE_PATH} did not contain a list.")
                    return []
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from {BLACKLIST_FILE_PATH}. Will attempt to rebuild.")
                return []
            except Exception as e:
                logging.error(f"Error loading blacklist from disk {BLACKLIST_FILE_PATH}: {e}")
                return []
        return []

    def _save_blacklist_to_disk(self, data: list):
        """Saves the blacklist to a local JSON file atomically."""
        self._ensure_cache_dir_exists()
        temp_file_path = BLACKLIST_FILE_PATH.with_suffix(".json.tmp")
        try:
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file_path, BLACKLIST_FILE_PATH)
            logging.info(f"Saved {len(data)} blacklist entries to {BLACKLIST_FILE_PATH}")
        except Exception as e:
            logging.error(f"Error saving blacklist to disk {BLACKLIST_FILE_PATH}: {e}")
            if temp_file_path.exists():
                try:
                    os.remove(temp_file_path)
                except OSError as e_remove:
                    logging.error(f"Could not remove temporary blacklist file {temp_file_path}: {e_remove}")

    async def _fetch_all_blacklist_pages(self) -> list:
        """Helper to fetch all entries from the /api/stableCoin/blackList endpoint."""
        all_entries = []
        current_start = 0
        page_limit = 50  
        max_retries = 3 
        current_page_retries = 0

        while True:
            try:
                params = {
                    "limit": page_limit,
                    "start": current_start,
                    "sort": 2,  
                    "direction": 2  
                }
                logging.debug(f"Fetching blacklist page: start={current_start}, limit={page_limit}, sort=time, direction=desc")
                response_data = await self._request("GET", "stableCoin/blackList", params=params)
                current_page_retries = 0 

                if response_data and isinstance(response_data.get('data'), list):
                    page_entries = response_data['data']
                    if not page_entries:  
                        logging.debug("Fetched last page of blacklist or no entries found on current page.")
                        break
                    all_entries.extend(page_entries)

                    if len(page_entries) < page_limit: 
                        logging.debug(f"Fetched {len(page_entries)} entries, which is less than page_limit {page_limit}. Assuming end of blacklist.")
                        break
                    current_start += len(page_entries)
                else:
                    if current_start == 0 and not all_entries:
                        logging.warning(
                            "Failed to fetch initial blacklist page. "
                            f"Response data: {response_data if response_data is not None else 'No response data (see previous HTTP error logs)'}"
                        )
                    else:
                        logging.warning(
                            f"Error fetching blacklist page or unexpected data format after fetching {len(all_entries)} entries. "
                            f"Problematic response_data for start={current_start}: {response_data if response_data is not None else 'No response data (see previous HTTP error logs)'}"
                        )
                    break 
            except TronScanRateLimitError as e:
                if current_page_retries < max_retries:
                    current_page_retries += 1
                    wait_time = e.retry_after if e.retry_after and e.retry_after > 0 else 30
                    logging.warning(
                        f"Rate limit hit while fetching blacklist (attempt {current_page_retries}/{max_retries} for page starting at {current_start}). "
                        f"Waiting for {wait_time} seconds. Error: {e.args[0]}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logging.error(
                        f"Max retries ({max_retries}) exceeded for rate limit error at start={current_start}. Aborting blacklist fetch."
                    )
                    break 
            except Exception as e:
                logging.error(f"Unexpected error during blacklist page fetch for start={current_start}: {e}", exc_info=True)
                break 
        return all_entries

    async def get_stablecoin_blacklist(self, limit: int = 50, start: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fetches a list of all blacklist addresses for stablecoins.
        Manages a local cache (data/cache/stablecoin_blacklist.json).
        """
        cached_blacklist = self._load_blacklist_from_disk()
        final_blacklist_data = []

        if cached_blacklist:
            logging.info(f"Loaded {len(cached_blacklist)} blacklist entries from cache: {BLACKLIST_FILE_PATH}")
            latest_cached_timestamp = 0
            if cached_blacklist:
                try:
                    valid_times = [item.get('time', 0) for item in cached_blacklist if isinstance(item.get('time'), (int, float))]
                    if valid_times:
                        latest_cached_timestamp = max(valid_times)
                except Exception as e: 
                    logging.warning(f"Could not determine latest timestamp from cached blacklist: {e}. Will perform full refresh.")
                    latest_cached_timestamp = 0
                    cached_blacklist = [] 

            if latest_cached_timestamp > 0 : 
                logging.info(f"Checking for blacklist updates since timestamp: {latest_cached_timestamp}")
                newly_fetched_entries_on_api = []
                current_api_page_start = 0
                api_page_limit = 50
                stop_fetching_further_pages = False 

                while True:
                    params = {
                        "limit": api_page_limit,
                        "start": current_api_page_start,
                        "sort": 2,  
                        "direction": 2,  
                    }
                    logging.debug(f"Params for blacklist update request: {params}") 
                    logging.debug(f"Fetching update page for blacklist: start={current_api_page_start}, sort=time, direction=desc") 
                    
                    api_response = None
                    try:
                        api_response = await self._request("GET", "stableCoin/blackList", params=params)
                    except TronScanRateLimitError as e:
                        logging.warning(f"Rate limit hit during stablecoin blacklist update (page start={current_api_page_start}): {e.args[0]}. "
                                        f"Aborting further updates for this call. Using currently fetched new items plus cache.")
                        stop_fetching_further_pages = True 
                    
                    current_page_new_items_to_add = []

                    if stop_fetching_further_pages: 
                        break

                    if api_response and isinstance(api_response.get('data'), list):
                        page_data_from_api = api_response['data']
                        if not page_data_from_api:
                            stop_fetching_further_pages = True
                            break

                        for item_from_api in page_data_from_api:
                            item_time = item_from_api.get('time', 0)
                            item_hash = item_from_api.get('transHash')

                            if not isinstance(item_time, (int, float)) or not item_hash:
                                logging.debug(f"Skipping item with invalid time or missing transHash: {item_from_api}")
                                continue

                            if item_time > latest_cached_timestamp:
                                if not any(cached_item.get('transHash') == item_hash for cached_item in cached_blacklist) and \
                                   not any(new_item.get('transHash') == item_hash for new_item in newly_fetched_entries_on_api):
                                    current_page_new_items_to_add.append(item_from_api)
                            else:
                                stop_fetching_further_pages = True
                                break 
                        
                        newly_fetched_entries_on_api.extend(current_page_new_items_to_add)
                        
                        if stop_fetching_further_pages or len(page_data_from_api) < api_page_limit:
                            break 
                        current_api_page_start += len(page_data_from_api)
                    else:
                        logging.warning("Failed to fetch blacklist update page from API or no data.")
                        break
                
                if newly_fetched_entries_on_api:
                    logging.info(f"Found {len(newly_fetched_entries_on_api)} new potential blacklist entries.")
                    combined_dict = {item['transHash']: item for item in newly_fetched_entries_on_api} 
                    for item in cached_blacklist: 
                        if item.get('transHash') not in combined_dict:
                            combined_dict[item['transHash']] = item
                    
                    final_blacklist_data = sorted(list(combined_dict.values()), key=lambda x: x.get('time', 0), reverse=True)
                    self._save_blacklist_to_disk(final_blacklist_data)
                else:
                    logging.info("No new blacklist entries found.")
                    final_blacklist_data = cached_blacklist
            else: 
                 cached_blacklist = [] 
                 logging.info("Cache was effectively empty. Performing full download for stablecoin blacklist.")


        if not cached_blacklist: 
            logging.info(f"No local blacklist cache found or cache was marked for refresh. Performing full download.")
            all_api_entries = [] 
            try:
                all_api_entries = await self._fetch_all_blacklist_pages()
            except Exception as e: 
                logging.error(f"Full download of blacklist failed unexpectedly at get_stablecoin_blacklist level: {e}", exc_info=True)
            
            if all_api_entries:
                final_blacklist_data = sorted(all_api_entries, key=lambda x: x.get('time', 0), reverse=True)
                unique_data_dict = {item['transHash']: item for item in final_blacklist_data if item.get('transHash')}
                final_blacklist_data = list(unique_data_dict.values())
                final_blacklist_data = sorted(final_blacklist_data, key=lambda x: x.get('time', 0), reverse=True)

                logging.info(f"Successfully fetched {len(final_blacklist_data)} total blacklist entries for new cache.") 
                self._save_blacklist_to_disk(final_blacklist_data)
            else:
                logging.warning("Full download of blacklist failed or returned no entries.")
                final_blacklist_data = []

        paginated_data = final_blacklist_data[start : start + limit]
        
        return {
            "total": len(final_blacklist_data),
            "data": paginated_data
        }

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
            params["contractAddress"] = contract_address 
        
        logging.info(f"Fetching big token amounts for address: {address}, contract: {contract_address} (limit: {limit})") 
        return await self._request("GET", endpoint, params=params)

    async def get_stablecoin_key_events(
        self,
        limit: int = 50,
        start: int = 0,
        operator_address: Optional[str] = None,
        sort_by: Optional[int] = None, 
        direction: Optional[int] = None, 
        start_time: Optional[int] = None, 
        end_time: Optional[int] = None, 
        start_amount: Optional[float] = None,
        end_amount: Optional[float] = None,
        usdt_events: Optional[str] = None, 
        usdc_events: Optional[str] = None,
        usdd_events: Optional[str] = None,
        usdj_events: Optional[str] = None,
        tusd_events: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches key events of TRON stablecoins.
        Endpoint: /api/deep/stableCoin/totalSupply/keyEvents
        """
        endpoint = "deep/stableCoin/totalSupply/keyEvents"
        params = {
            "limit": limit,
            "start": start
        }
        if operator_address is not None:
            params["operatorAddress"] = operator_address
        if sort_by is not None:
            params["sort"] = sort_by
        if direction is not None:
            params["direction"] = direction
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if start_amount is not None:
            params["startAmount"] = start_amount
        if end_amount is not None:
            params["endAmount"] = end_amount
        if usdt_events is not None:
            params["USDT"] = usdt_events
        if usdc_events is not None:
            params["USDC"] = usdc_events
        if usdd_events is not None:
            params["USDD"] = usdd_events
        if usdj_events is not None:
            params["USDJ"] = usdj_events
        if tusd_events is not None:
            params["TUSD"] = tusd_events

        logging.info(f"Fetching stablecoin key events with params: {params}")
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
        history_all = await api_client.get_trc20_transaction_history(test_user_address, limit=5)
        # history_all = await api_client.get_trc20_transaction_history(test_user_address)
        if history_all and history_all.get("token_transfers"):
            print("TRC20 Transaction History (All Tokens, first 5):")
            for tx in history_all["token_transfers"][:5]:
            # for tx in history_all["token_transfers"]:
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
            print(f"Related Accounts ({len(related_accounts.get('data', []))}) data received (first few entries if list):")
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
            print(f"Account Tags ({len(account_tags.get('Assets', []))})received for {test_user_address}:")
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

        print("\n\033[93m--- Testing get_stablecoin_blacklist (first 5) ---\033[0m")
        blacklist = await api_client.get_stablecoin_blacklist(limit=5)
        if blacklist and blacklist.get('data'): # Assuming data is in 'data' key
            print("Stablecoin Blacklist (first 5):")
            for item in blacklist['data'][:5]: # Iterate through items in 'data'
                print(f"  Address: {item.get('blackAddress')}, Token: {item.get('tokenName')}, Tx Hash: {item.get('transHash')}")
        elif blacklist:
            print(f"Stablecoin Blacklist response (structure might vary): {blacklist}")
        else:
            print("Failed to get stablecoin blacklist.")

        print(f"\n\033[93m--- Testing get_account_transfer_amounts for {test_user_address} ---\033[0m")
        transfer_amounts = await api_client.get_account_transfer_amounts(test_user_address)
        if transfer_amounts:
            print(f"Account Transfer Amounts for {test_user_address}:")

            # Check for the new structure: 'transfer_out' and 'transfer_in'
            if 'transfer_out' in transfer_amounts or 'transfer_in' in transfer_amounts:
                if transfer_amounts.get('transfer_out'):
                    out_data = transfer_amounts['transfer_out']
                    print(f"  Transfer Out (Total: {out_data.get('total')}, Amount Total USD: {out_data.get('amountTotal')}) (first 2 entries):")
                    if isinstance(out_data.get('data'), list):
                        for item in out_data['data'][:2]:
                            print(f"    - Address: {item.get('address')}, Amount USD: {item.get('amountInUsd')}, Tag: {item.get('addressTag')}")
                            # Optionally print contract info if relevant and present for this address
                            if isinstance(out_data.get('contractInfo'), dict) and item.get('address') in out_data['contractInfo']:
                                print(f"      Contract Info: {out_data['contractInfo'][item.get('address')]}")
                
                if transfer_amounts.get('transfer_in'):
                    in_data = transfer_amounts['transfer_in']
                    print(f"  Transfer In (Total: {in_data.get('total')}, Amount Total USD: {in_data.get('amountTotal')}) (first 2 entries):")
                    if isinstance(in_data.get('data'), list):
                        for item in in_data['data'][:2]:
                            print(f"    - Address: {item.get('address')}, Amount USD: {item.get('amountInUsd')}, Tag: {item.get('addressTag')}")
                            if isinstance(in_data.get('contractInfo'), dict) and item.get('address') in in_data['contractInfo']:
                                print(f"      Contract Info: {in_data['contractInfo'][item.get('address')]}")

            # Fallback to checking for 'stableAmountLine' or 'stableAmount24h'
            elif 'stableAmountLine' in transfer_amounts or 'stableAmount24h' in transfer_amounts:
                if transfer_amounts.get('stableAmountLine'):
                    print("  Stable Amount Line (first 2 tokens, first 2 data points per token):")
                    for token_data in transfer_amounts['stableAmountLine'][:2]:
                        print(f"    Token: {token_data.get('tokenAbbr')}, Contract: {token_data.get('contractAddress')}")
                        if isinstance(token_data.get('lineData'), list):
                            for ld_item in token_data['lineData'][:2]:
                                print(f"      - Timestamp: {ld_item.get('t')}, Value: {ld_item.get('v')}")
                
                if transfer_amounts.get('stableAmount24h'):
                    print("  Stable Amount 24h (first 2 tokens):")
                    for token_data in transfer_amounts['stableAmount24h'][:2]:
                        print(f"    - Token: {token_data.get('tokenAbbr')}, Contract: {token_data.get('contractAddress')}, Amount24h: {token_data.get('amount24h')}")
            
            # Fallback to checking for the previously assumed structure (receiveList/sendList)
            elif transfer_amounts.get('receiveList') or transfer_amounts.get('sendList'):
                if transfer_amounts.get('receiveList'):
                    print("  Top Incoming (first 2 entries):")
                    for tx_info in transfer_amounts['receiveList'][:2]:
                        print(f"    - {tx_info}") # Print the dictionary item
                
                if transfer_amounts.get('sendList'):
                    print("  Top Outgoing (first 2 entries):")
                    for tx_info in transfer_amounts['sendList'][:2]:
                        print(f"    - {tx_info}") # Print the dictionary item
            
            # If no known structure is found, print a generic representation
            else:
                print("  Data structure not recognized by specific formatting, printing raw (up to 400 chars):")
                raw_str = str(transfer_amounts)
                print(f"    {raw_str[:400]}{'...' if len(raw_str) > 400 else ''}")

        else:
            print(f"Failed to get account transfer amounts for {test_user_address}.")


        print(f"\n\033[93m--- Testing get_account_token_big_amounts for {test_user_address} (USDT, limit 3) ---\033[0m")
        big_amounts_usdt = await api_client.get_account_token_big_amounts(test_user_address, contract_address=usdt_trc20_contract_address, limit=3)
        if big_amounts_usdt and big_amounts_usdt.get('data'):
            print(f"Big USDT Token Amounts ({len(big_amounts_usdt['data'])}) for {test_user_address} (first 3):")
            for tx_info in big_amounts_usdt['data'][:3]:
                print(f"  TxID: {tx_info.get('transaction_id')}, Amount: {tx_info.get('amount')}, To: {tx_info.get('to_address')}, From: {tx_info.get('from_address')}")
        elif big_amounts_usdt:
            print(f"Big USDT Token Amounts response (structure might vary): {big_amounts_usdt}")
        else:
            print(f"Failed to get big USDT token amounts for {test_user_address}.")

        print(f"\n\033[93m--- Testing get_stablecoin_key_events (first 5) ---\033[0m")
        key_events = await api_client.get_stablecoin_key_events(limit=5)
        if key_events and key_events.get('data'):
            print(f"Stablecoin Key Events ({len(key_events['data'])}) (first 5):")
            for event in key_events['data'][:5]:
                print(f"  Event Type: {event.get('eventType')}, Token: {event.get('tokenSymbol')}, Address: {event.get('address')}, Timestamp: {event.get('block_ts')}")
        elif key_events:
            print(f"Stablecoin Key Events response (structure might vary): {key_events}")
        else:
            print("Failed to get stablecoin key events.")


        print(f"\n\033[93m--- Testing get_stablecoin_key_events (first 5, USDT AddedBlackList) ---\033[0m")
        key_events = await api_client.get_stablecoin_key_events(limit=5, usdt_events="AddedBlackList", sort_by=2, direction=2)
        if key_events and key_events.get('data'):
            event_list = key_events['data']
            print(f"Stablecoin Key Events (Total in response: {key_events.get('total', len(event_list))}, showing first {len(event_list[:5])}):")
            for event in event_list[:5]:
                print(
                    f"  Event Type: {event.get('eventName')}, Token: {event.get('tokenSymbol')}, " # Adjusted 'eventType' to 'eventName' if that's the field
                    f"Tx Hash: {event.get('transaction_id')}, "
                    f"Block TS: {event.get('block_ts')}, "
                    f"Contract: {event.get('contract_address')}, "
                    f"Operator: {event.get('operator_address')}" 
                )
                details_to_print = {}
                if 'old_value' in event: details_to_print['Old Value'] = event['old_value']
                if 'new_value' in event: details_to_print['New Value'] = event['new_value']
                if 'black_address' in event: details_to_print['Black Address'] = event['black_address']
                if 'amount' in event: details_to_print['Amount'] = event['amount']
                if details_to_print:
                    print(f"    Details: {details_to_print}")

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
