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

    def __init__(self, base_url: str = None, request_interval: float = None, timeout: int = 10):
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
        self.request_interval = request_interval if request_interval is not None else self.REQUEST_INTERVAL_SECONDS
        self.timeout = timeout
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Rebot/1.0 TronScanClient (OOP)"
        })
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
            
            data = response.json()

            # Interpret TronScan API response for account data
            if isinstance(data, list) and data:
                account_data = data[0] # Typically, /account returns a list with one item for a valid address
            elif isinstance(data, dict) and ("address" in data or "balance" in data or "message" in data):
                account_data = data
            else: # Unexpected format or empty list/dict for non-existent
                logger.info("TronScan: Address %s not found or unexpected response format: %s", address, data)
                return None

            # Check if the data actually represents an account or an error message
            if "message" in account_data and "address" not in account_data : # Common error pattern
                logger.info("TronScan: Address %s not found or error: %s", address, account_data.get('message'))
                return None
            if not account_data or ("address" not in account_data and "balance" not in account_data): # If it's an empty dict or lacks key fields
                logger.info("TronScan: Address %s likely not found, data: %s", address, account_data)
                return None

            logger.info("Successfully fetched account info for %s from TronScan.", address)
            return account_data

        except requests.exceptions.HTTPError as http_err:
            logger.error("HTTP error occurred while fetching Tron address %s: %s - Response: %s", address, http_err, getattr(http_err, 'response', None).text if hasattr(http_err, 'response') else "N/A")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error("Connection error occurred while fetching Tron address %s: %s", address, conn_err)
        except requests.exceptions.Timeout as timeout_err:
            logger.error("Timeout error occurred while fetching Tron address %s: %s", address, timeout_err)
        except requests.exceptions.RequestException as req_err:
            logger.error("An error occurred during TronScan API request for %s: %s", address, req_err)
        except ValueError as json_err:  # Includes JSONDecodeError
            logger.error("Failed to decode JSON response from TronScan for %s: %s", address, json_err)
        
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

# Example Usage:
if __name__ == "__main__":
    # Configure logging for example run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    tron_client = TronScanAPI()

    test_address_valid = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # A known valid address (Tron Foundation)
    test_address_invalid_format = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6" # Invalid checksum/length
    test_address_non_existent = "TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" # Syntactically okay, but likely non-existent
    
    logger.info("--- Testing valid address: %s ---", test_address_valid)
    info_valid = tron_client.get_account_info(test_address_valid)
    if info_valid:
        print(f"Info for {test_address_valid}:")
        print(f"  Address: {info_valid.get('address')}")
        # Balance is in SUN (1 TRX = 1,000,000 SUN)
        print(f"  Balance: {info_valid.get('balance', 0) / 1_000_000:.6f} TRX")
        print(f"  Total transactions: {info_valid.get('totalTransactionCount', 'N/A')}")
        print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}")
    else:
        print(f"Could not retrieve info for {test_address_valid}.")
        print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}")

    print("\n")
    logger.info("--- Testing invalid format address: %s ---", test_address_invalid_format)
    info_invalid_format = tron_client.get_account_info(test_address_invalid_format)
    if info_invalid_format:
        print(f"Info for {test_address_invalid_format}: {info_invalid_format}")
    else:
        print(f"Could not retrieve info for {test_address_invalid_format} (as expected for invalid format or non-existent).")
    print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_invalid_format)}")

    print("\n")
    logger.info("--- Testing non-existent address: %s ---", test_address_non_existent)
    info_non_existent = tron_client.get_account_info(test_address_non_existent)
    if info_non_existent:
        print(f"Info for {test_address_non_existent}: {info_non_existent}")
    else:
        print(f"Could not retrieve info for {test_address_non_existent} (as expected for non-existent).")
    print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_non_existent)}")

