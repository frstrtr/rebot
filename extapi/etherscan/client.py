"""
client.py
Module for interacting with the Etherscan API.
"""
import asyncio
import logging
import time # Added
from collections import deque # Added
from typing import Optional, Dict, Any, List
import aiohttp

# Assuming 'config' is a top-level directory relative to where the bot runs,
# or it's in PYTHONPATH.
from config.config import Config

# Define custom exception for Etherscan API errors
class EtherscanAPIError(Exception):
    """Custom exception for Etherscan API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, etherscan_message: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.etherscan_message = etherscan_message

class EtherscanRateLimitError(EtherscanAPIError):
    """Custom exception for Etherscan API rate limit errors."""
    pass

class EtherscanAPI:
    """
    A client for interacting with the Etherscan API.
    Ref: https://docs.etherscan.io/etherscan-v2
    """

    def __init__(self, 
                 api_key: Optional[str] = None, 
                 session: Optional[aiohttp.ClientSession] = None, 
                 chain_id: Optional[str] = None,
                 base_url: Optional[str] = None, # Added base_url parameter
                 rate_limit_calls: Optional[int] = None,
                 rate_limit_period: Optional[float] = None,
                 default_retries: Optional[int] = None,
                 default_backoff_factor: Optional[float] = None):
        """
        Initializes the EtherscanAPI client.

        Args:
            api_key: The Etherscan API key. Defaults to Config.ETHERSCAN_API_KEY.
            session: An optional aiohttp.ClientSession to use for requests.
            chain_id: The chain ID for the network. Defaults to Config.ETHERSCAN_CHAIN_ID.
            base_url: The base URL for the Etherscan API. Defaults to Config.ETHERSCAN_API_BASE_URL or "https://api.etherscan.io/v2/api".
            rate_limit_calls: Max calls per rate_limit_period. Defaults to Config.ETHERSCAN_RATE_LIMIT_CALLS.
            rate_limit_period: The period in seconds for rate limiting. Defaults to Config.ETHERSCAN_RATE_LIMIT_PERIOD.
            default_retries: Default number of retries for rate-limited requests. Defaults to Config.ETHERSCAN_REQUEST_RETRIES.
            default_backoff_factor: Default backoff factor for retries. Defaults to Config.ETHERSCAN_REQUEST_BACKOFF_FACTOR.
        """
        self.api_key = api_key if api_key is not None else getattr(Config, "ETHERSCAN_API_KEY", None)
        self._session = session
        self.base_url = base_url if base_url is not None else getattr(Config, "ETHERSCAN_API_BASE_URL", "https://api.etherscan.io/v2/api")
        self.chain_id = chain_id if chain_id is not None else getattr(Config, "ETHERSCAN_CHAIN_ID", None)

        self.rate_limit_calls = rate_limit_calls if rate_limit_calls is not None else getattr(Config, "ETHERSCAN_RATE_LIMIT_CALLS", 5)
        self.rate_limit_period = rate_limit_period if rate_limit_period is not None else getattr(Config, "ETHERSCAN_RATE_LIMIT_PERIOD", 1.0)
        self.default_retries = default_retries if default_retries is not None else getattr(Config, "ETHERSCAN_REQUEST_RETRIES", 3)
        self.default_backoff_factor = default_backoff_factor if default_backoff_factor is not None else getattr(Config, "ETHERSCAN_REQUEST_BACKOFF_FACTOR", 0.5)
        
        self._request_timestamps = deque()
        self._rate_limit_lock = asyncio.Lock()


        if not self.api_key:
            logging.warning(
                "EtherscanAPI initialized without an API key. Some endpoints may not work or be rate-limited."
            )
        else:
            logging.info(f"EtherscanAPI initialized with API key (first 5 chars): {self.api_key[:5]}...")
        
        if not self.chain_id:
            logging.error("EtherscanAPI initialized without a chain_id. API v2 calls will likely fail.")
        else:
            logging.info(f"EtherscanAPI using chain_id: {self.chain_id}")
        
        logging.info(
            f"EtherscanAPI rate limit: {self.rate_limit_calls} calls / {self.rate_limit_period}s. Retries: {self.default_retries}."
        )


    async def _get_session(self) -> aiohttp.ClientSession:
        """Returns the existing session or creates a new one if none exists."""
        if self._session is None or self._session.closed:
            # You might want to configure connector limits here if needed
            # connector = aiohttp.TCPConnector(limit_per_host=5) # Example
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self):
        """Closes the aiohttp session if it was created by this instance."""
        if self._session and not self._session.closed:
            await self._session.close()
            logging.info("EtherscanAPI session closed.")

    async def _enforce_rate_limit(self):
        """Ensures that the number of requests does not exceed the defined rate limit."""
        async with self._rate_limit_lock:
            current_time = time.monotonic()

            # Remove timestamps older than the rate_limit_period from the left of the deque
            while self._request_timestamps and self._request_timestamps[0] <= current_time - self.rate_limit_period:
                self._request_timestamps.popleft()

            # If we have made rate_limit_calls or more requests within the current window
            if len(self._request_timestamps) >= self.rate_limit_calls:
                # Calculate how long to wait until the oldest request in the window is outside the period
                time_of_oldest_request_in_window = self._request_timestamps[0]
                wait_time = (time_of_oldest_request_in_window + self.rate_limit_period) - current_time
                
                if wait_time > 0:
                    logging.debug(f"Rate limit: sleeping for {wait_time:.3f} seconds. "
                                  f"Requests in window: {len(self._request_timestamps)}.")
                    await asyncio.sleep(wait_time)
            
            # Record the timestamp of the current request attempt
            self._request_timestamps.append(time.monotonic())


    async def _request(self, params: Dict[str, Any], 
                       retries: Optional[int] = None, 
                       backoff_factor: Optional[float] = None) -> Optional[Any]:
        """
        Makes an asynchronous GET request to the Etherscan API with rate limiting and retries.
        """
        current_retries = retries if retries is not None else self.default_retries
        current_backoff_factor = backoff_factor if backoff_factor is not None else self.default_backoff_factor

        request_params = params.copy() # Work with a copy for modifications

        if self.api_key:
            request_params["apikey"] = self.api_key
        else:
            logging.debug("Making Etherscan request without API key.")

        if self.chain_id:
            request_params["chainid"] = self.chain_id
        else:
            logging.warning("Making Etherscan request without chainid. This will likely fail for API v2.")

        last_exception = None
        for attempt in range(current_retries + 1):
            await self._enforce_rate_limit()
            
            session = await self._get_session()
            try:
                logging.debug(f"Etherscan request (attempt {attempt + 1}): URL={self.base_url}, Params={request_params}")
                async with session.get(self.base_url, params=request_params, timeout=30) as response:
                    if not response.ok:
                        error_body = await response.text()
                        logging.error(
                            f"Etherscan API HTTP error: {response.status} {response.reason} for Params {request_params}. "
                            f"Response: {error_body}"
                        )
                        if response.status == 429 or "rate limit" in error_body.lower():
                            raise EtherscanRateLimitError(
                                f"Rate limit exceeded: {response.status}",
                                status_code=response.status,
                                etherscan_message=error_body
                            )
                        raise EtherscanAPIError(
                            f"HTTP error {response.status}: {response.reason}",
                            status_code=response.status,
                            etherscan_message=error_body
                        )

                    json_response = await response.json()
                    logging.debug(f"Etherscan API response: {json_response}")

                    if isinstance(json_response, dict):
                        if json_response.get("status") == "0":
                            etherscan_msg = json_response.get("message", "Error")
                            etherscan_result = json_response.get("result", "")
                            if "max rate limit reached" in str(etherscan_result).lower() or \
                               "rate limit reached" in etherscan_msg.lower() or \
                               "max calls per sec rate limit reached" in str(etherscan_result).lower(): # Added specific error message
                                raise EtherscanRateLimitError(
                                    f"Etherscan API Error (Rate Limit): {etherscan_msg} - {etherscan_result}",
                                    etherscan_message=f"{etherscan_msg} - {etherscan_result}"
                                )
                            logging.warning(
                                f"Etherscan API returned error status: Message='{etherscan_msg}', Result='{etherscan_result}', Params='{request_params}'"
                            )
                            raise EtherscanAPIError(
                                f"Etherscan API Error: {etherscan_msg}",
                                etherscan_message=f"{etherscan_msg} - {etherscan_result}"
                            )
                        return json_response.get("result")
                    else:
                        logging.error(f"Unexpected Etherscan API response format: {json_response}")
                        raise EtherscanAPIError("Unexpected API response format", etherscan_message=str(json_response))

            except EtherscanRateLimitError as e:
                last_exception = e
                if attempt < current_retries:
                    sleep_time = current_backoff_factor * (2 ** attempt)
                    logging.warning(
                        f"Rate limit hit. Retrying in {sleep_time:.2f}s (attempt {attempt + 1}/{current_retries + 1}). Params: {request_params['action'] if 'action' in request_params else 'N/A'}"
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logging.error(f"Rate limit error after {current_retries + 1} attempts. Params: {request_params['action'] if 'action' in request_params else 'N/A'}")
                    raise
            
            except EtherscanAPIError as e: # Non-rate-limit API errors from Etherscan
                raise # Do not retry these by default
            
            except aiohttp.ClientError as e: # Network/Client errors
                last_exception = EtherscanAPIError(f"AIOHTTP ClientError: {e}", etherscan_message=str(e))
                if attempt < current_retries: # Retry these transient errors
                    sleep_time = current_backoff_factor * (2 ** attempt)
                    logging.warning(
                        f"AIOHTTP ClientError: {e}. Retrying in {sleep_time:.2f}s (attempt {attempt + 1}/{current_retries + 1}). Params: {request_params['action'] if 'action' in request_params else 'N/A'}"
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logging.error(f"AIOHTTP ClientError after {current_retries + 1} attempts: {e}. Params: {request_params['action'] if 'action' in request_params else 'N/A'}")
                    raise last_exception from e
            
            except Exception as e:
                logging.error(f"An unexpected error occurred during Etherscan API request for Params {request_params}: {e}", exc_info=True)
                raise EtherscanAPIError(f"Unexpected error: {e}", etherscan_message=str(e)) from e
        
        if last_exception: # Should have been raised within the loop if all retries failed
            raise last_exception
        return None # Should ideally not be reached

    # --- Account Endpoints ---
    async def get_ether_balance_single(self, address: str, tag: str = "latest") -> Optional[str]:
        """
        Get Ether Balance for a single Address.
        Module: account, Action: balance
        """
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": tag,
        }
        return await self._request(params)

    async def get_ether_balance_multiple(self, addresses: List[str], tag: str = "latest") -> Optional[List[Dict[str, str]]]:
        """
        Get Ether Balance for multiple Addresses in a single call.
        Module: account, Action: balancemulti
        """
        if len(addresses) > 20:
            logging.warning("Etherscan get_ether_balance_multiple: Max 20 addresses allowed.")
            # Or raise an error: raise ValueError("Max 20 addresses allowed for balancemulti")
            addresses = addresses[:20]
        
        params = {
            "module": "account",
            "action": "balancemulti",
            "address": ",".join(addresses),
            "tag": tag,
        }
        return await self._request(params)

    async def get_normal_transactions(
        self, address: str, start_block: int = 0, end_block: int = 99999999,
        page: int = 1, offset: int = 10, sort: str = "asc"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of 'Normal' Transactions By Address.
        Module: account, Action: txlist
        Max 10,000 records returned.
        """
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort, # asc or desc
        }
        return await self._request(params)

    async def get_internal_transactions(
        self, address: Optional[str] = None, txhash: Optional[str] = None,
        start_block: int = 0, end_block: int = 99999999,
        page: int = 1, offset: int = 10, sort: str = "asc"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of 'Internal' Transactions by Address or by Transaction Hash.
        Module: account, Action: txlistinternal
        Provide either 'address' or 'txhash'.
        """
        if not address and not txhash:
            raise ValueError("Either address or txhash must be provided for internal transactions.")
        
        params = {
            "module": "account",
            "action": "txlistinternal",
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        }
        if address:
            params["address"] = address
        if txhash:
            params["txhash"] = txhash
        return await self._request(params)

    async def get_erc20_token_transfers(
        self, address: Optional[str] = None, contract_address: Optional[str] = None,
        start_block: int = 0, end_block: int = 99999999,
        page: int = 1, offset: int = 100, sort: str = "asc"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of "ERC20 - Token Transfer Events" by Address.
        Provide 'address' and optionally 'contract_address'.
        Module: account, Action: tokentx
        """
        if not address:
            raise ValueError("Address must be provided for ERC20 token transfers.")
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        }
        if contract_address:
            params["contractaddress"] = contract_address
        return await self._request(params)

    async def get_erc721_token_transfers(
        self, address: Optional[str] = None, contract_address: Optional[str] = None,
        start_block: int = 0, end_block: int = 99999999,
        page: int = 1, offset: int = 100, sort: str = "asc"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of "ERC721 - Token Transfer Events" by Address.
        Provide 'address' and optionally 'contract_address'.
        Module: account, Action: tokennfttx
        """
        if not address:
            raise ValueError("Address must be provided for ERC721 token transfers.")
        params = {
            "module": "account",
            "action": "tokennfttx",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        }
        if contract_address:
            params["contractaddress"] = contract_address
        return await self._request(params)

    # --- Contract Endpoints ---
    async def get_contract_abi(self, address: str) -> Optional[str]: # ABI is usually a JSON string
        """
        Get Contract ABI for Verified Contract Source Codes.
        Module: contract, Action: getabi
        """
        params = {
            "module": "contract",
            "action": "getabi",
            "address": address,
        }
        return await self._request(params)

    # --- Transaction Endpoints ---
    async def get_transaction_receipt_status(self, txhash: str) -> Optional[Dict[str, str]]:
        """
        Check Transaction Receipt Status (Only applicable for Post Byzantium fork transactions).
        Returns '0' for failed, '1' for successful.
        Module: transaction, Action: gettxreceiptstatus
        """
        params = {
            "module": "transaction",
            "action": "gettxreceiptstatus",
            "txhash": txhash,
        }
        return await self._request(params)


    # --- Stats Endpoints ---
    async def get_native_currency_supply(self) -> Optional[str]: # Renamed from get_total_eth_supply
        """
        Get Total Supply of the native currency (Ether for Ethereum, BNB for BSC).
        Module: stats
        Result is in Wei.
        """
        action = "ethsupply" # Default for Ethereum
        if self.chain_id == getattr(Config, "BSC_CHAIN_ID", "56"): # Check if BSC
            action = "bnbsupply"
        # Add other chains here if needed, e.g.:
        # elif self.chain_id == getattr(Config, "POLYGON_CHAIN_ID", "137"):
        #     action = "maticcoinsupply" # Hypothetical, check actual Etherscan-family API for Polygon

        params = {
            "module": "stats",
            "action": action,
        }
        return await self._request(params)

    async def get_native_currency_last_price(self) -> Optional[Dict[str, str]]: # Renamed from get_eth_last_price
        """
        Get Last Price of the native currency (e.g., ETH vs BTC/USD, BNB vs BTC/USD).
        Module: stats
        """
        action = "ethprice" # Default for Ethereum
        price_keys = {'btc': 'ethbtc', 'usd': 'ethusd', 'btc_timestamp': 'ethbtc_timestamp', 'usd_timestamp': 'ethusd_timestamp'}
        if self.chain_id == getattr(Config, "BSC_CHAIN_ID", "56"): # Check if BSC
            action = "bnbprice"
            price_keys = {'btc': 'bnbbtc', 'usd': 'bnbusd', 'btc_timestamp': 'bnbbtc_timestamp', 'usd_timestamp': 'bnbusd_timestamp'}
        # Add other chains here if needed

        params = {
            "module": "stats",
            "action": action,
        }
        # The result parsing might need to be more dynamic if keys change significantly per chain
        # For now, assuming Etherscan-family APIs return similar structures for price with different prefixes
        response = await self._request(params)
        if response: # Ensure response is not None
             # Etherscan API for ethprice returns keys like 'ethbtc', 'ethusd'
             # BscScan API for bnbprice returns keys like 'bnbbtc', 'bnbusd'
             # The self._request method returns the 'result' part of the JSON.
             # The actual keys in the 'result' object are what we need.
             # For simplicity, we'll return the raw dictionary.
             # The caller (test_bsc_client.py) will need to know what keys to expect.
            return response
        return None

    # --- Geth/Parity Proxy Endpoints (Example) ---
    async def eth_get_block_by_number(self, block_number: int, is_full: bool = True) -> Optional[Dict[str, Any]]:
        """
        Proxy for Geth's eth_getBlockByNumber.
        Module: proxy, Action: eth_getBlockByNumber
        Args:
            block_number: Integer of a block number
            is_full: Boolean if true returns the full transaction objects, if false only the hashes of the transactions.
        """
        tag = hex(block_number) # Convert block number to hex string
        boolean = str(is_full).lower()
        params = {
            "module": "proxy",
            "action": "eth_getBlockByNumber",
            "tag": tag,
            "boolean": boolean
        }
        return await self._request(params)

    async def eth_get_transaction_by_hash(self, txhash: str) -> Optional[Dict[str, Any]]:
        """
        Proxy for Geth's eth_getTransactionByHash.
        Module: proxy, Action: eth_getTransactionByHash
        """
        params = {
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": txhash
        }
        return await self._request(params)
