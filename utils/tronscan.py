"""Module utils/tronscan.py
This module provides a client for interacting with the TronScan API to fetch account and contract information.
It includes methods to check if an address is a smart contract, fetch basic account info, and validate Tron addresses.
"""

import requests
import logging
import time

# Configure logging - can be configured by the application using this module
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TronScanAPI:
    """
    A client for interacting with the TronScan API.
    """

    DEFAULT_BASE_URL = "https://apilist.tronscan.org/api"
    REQUEST_INTERVAL_SECONDS = 1  # Default interval between requests

    def __init__(
        self, base_url: str = None, request_interval: float = None, timeout: int = 10
    ):
        """
        Initializes the TronScanAPI client.

        Args:
            base_url: The base URL for the TronScan API.
                      Defaults to "https://apilist.tronscan.org/api".
            request_interval: Minimum time in seconds between consecutive requests to the API.
                              Defaults to 1 second.
            timeout: Request timeout in seconds. Defaults to 10.
        """
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.request_interval = (
            request_interval
            if request_interval is not None
            else self.REQUEST_INTERVAL_SECONDS
        )
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Rebot/1.0 TronScanClient (OOP)"})
        self._last_request_time = 0

    def _rate_limit(self):
        """Ensures that requests do not exceed the defined interval."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_time = time.time()

    def get_account_info(self, address: str) -> dict | None:
        """
        Fetches account information for a given Tron address from TronScan.

        Args:
            address: The Tron address (e.g., TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t).

        Returns:
            A dictionary containing the account information if successful, None otherwise.
        """
        if not address or not isinstance(address, str):
            logger.error("Invalid address provided for TronScan lookup: %s", address)
            return None

        self._rate_limit()
        endpoint = f"{self.base_url}/account"
        params = {"address": address}

        try:
            response = self.session.get(endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
            logger.info("Fetched account info for %s: %s", address, response.text)
            data = response.json()

            # Interpret TronScan API response for account data
            if isinstance(data, list) and data:
                account_data = data[
                    0
                ]  # Typically, /account returns a list with one item for a valid address
            elif isinstance(data, dict) and (
                "address" in data or "balance" in data or "message" in data
            ):
                account_data = data
            else:  # Unexpected format or empty list/dict for non-existent
                logger.info(
                    "TronScan: Address %s not found or unexpected response format: %s",
                    address,
                    data,
                )
                return None

            # Check if the data actually represents an account or an error message
            if (
                "message" in account_data and "address" not in account_data
            ):  # Common error pattern
                logger.info(
                    "TronScan: Address %s not found or error: %s",
                    address,
                    account_data.get("message"),
                )
                return None
            if not account_data or (
                "address" not in account_data and "balance" not in account_data
            ):  # If it's an empty dict or lacks key fields
                logger.info(
                    "TronScan: Address %s likely not found, data: %s",
                    address,
                    account_data,
                )
                return None

            logger.info(
                "Successfully fetched account info for %s from TronScan.", address
            )
            return account_data

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                "HTTP error occurred while fetching Tron address %s: %s - Response: %s",
                address,
                http_err,
                (
                    getattr(http_err, "response", None).text
                    if hasattr(http_err, "response")
                    else "N/A"
                ),
            )
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(
                "Connection error occurred while fetching Tron address %s: %s",
                address,
                conn_err,
            )
        except requests.exceptions.Timeout as timeout_err:
            logger.error(
                "Timeout error occurred while fetching Tron address %s: %s",
                address,
                timeout_err,
            )
        except requests.exceptions.RequestException as req_err:
            logger.error(
                "An error occurred during TronScan API request for %s: %s",
                address,
                req_err,
            )
        except ValueError as json_err:  # Includes JSONDecodeError
            logger.error(
                "Failed to decode JSON response from TronScan for %s: %s",
                address,
                json_err,
            )

        return None

    def is_tron_address_valid_on_chain(self, address: str) -> bool:
        """
        Checks if a Tron address exists or has activity on the Tron blockchain
        by fetching its account info.

        Args:
            address: The Tron address to check.

        Returns:
            True if the address information can be fetched (implying it exists or has existed),
            False otherwise.
        """
        account_info = self.get_account_info(address)
        return account_info is not None

    def get_basic_account_info(self, address: str) -> dict | None:
        """
        Fetches basic account information for a given Tron address from TronScan
        optimized for scam analysis. Returns only essential fields to reduce API load
        and token usage in AI analysis. Now includes token balances for enriched analysis.

        Args:
            address: The Tron address (e.g., TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t).

        Returns:
            A dictionary containing basic account information if successful, None otherwise.
            Includes: address, balance, createTime, totalTransactionCount, tokenBalances
        """
        if not address or not isinstance(address, str):
            logger.error(
                "Invalid address provided for TronScan basic lookup: %s", address
            )
            return None

        self._rate_limit()

        # Get basic account info
        account_endpoint = f"{self.base_url}/account"
        account_params = {"address": address}

        try:
            # Fetch account data
            account_response = self.session.get(
                account_endpoint, params=account_params, timeout=self.timeout
            )
            account_response.raise_for_status()

            account_data_raw = account_response.json()

            # Interpret TronScan API response for account data
            if isinstance(account_data_raw, list) and account_data_raw:
                account_data = account_data_raw[0]
            elif isinstance(account_data_raw, dict) and (
                "address" in account_data_raw
                or "balance" in account_data_raw
                or "message" in account_data_raw
            ):
                account_data = account_data_raw
            else:
                logger.info(
                    "TronScan: Address %s not found or unexpected response format: %s",
                    address,
                    account_data_raw,
                )
                return None

            # Check if the data actually represents an account or an error message
            if "message" in account_data and "address" not in account_data:
                logger.info(
                    "TronScan: Address %s not found or error: %s",
                    address,
                    account_data.get("message"),
                )
                return None
            if not account_data or (
                "address" not in account_data and "balance" not in account_data
            ):
                logger.info(
                    "TronScan: Address %s likely not found, data: %s",
                    address,
                    account_data,
                )
                return None

            # Extract basic account info with correct field names
            basic_info = {
                "address": account_data.get("address"),
                "balance": account_data.get("balance", 0),
                "createTime": account_data.get(
                    "date_created"
                ),  # Fixed: use date_created instead of createTime
                "totalTransactionCount": account_data.get("totalTransactionCount", 0),
            }

            # For smart contracts, try to get more accurate creation time from contract endpoint
            if self.is_smart_contract(address):
                try:
                    contract_info = self.get_contract_info(address)
                    if (
                        contract_info
                        and contract_info.get("date_created")
                        and contract_info.get("date_created") != 0
                    ):
                        basic_info["createTime"] = contract_info["date_created"]
                        logger.info(
                            f"Updated createTime for smart contract {address} from contract data: {contract_info['date_created']}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to get contract creation time for {address}: {e}"
                    )

            # Fetch token balances for enriched analysis
            try:
                self._rate_limit()  # Rate limit for second API call
                tokens_endpoint = f"{self.base_url}/account/tokens"
                tokens_params = {
                    "address": address,
                    "start": 0,
                    "limit": 20,
                }  # Get top 20 tokens

                tokens_response = self.session.get(
                    tokens_endpoint, params=tokens_params, timeout=self.timeout
                )
                tokens_response.raise_for_status()

                tokens_data = tokens_response.json()

                # Process token data
                token_balances = []
                if isinstance(tokens_data, dict) and "data" in tokens_data:
                    for token in tokens_data.get("data", [])[
                        :10
                    ]:  # Limit to top 10 for AI analysis
                        if isinstance(token, dict):
                            token_info = {
                                "tokenName": token.get("tokenName", "Unknown"),
                                "tokenSymbol": token.get("tokenSymbol", ""),
                                "balance": token.get("balance", "0"),
                                "tokenDecimal": token.get("tokenDecimal", 0),
                                "tokenType": token.get("tokenType", ""),
                                "tokenId": token.get("tokenId", ""),
                            }
                            token_balances.append(token_info)

                basic_info["tokenBalances"] = token_balances
                logger.info(
                    "Successfully fetched %d token balances for %s",
                    len(token_balances),
                    address,
                )

            except Exception as token_err:
                logger.warning(
                    "Failed to fetch token balances for %s: %s", address, token_err
                )
                basic_info["tokenBalances"] = []  # Empty list if token fetch fails

            logger.info(
                "Successfully fetched basic account info for %s from TronScan.", address
            )
            return basic_info

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                "HTTP error occurred while fetching basic Tron address %s: %s",
                address,
                http_err,
            )
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(
                "Connection error occurred while fetching basic Tron address %s: %s",
                address,
                conn_err,
            )
        except requests.exceptions.Timeout as timeout_err:
            logger.error(
                "Timeout error occurred while fetching basic Tron address %s: %s",
                address,
                timeout_err,
            )
        except requests.exceptions.RequestException as req_err:
            logger.error(
                "An error occurred during TronScan basic API request for %s: %s",
                address,
                req_err,
            )
        except ValueError as json_err:
            logger.error(
                "Failed to decode JSON response from TronScan for basic info %s: %s",
                address,
                json_err,
            )

        return None

    def is_smart_contract(self, address: str) -> bool:
        """
        Checks if a TRON address is a smart contract by querying the contract endpoint.

        Args:
            address: The TRON address to check.

        Returns:
            True if the address is a smart contract, False if it's a regular wallet address.
        """
        if not address or not isinstance(address, str):
            return False

        self._rate_limit()

        # First check the account info to see if it's a Super Representative or other special account
        account_info = self.get_account_info(address)
        if account_info:
            # Check if this is a Super Representative (they have special account status but are not contracts)
            if account_info.get("is_sr", False) or account_info.get(
                "is_committee", False
            ):
                logger.info(
                    f"Address {address} is a Super Representative or Committee member, treating as wallet"
                )
                return False

            # Check account type - some numeric codes indicate special account types
            account_type = account_info.get("accountType")
            if account_type == 1:  # Normal account
                logger.info(
                    f"Address {address} is a normal account type, treating as wallet"
                )
                return False

        # Query the contract endpoint directly
        contract_endpoint = f"{self.base_url}/contract"
        contract_params = {"contract": address}

        try:
            response = self.session.get(
                contract_endpoint, params=contract_params, timeout=self.timeout
            )
            response.raise_for_status()

            contract_data = response.json()

            # Check if we get actual contract data back
            if isinstance(contract_data, dict) and "data" in contract_data:
                data_list = contract_data["data"]
                if isinstance(data_list, list) and len(data_list) > 0:
                    contract_info = data_list[0]

                    # Count meaningful contract indicators
                    meaningful_indicators = 0

                    # Check for strong contract indicators
                    if contract_info.get("name"):
                        meaningful_indicators += 1
                    if contract_info.get("tag1"):
                        meaningful_indicators += 1
                    if contract_info.get("creator") and isinstance(
                        contract_info.get("creator"), dict
                    ):
                        creator_data = contract_info.get("creator")
                        # Only count creator if it has meaningful data (not just empty fields)
                        if creator_data.get("address") or creator_data.get("txHash"):
                            meaningful_indicators += 1
                    if contract_info.get("tokenInfo") and contract_info.get(
                        "tokenInfo"
                    ):
                        meaningful_indicators += 1
                    if contract_info.get("methodMap") and contract_info.get(
                        "methodMap"
                    ):
                        meaningful_indicators += 1
                    if contract_info.get("description"):
                        meaningful_indicators += 1

                    # verify_status alone is not a strong indicator as it can be 0 for non-contracts
                    # Only count it if we have other indicators
                    if (
                        meaningful_indicators >= 1
                        and contract_info.get("verify_status") is not None
                    ):
                        meaningful_indicators += 0.5  # Half weight for verify_status

                    # If we have at least 2 meaningful indicators, it's likely a contract
                    if meaningful_indicators >= 2:
                        logger.info(
                            f"Address {address} detected as smart contract with {meaningful_indicators} indicators"
                        )
                        return True
                    else:
                        logger.info(
                            f"Address {address} detected as wallet with {meaningful_indicators} indicators"
                        )
                        return False

            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking contract status for {address}: {e}")
            return False

    def get_contract_info(self, contract_address: str) -> dict | None:
        """
        Fetches smart contract information for a given TRON contract address.

        Args:
            contract_address: The TRON contract address.

        Returns:
            A dictionary containing contract information if successful, None otherwise.
            Includes: address, balance, createTime, totalTransactionCount, contractType, creator, etc.
        """
        if not contract_address or not isinstance(contract_address, str):
            logger.error(
                "Invalid contract address provided for TronScan contract lookup: %s",
                contract_address,
            )
            return None

        self._rate_limit()

        # Get basic contract info
        contract_endpoint = f"{self.base_url}/contract"
        contract_params = {"contract": contract_address}

        try:
            # Fetch contract data
            contract_response = self.session.get(
                contract_endpoint, params=contract_params, timeout=self.timeout
            )
            contract_response.raise_for_status()

            contract_data_raw = contract_response.json()

            # Also get account data for basic info
            account_info = self.get_account_info(contract_address)

            if not contract_data_raw and not account_info:
                logger.info("TronScan: Contract %s not found", contract_address)
                return None

            # Combine contract and account data
            contract_info = {
                "address": contract_address,
                "isContract": True,
                "balance": account_info.get("balance", 0) if account_info else 0,
                "date_created": (
                    account_info.get("date_created") if account_info else None
                ),
                "totalTransactionCount": (
                    account_info.get("totalTransactionCount", 0) if account_info else 0
                ),
                "accountType": (
                    account_info.get("accountType") if account_info else "Contract"
                ),
            }

            # Parse contract-specific information from the correct data structure
            if (
                isinstance(contract_data_raw, dict)
                and "data" in contract_data_raw
                and contract_data_raw["data"]
            ):
                contract_data = contract_data_raw["data"][
                    0
                ]  # Get the first (and usually only) contract data

                # Prioritize contract creation time over account creation time
                contract_creation_time = contract_data.get("date_created")
                if contract_creation_time and contract_creation_time != 0:
                    contract_info["date_created"] = contract_creation_time

                contract_info.update(
                    {
                        "contractType": contract_data.get("contractType"),
                        "creator": contract_data.get("creator"),
                        "name": contract_data.get("name"),
                        "tag1": contract_data.get("tag1"),
                        "description": contract_data.get("description"),
                        "website": contract_data.get("website"),
                        "github": contract_data.get("github"),
                        "email": contract_data.get("email"),
                        "whitepaper": contract_data.get("whitepaper"),
                        "verified": contract_data.get("verify_status", 0)
                        > 0,  # verify_status > 0 means verified
                        "verify_status": contract_data.get("verify_status", 0),
                        "compiler_version": contract_data.get("compiler_version"),
                        "social_media": contract_data.get("social_media", []),
                        "methodMap": contract_data.get("methodMap", {}),
                        "vip": contract_data.get("vip", False),
                        "publicTag": contract_data.get("publicTag"),
                        "is_proxy": contract_data.get("is_proxy", False),
                    }
                )

                # Add token information if available
                if contract_data.get("tokenInfo"):
                    token_data = contract_data["tokenInfo"]
                    contract_info["tokenInfo"] = {
                        "symbol": token_data.get("tokenAbbr"),
                        "name": token_data.get("tokenName"),
                        "decimals": token_data.get("tokenDecimal"),
                        "tokenType": token_data.get("tokenType", "TRC20"),
                        "vip": token_data.get("vip", False),
                        "tokenId": token_data.get("tokenId"),
                        "issuerAddr": token_data.get("issuerAddr"),
                    }
                    logger.info(
                        "Successfully parsed token info for contract %s",
                        contract_address,
                    )
            else:
                # Fallback: Add contract-specific information from the raw response (old format)
                contract_info.update(
                    {
                        "contractType": contract_data_raw.get("contractType"),
                        "creator": contract_data_raw.get("creator"),
                        "name": contract_data_raw.get("name"),
                        "tag1": contract_data_raw.get("tag1"),
                        "description": contract_data_raw.get("description"),
                        "website": contract_data_raw.get("website"),
                        "github": contract_data_raw.get("github"),
                        "email": contract_data_raw.get("email"),
                        "whitepaper": contract_data_raw.get("whitepaper"),
                        "verified": contract_data_raw.get("verified", False),
                        "compiler_version": contract_data_raw.get("compiler_version"),
                        "social_media": contract_data_raw.get("social_media", []),
                    }
                )

            logger.info(
                "Successfully fetched contract info for %s from TronScan.",
                contract_address,
            )
            return contract_info

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                "HTTP error occurred while fetching contract %s: %s",
                contract_address,
                http_err,
            )
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(
                "Connection error occurred while fetching contract %s: %s",
                contract_address,
                conn_err,
            )
        except requests.exceptions.Timeout as timeout_err:
            logger.error(
                "Timeout error occurred while fetching contract %s: %s",
                contract_address,
                timeout_err,
            )
        except requests.exceptions.RequestException as req_err:
            logger.error(
                "An error occurred during TronScan contract API request for %s: %s",
                contract_address,
                req_err,
            )
        except ValueError as json_err:
            logger.error(
                "Failed to decode JSON response from TronScan for contract %s: %s",
                contract_address,
                json_err,
            )

        return None


# Example Usage:
if __name__ == "__main__":
    # Configure logging for example run
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    tron_client = TronScanAPI()

    test_address_valid = (
        "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # A known valid address (Tron Foundation)
    )
    test_address_invalid_format = (
        "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6"  # Invalid checksum/length
    )
    test_address_non_existent = "TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"  # Syntactically okay, but likely non-existent

    logger.info("--- Testing valid address: %s ---", test_address_valid)
    info_valid = tron_client.get_account_info(test_address_valid)
    if info_valid:
        print(f"Info for {test_address_valid}:")
        print(f"  Address: {info_valid.get('address')}")
        # Balance is in SUN (1 TRX = 1,000,000 SUN)
        print(f"  Balance: {info_valid.get('balance', 0) / 1_000_000:.6f} TRX")
        print(f"  Total transactions: {info_valid.get('totalTransactionCount', 'N/A')}")
        print(
            f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}"
        )
    else:
        print(f"Could not retrieve info for {test_address_valid}.")
        print(
            f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}"
        )

    print("\n")
    logger.info(
        "--- Testing invalid format address: %s ---", test_address_invalid_format
    )
    info_invalid_format = tron_client.get_account_info(test_address_invalid_format)
    if info_invalid_format:
        print(f"Info for {test_address_invalid_format}: {info_invalid_format}")
    else:
        print(
            f"Could not retrieve info for {test_address_invalid_format} (as expected for invalid format or non-existent)."
        )
    print(
        f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_invalid_format)}"
    )

    print("\n")
    logger.info("--- Testing non-existent address: %s ---", test_address_non_existent)
    info_non_existent = tron_client.get_account_info(test_address_non_existent)
    if info_non_existent:
        print(f"Info for {test_address_non_existent}: {info_non_existent}")
    else:
        print(
            f"Could not retrieve info for {test_address_non_existent} (as expected for non-existent)."
        )
    print(
        f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_non_existent)}"
    )

    print("\n")
    logger.info(
        "--- Testing basic info for valid address (scam analysis): %s ---",
        test_address_valid,
    )
    basic_info_valid = tron_client.get_basic_account_info(test_address_valid)
    if basic_info_valid:
        print(f"Basic info for {test_address_valid}:")
        print(f"  Address: {basic_info_valid.get('address')}")
        print(f"  Balance: {basic_info_valid.get('balance', 0) / 1_000_000:.6f} TRX")
        print(
            f"  Creation time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(basic_info_valid.get('createTime') / 1000))}"
        )
        print(
            f"  Total transactions: {basic_info_valid.get('totalTransactionCount', 'N/A')}"
        )
    else:
        print(f"Could not retrieve basic info for {test_address_valid}.")

    print("\n")
    logger.info(
        "--- Testing basic info for non-existent address (scam analysis): %s ---",
        test_address_non_existent,
    )
    basic_info_non_existent = tron_client.get_basic_account_info(
        test_address_non_existent
    )
    if basic_info_non_existent:
        print(f"Basic info for {test_address_non_existent}: {basic_info_non_existent}")
    else:
        print(
            f"Could not retrieve basic info for {test_address_non_existent} (as expected for non-existent)."
        )


def get_tron_account_changes(address: str, previous_data: dict = None):
    """
    Fetch detailed account info for a given address using TronScan v2 API and compare with previous_data.
    Returns a dict describing what changed: { 'trx_change': ..., 'token_changes': [...], 'tx_count_change': ..., ... }
    previous_data should be a dict from a prior v2 API call.
    """


    import datetime
    API_URL = f"https://apilist.tronscanapi.com/api/accountv2?address={address}"
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        current = response.json()
        logger.debug("Fetched TronScan v2 account info for %s: %s", address, current)
    except Exception as e:
        logger.error(f"Failed to fetch TronScan v2 account info for {address}: {e}")
        changes = {"changed": False, "reason": f"API error: {e}", "details": {}}
        return changes, None, None
    if not current or not isinstance(current, dict):
        changes = {"changed": False, "reason": "No account info found", "details": {}}
        return changes, current, current

    # Keys to check for changes
    root_keys = [
        "transactions_out", "balance", "transactions_in", "totalTransactionCount",
        "transactions", "latest_operation_time", "activated"
    ]
    static_keys = ["publicTag", "date_created", "address"]

    # Helper to get value safely
    def safe_get(d, k, default=None):
        return d[k] if isinstance(d, dict) and k in d else default

    changes = {"changed": False, "details": {}}
    details = {}
    # Compare root keys
    for k in root_keys:
        prev_v = safe_get(previous_data, k) if previous_data else None
        curr_v = safe_get(current, k)
        if prev_v != curr_v:
            changes["changed"] = True
            details[k] = {"prev": prev_v, "curr": curr_v}
        else:
            details[k] = {"curr": curr_v}

    # Parse withPriceTokens
    prev_tokens = safe_get(previous_data, "withPriceTokens", []) if previous_data else []
    curr_tokens = safe_get(current, "withPriceTokens", [])
    token_changes = []
    # Build token dicts by tokenId for easy comparison
    def token_map(tokens):
        m = {}
        for t in tokens:
            tid = safe_get(t, "tokenId")
            if tid:
                m[tid] = t
        return m
    prev_map = token_map(prev_tokens)
    curr_map = token_map(curr_tokens)
    all_token_ids = set(prev_map.keys()) | set(curr_map.keys())
    for tid in all_token_ids:
        prev_t = prev_map.get(tid, {})
        curr_t = curr_map.get(tid, {})
        token_diff = {}
        for tk in ["balance", "tokenName", "tokenAbbr", "amount"]:
            prev_v = safe_get(prev_t, tk)
            curr_v = safe_get(curr_t, tk)
            if prev_v != curr_v:
                changes["changed"] = True
                token_diff[tk] = {"prev": prev_v, "curr": curr_v}
            else:
                token_diff[tk] = {"curr": curr_v}
        token_diff["tokenId"] = tid
        token_changes.append(token_diff)
    details["withPriceTokens"] = token_changes

    # Always include static info
    for k in static_keys:
        v = safe_get(current, k)
        details[k] = v
    # Human readable date_created and latest_operation_time
    def human_ts(ts):
        try:
            if ts:
                # TronScan returns ms timestamps
                return datetime.datetime.utcfromtimestamp(int(ts)/1000).strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            pass
        return None
    details["date_created_human"] = human_ts(safe_get(current, "date_created"))
    details["latest_operation_time_human"] = human_ts(safe_get(current, "latest_operation_time"))

    changes["details"] = details
    return changes, current, current