'''

**Key changes in the OOP version:**

1.  **`TronScanAPI` Class**:
    *   The main logic is now encapsulated within this class.
    *   **`__init__`**:
        *   Initializes `base_url`, `request_interval`, and `timeout`.
        *   Creates a `requests.Session` instance (`self.session`).
        *   Initializes `_last_request_time` for rate limiting.
    *   **`_rate_limit`**: Now a method of the class, using `self._last_request_time` and `self.request_interval`.
    *   **`get_account_info`**:
        *   Is a method of the class.
        *   Uses `self.session`, `self.base_url`, `self.timeout`.
        *   Calls `self._rate_limit()`.
        *   Logging uses `logger.error`, `logger.info` (it's good practice to define a module-level logger).
        *   The logic for interpreting the TronScan API response has been slightly refined to better handle cases where an address might not exist but the API returns 200 OK with a specific message or an empty list/dictionary.
    *   **`is_tron_address_valid_on_chain`**: Also a method, calling `self.get_account_info`.

2.  **Logging**:
    *   A module-level logger (`logger = logging.getLogger(__name__)`) is defined. This allows the application using this module to configure logging centrally.
    *   The `if __name__ == "__main__":` block now includes `logging.basicConfig` to set up basic logging when the script is run directly for testing.

3.  **Example Usage (`if __name__ == "__main__":`)**:
    *   An instance of `TronScanAPI` (`tron_client`) is created.
    *   The methods of this instance are called for testing.

This OOP structure makes the TronScan client more reusable, configurable, and testable. You can create instances of `TronScanAPI` with different configurations if needed.# filepath: /home/user0/rebot/utils/tronscan.py
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

    def __init__(self, base_url: str = None, request_interval: float = None, timeout: int = 10):
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
        self.request_interval = request_interval if request_interval is not None else self.REQUEST_INTERVAL_SECONDS
        self.timeout = timeout
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Rebot/1.0 TronScanClient (OOP)"
        })
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
            
            data = response.json()

            # Interpret TronScan API response for account data
            if isinstance(data, list) and data:
                account_data = data[0] # Typically, /account returns a list with one item for a valid address
            elif isinstance(data, dict) and ("address" in data or "balance" in data or "message" in data):
                account_data = data
            else: # Unexpected format or empty list/dict for non-existent
                logger.info("TronScan: Address %s not found or unexpected response format: %s", address, data)
                return None

            # Check if the data actually represents an account or an error message
            if "message" in account_data and "address" not in account_data : # Common error pattern
                logger.info("TronScan: Address %s not found or error: %s", address, account_data.get('message'))
                return None
            if not account_data or ("address" not in account_data and "balance" not in account_data): # If it's an empty dict or lacks key fields
                logger.info("TronScan: Address %s likely not found, data: %s", address, account_data)
                return None

            logger.info("Successfully fetched account info for %s from TronScan.", address)
            return account_data

        except requests.exceptions.HTTPError as http_err:
            logger.error("HTTP error occurred while fetching Tron address %s: %s - Response: %s", address, http_err, getattr(http_err, 'response', None).text if hasattr(http_err, 'response') else "N/A")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error("Connection error occurred while fetching Tron address %s: %s", address, conn_err)
        except requests.exceptions.Timeout as timeout_err:
            logger.error("Timeout error occurred while fetching Tron address %s: %s", address, timeout_err)
        except requests.exceptions.RequestException as req_err:
            logger.error("An error occurred during TronScan API request for %s: %s", address, req_err)
        except ValueError as json_err:  # Includes JSONDecodeError
            logger.error("Failed to decode JSON response from TronScan for %s: %s", address, json_err)
        
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

# Example Usage:
if __name__ == "__main__":
    # Configure logging for example run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    tron_client = TronScanAPI()

    test_address_valid = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # A known valid address (Tron Foundation)
    test_address_invalid_format = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6" # Invalid checksum/length
    test_address_non_existent = "TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" # Syntactically okay, but likely non-existent
    
    logger.info("--- Testing valid address: %s ---", test_address_valid)
    info_valid = tron_client.get_account_info(test_address_valid)
    if info_valid:
        print(f"Info for {test_address_valid}:")
        print(f"  Address: {info_valid.get('address')}")
        # Balance is in SUN (1 TRX = 1,000,000 SUN)
        print(f"  Balance: {info_valid.get('balance', 0) / 1_000_000:.6f} TRX")
        print(f"  Total transactions: {info_valid.get('totalTransactionCount', 'N/A')}")
        print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}")
    else:
        print(f"Could not retrieve info for {test_address_valid}.")
        print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_valid)}")

    print("\n")
    logger.info("--- Testing invalid format address: %s ---", test_address_invalid_format)
    info_invalid_format = tron_client.get_account_info(test_address_invalid_format)
    if info_invalid_format:
        print(f"Info for {test_address_invalid_format}: {info_invalid_format}")
    else:
        print(f"Could not retrieve info for {test_address_invalid_format} (as expected for invalid format or non-existent).")
    print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_invalid_format)}")

    print("\n")
    logger.info("--- Testing non-existent address: %s ---", test_address_non_existent)
    info_non_existent = tron_client.get_account_info(test_address_non_existent)
    if info_non_existent:
        print(f"Info for {test_address_non_existent}: {info_non_existent}")
    else:
        print(f"Could not retrieve info for {test_address_non_existent} (as expected for non-existent).")
    print(f"  Is valid on chain: {tron_client.is_tron_address_valid_on_chain(test_address_non_existent)}")

```

**Key changes in the OOP version:**

1.  **`TronScanAPI` Class**:
    *   The main logic is now encapsulated within this class.
    *   **`__init__`**:
        *   Initializes `base_url`, `request_interval`, and `timeout`.
        *   Creates a `requests.Session` instance (`self.session`).
        *   Initializes `_last_request_time` for rate limiting.
    *   **`_rate_limit`**: Now a method of the class, using `self._last_request_time` and `self.request_interval`.
    *   **`get_account_info`**:
        *   Is a method of the class.
        *   Uses `self.session`, `self.base_url`, `self.timeout`.
        *   Calls `self._rate_limit()`.
        *   Logging uses `logger.error`, `logger.info` (it's good practice to define a module-level logger).
        *   The logic for interpreting the TronScan API response has been slightly refined to better handle cases where an address might not exist but the API returns 200 OK with a specific message or an empty list/dictionary.
    *   **`is_tron_address_valid_on_chain`**: Also a method, calling `self.get_account_info`.

2.  **Logging**:
    *   A module-level logger (`logger = logging.getLogger(__name__)`) is defined. This allows the application using this module to configure logging centrally.
    *   The `if __name__ == "__main__":` block now includes `logging.basicConfig` to set up basic logging when the script is run directly for testing.

3.  **Example Usage (`if __name__ == "__main__":`)**:
    *   An instance of `TronScanAPI` (`tron_client`) is created.
    *   The methods of this instance are called for testing.

This OOP structure makes the TronScan client more reusable, configurable, and testable. You can create instances of `TronScanAPI` with different configurations if needed.

'''