"""
test_bsc_client.py
Example usage and test functions for EtherscanAPI client, configured for BscScan.
"""
import asyncio
import logging
from decimal import Decimal

from config.config import Config # Assuming Config stores the API key
from .client import EtherscanAPI, EtherscanAPIError, EtherscanRateLimitError

# Configure logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- BSC Specific Configuration ---
# Use Etherscan's base URL and API key, but with BSC Chain ID from Config
BSC_API_BASE_URL = getattr(Config, "ETHERSCAN_API_BASE_URL", "https://api.etherscan.io/api/v2")
BSC_API_KEY = getattr(Config, "ETHERSCAN_API_KEY", None) # Use Etherscan API Key
# BSC_CHAIN_ID is now imported from Config


async def main_test_bsc():
    """
    Main function to test EtherscanAPI client methods against BscScan.
    """
    # Initialize EtherscanAPI client for BscScan
    # The EtherscanAPI client will use its default base_url from Config if not overridden here.
    # We are specifically setting the chain_id for BSC.
    api_client = EtherscanAPI(
        api_key=BSC_API_KEY,
        base_url=BSC_API_BASE_URL, # Explicitly pass the base_url
        chain_id=Config.BSC_CHAIN_ID # Use BSC_CHAIN_ID from Config
        # Rate limit parameters will use defaults from Config or EtherscanAPI class
    )

    if not api_client.api_key:
        logging.warning("BSC_API_KEY (or ETHERSCAN_API_KEY) not found in config. Some endpoints might be rate-limited or require it.")

    # --- Replace with actual BSC addresses and data for testing ---
    # Example: PancakeSwap Router V2 address on BSC
    example_bsc_address = "0x933F25c19642822C08D8E97bd1D5C48328C0f08E"
    # Example: USDC token contract address on BSC
    bsc_usd_contract_address_bsc = "0x55d398326f99059fF775485246999027B3197955"
    # Example: A known BSC transaction hash (e.g., a PancakeSwap V2 swap)
    example_bsc_tx_hash = "0xe63f305aa0cf489312dcb221439f5ae3cf6dc92b01e916e4a599cc3db180f370" # Replace if this becomes invalid
    # Example: A recent BSC block number (check BscScan for a recent one if tests fail)
    example_bsc_block = 51089015 # As of early June 2024, this should be a valid past block. Adjust if needed


    print(f"\n\033[93m--- Testing get_ether_balance_single (BNB Balance) for {example_bsc_address} ---\033[0m")
    try:
        balance_wei = await api_client.get_ether_balance_single(example_bsc_address)
        if balance_wei is not None:
            balance_bnb = Decimal(balance_wei) / Decimal("1e18")
            print(f"Balance for {example_bsc_address}: {balance_bnb:.6f} BNB ({balance_wei} Wei)")
        else:
            print(f"Failed to get balance for {example_bsc_address} or address not found.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_ether_balance_single: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_ether_balance_single: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_ether_balance_multiple (BNB Balances) for {example_bsc_address} & {bsc_usd_contract_address_bsc} ---\033[0m")
    try:
        balances = await api_client.get_ether_balance_multiple([example_bsc_address, bsc_usd_contract_address_bsc])
        if balances:
            for acc_balance in balances:
                balance_bnb = Decimal(acc_balance.get('balance', '0')) / Decimal("1e18")
                print(f"  Account: {acc_balance.get('account')}, Balance: {balance_bnb:.6f} BNB")
        else:
            print("Failed to get multiple balances.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_ether_balance_multiple: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_ether_balance_multiple: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


    print(f"\n\033[93m--- Testing get_normal_transactions for {example_bsc_address} (last 2) ---\033[0m")
    try:
        transactions = await api_client.get_normal_transactions(example_bsc_address, page=1, offset=2, sort="desc")
        if transactions:
            print(f"Found {len(transactions)} normal transactions (showing last 2):")
            for tx in transactions:
                value_bnb = Decimal(tx.get('value', '0')) / Decimal("1e18")
                print(f"  TxHash: {tx.get('hash')[:15]}..., From: {tx.get('from')[:10]}..., To: {tx.get('to')[:10]}..., Value: {value_bnb:.4f} BNB, Time: {tx.get('timeStamp')}")
        else:
            print("No normal transactions found or failed to fetch.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_normal_transactions: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_normal_transactions: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_erc20_token_transfers for {example_bsc_address} with BUSD (last 2) ---\033[0m")
    try:
        erc20_transfers = await api_client.get_erc20_token_transfers(
            address=example_bsc_address,
            contract_address=bsc_usd_contract_address_bsc,
            page=1, offset=2, sort="desc"
        )
        if erc20_transfers:
            print(f"Found {len(erc20_transfers)} ERC20 BUSD transfers (showing last 2):")
            for tx in erc20_transfers:
                token_decimals = int(tx.get('tokenDecimal', '18')) # BUSD has 18 decimals
                value_token = Decimal(tx.get('value', '0')) / (Decimal('10') ** token_decimals)
                print(f"  TxHash: {tx.get('hash')[:15]}..., From: {tx.get('from')[:10]}..., To: {tx.get('to')[:10]}..., Value: {value_token} {tx.get('tokenSymbol')}")
        else:
            print("No ERC20 BUSD transfers found or failed to fetch.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_erc20_token_transfers: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_erc20_token_transfers: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_contract_abi for BUSD ({bsc_usd_contract_address_bsc}) ---\033[0m")
    try:
        abi = await api_client.get_contract_abi(bsc_usd_contract_address_bsc)
        if abi:
            print(f"ABI for {bsc_usd_contract_address_bsc} (first 100 chars): {abi[:100]}...")
        else:
            print(f"Failed to get ABI for {bsc_usd_contract_address_bsc}.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_contract_abi: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_contract_abi: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_bnb_supply ---\033[0m")
    try:
        supply_wei = await api_client.get_native_currency_supply() # Changed method call
        if supply_wei:
            supply_bnb = Decimal(supply_wei) / Decimal("1e18")
            print(f"Total BNB Supply: {supply_bnb:,.2f} BNB ({supply_wei} Wei)")
        else:
            print("Failed to get total BNB supply.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_bnb_supply: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_bnb_supply: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print("\n\033[93m--- Testing get_bnb_last_price ---\033[0m")
    try:
        price_info = await api_client.get_native_currency_last_price() # Method call is correct
        if price_info:
            # Adjust to expect 'ethbtc' and 'ethusd' as per the actual API response observed
            # when using Etherscan's endpoint with chainid=56 and action=bnbprice.
            bnb_btc_price = price_info.get('ethbtc') # Changed from 'bnbbtc'
            bnb_usd_price = price_info.get('ethusd') # Changed from 'bnbusd'
            bnb_btc_timestamp = price_info.get('ethbtc_timestamp') # Changed from 'bnbbtc_timestamp'
            bnb_usd_timestamp = price_info.get('ethusd_timestamp') # Changed from 'bnbusd_timestamp'

            print(f"BNB Last Price: BNB/BTC = {bnb_btc_price}, BNB/USD = {bnb_usd_price}")
            print(f"  Timestamp: BNB/BTC = {bnb_btc_timestamp}, BNB/USD = {bnb_usd_timestamp}")
        else:
            print("Failed to get BNB last price.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_bnb_last_price: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_bnb_last_price: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing eth_get_block_by_number for BSC block {example_bsc_block} ---\033[0m")
    try:
        block_data = await api_client.eth_get_block_by_number(example_bsc_block, is_full=False)
        if block_data:
            print(f"Block {example_bsc_block} Data (partial): Hash: {block_data.get('hash')}, Miner: {block_data.get('miner')}, Tx count: {len(block_data.get('transactions', []))}")
        else:
            print(f"Failed to get block {example_bsc_block} data.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for eth_get_block_by_number: {e}")
    except EtherscanAPIError as e:
        print(f"API error for eth_get_block_by_number: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing eth_get_transaction_by_hash for BSC Tx {example_bsc_tx_hash[:20]}... ---\033[0m")
    try:
        tx_data = await api_client.eth_get_transaction_by_hash(example_bsc_tx_hash)
        if tx_data:
            print(f"Transaction {example_bsc_tx_hash[:20]}... Data (partial): From: {tx_data.get('from')}, To: {tx_data.get('to')}, Value: {tx_data.get('value')}")
        else:
            print(f"Failed to get transaction {example_bsc_tx_hash[:20]}... data.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for eth_get_transaction_by_hash: {e}")
    except EtherscanAPIError as e:
        print(f"API error for eth_get_transaction_by_hash: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


    await api_client.close_session()

if __name__ == "__main__":
    # To run this test directly:
    # Ensure you are in the /home/user0/rebot/ directory
    # Then run: python -m extapi.etherscan.test_bsc_client
    # Make sure config/config.py has ETHERSCAN_API_KEY (or a specific BSC_API_KEY) and other relevant settings.
    asyncio.run(main_test_bsc())