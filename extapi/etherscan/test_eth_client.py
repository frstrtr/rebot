# filepath: /home/user0/rebot/extapi/etherscan/test_eth_client.py
"""
test_eth_client.py
Example usage and test functions for EtherscanAPI client.
"""
import asyncio
import logging
from decimal import Decimal

# Assuming this test script is run in an environment where 'config'
# and 'extapi' are accessible.
from config.config import Config
from .client import EtherscanAPI, EtherscanAPIError, EtherscanRateLimitError

# Configure logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')


async def main_test():
    """
    Main function to test EtherscanAPI client methods.
    """
    # Initialize EtherscanAPI client
    # The API key is handled by Config.ETHERSCAN_API_KEY by default
    api_client = EtherscanAPI()

    if not api_client.api_key:
        logging.warning("ETHERSCAN_API_KEY not found in config. Some endpoints might be rate-limited or require it.")

    vitalik_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    usdt_contract_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    example_tx_hash = "0xeed634e842747f5b2c229b6ad329ac03ae81f1b181a062dfb38d9449c27f96ca" # Example Tx
    example_block = 18000000


    print(f"\n\033[93m--- Testing get_ether_balance_single for {vitalik_address} ---\033[0m")
    try:
        balance_wei = await api_client.get_ether_balance_single(vitalik_address)
        if balance_wei is not None:
            balance_eth = Decimal(balance_wei) / Decimal("1e18")
            print(f"Balance for {vitalik_address}: {balance_eth:.6f} ETH ({balance_wei} Wei)")
        else:
            print(f"Failed to get balance for {vitalik_address} or address not found.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_ether_balance_single: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_ether_balance_single: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_ether_balance_multiple for {vitalik_address} & {usdt_contract_address} ---\033[0m")
    try:
        balances = await api_client.get_ether_balance_multiple([vitalik_address, usdt_contract_address])
        if balances:
            for acc_balance in balances:
                balance_eth = Decimal(acc_balance.get('balance', '0')) / Decimal("1e18")
                print(f"  Account: {acc_balance.get('account')}, Balance: {balance_eth:.6f} ETH")
        else:
            print("Failed to get multiple balances.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_ether_balance_multiple: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_ether_balance_multiple: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


    print(f"\n\033[93m--- Testing get_normal_transactions for {vitalik_address} (last 2) ---\033[0m")
    try:
        transactions = await api_client.get_normal_transactions(vitalik_address, page=1, offset=2, sort="desc")
        if transactions:
            print(f"Found {len(transactions)} normal transactions (showing last 2):")
            for tx in transactions:
                value_eth = Decimal(tx.get('value', '0')) / Decimal("1e18")
                print(f"  TxHash: {tx.get('hash')[:15]}..., From: {tx.get('from')[:10]}..., To: {tx.get('to')[:10]}..., Value: {value_eth:.4f} ETH, Time: {tx.get('timeStamp')}")
        else:
            print("No normal transactions found or failed to fetch.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_normal_transactions: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_normal_transactions: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_erc20_token_transfers for {vitalik_address} with USDT (last 2) ---\033[0m")
    try:
        erc20_transfers = await api_client.get_erc20_token_transfers(
            address=vitalik_address,
            contract_address=usdt_contract_address,
            page=1, offset=2, sort="desc"
        )
        if erc20_transfers:
            print(f"Found {len(erc20_transfers)} ERC20 USDT transfers (showing last 2):")
            for tx in erc20_transfers:
                # ERC20 value needs to be divided by tokenDecimals
                token_decimals = int(tx.get('tokenDecimal', '18')) # Default to 18 if not present
                value_token = Decimal(tx.get('value', '0')) / (Decimal('10') ** token_decimals)
                print(f"  TxHash: {tx.get('hash')[:15]}..., From: {tx.get('from')[:10]}..., To: {tx.get('to')[:10]}..., Value: {value_token} {tx.get('tokenSymbol')}")
        else:
            print("No ERC20 USDT transfers found or failed to fetch.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_erc20_token_transfers: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_erc20_token_transfers: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_contract_abi for USDT ({usdt_contract_address}) ---\033[0m")
    try:
        abi = await api_client.get_contract_abi(usdt_contract_address)
        if abi:
            print(f"ABI for {usdt_contract_address} (first 100 chars): {abi[:100]}...")
            # ABI is a JSON string, you can load it with json.loads(abi)
        else:
            print(f"Failed to get ABI for {usdt_contract_address}.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_contract_abi: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_contract_abi: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing get_total_eth_supply ---\033[0m")
    try:
        supply_wei = await api_client.get_total_eth_supply()
        if supply_wei:
            supply_eth = Decimal(supply_wei) / Decimal("1e18")
            print(f"Total ETH Supply: {supply_eth:,.2f} ETH ({supply_wei} Wei)")
        else:
            print("Failed to get total ETH supply.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_total_eth_supply: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_total_eth_supply: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print("\n\033[93m--- Testing get_eth_last_price ---\033[0m")
    try:
        price_info = await api_client.get_eth_last_price()
        if price_info:
            print(f"ETH Last Price: ETH/BTC = {price_info.get('ethbtc')}, ETH/USD = {price_info.get('ethusd')}")
            print(f"  Timestamp: ETH/BTC = {price_info.get('ethbtc_timestamp')}, ETH/USD = {price_info.get('ethusd_timestamp')}")
        else:
            print("Failed to get ETH last price.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for get_eth_last_price: {e}")
    except EtherscanAPIError as e:
        print(f"API error for get_eth_last_price: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing eth_get_block_by_number for block {example_block} ---\033[0m")
    try:
        block_data = await api_client.eth_get_block_by_number(example_block, is_full=False)
        if block_data:
            print(f"Block {example_block} Data (partial): Hash: {block_data.get('hash')}, Miner: {block_data.get('miner')}, Tx count: {len(block_data.get('transactions', []))}")
        else:
            print(f"Failed to get block {example_block} data.")
    except EtherscanRateLimitError as e:
        print(f"Rate limit error for eth_get_block_by_number: {e}")
    except EtherscanAPIError as e:
        print(f"API error for eth_get_block_by_number: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print(f"\n\033[93m--- Testing eth_get_transaction_by_hash for {example_tx_hash[:20]}... ---\033[0m")
    try:
        tx_data = await api_client.eth_get_transaction_by_hash(example_tx_hash)
        if tx_data:
            print(f"Transaction {example_tx_hash[:20]}... Data (partial): From: {tx_data.get('from')}, To: {tx_data.get('to')}, Value: {tx_data.get('value')}")
        else:
            print(f"Failed to get transaction {example_tx_hash[:20]}... data.")
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
    # Then run: python -m extapi.etherscan.test_eth_client
    # Make sure config/config.py has ETHERSCAN_API_KEY and ETHERSCAN_API_BASE_URL set.
    asyncio.run(main_test())