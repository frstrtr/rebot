"""
test_tron_client.py
Example usage and test functions for TronScanAPI client.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any 

# Assuming this test script is run in an environment where 'config' 
# and 'extapi' are accessible.
# If running from /home/user0/rebot/ with `python -m extapi.tronscan.test_tron_client`
# this import should work.
from config.config import Config 
from .client import TronScanAPI, TronScanRateLimitError


async def main_test():
    """
    Main function to test TronScanAPI client methods.
    """
    # This test assumes it's run from the 'rebot' directory,
    # or that 'rebot' is in PYTHONPATH for 'from config.config import Config' to work.
    # Initialize TronScanAPI client
    # The API key is now handled by Config.TRONSCAN_API_KEY by default in the constructor
    api_client = TronScanAPI()

    if not api_client.api_key:
        print("TRONSCAN_API_KEY not found in config. Please set it up. Some endpoints might require it or be rate-limited.")
        # return # Optionally exit if no API key for testing, though some endpoints might work without it

    test_user_address = "TRnoPh9n4ea1QKbaTK9u3ocoQgFhNPSzRk" # Example: Scammer address
    # test_user_address = "TLa2f6VPqDgRE67v1736s7gWVaG1Dbte4c" # Example: TRON Foundation
    usdt_trc20_contract_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" # Tether (USDT) on TRON

    print(f"\n\033[93m--- Testing get_account_info for {test_user_address} ---\033[0m")
    try:
        account_info = await api_client.get_account_info(test_user_address)
        if account_info:
            print("Account Info Received:")
            print(f"  Address: {account_info.get('address')}")
            trx_balance_sun = account_info.get('balance', 0)
            trx_balance = trx_balance_sun / 1_000_000  # Convert SUN to TRX
            print(f"  TRX Balance: {trx_balance} TRX ({trx_balance_sun} SUN)")
            print(f"  Account Name: {account_info.get('account_name')}") 
            print(f"  Total transaction count: {account_info.get('total_transaction_count')}")
        else:
            print(f"Failed to get account info for {test_user_address} or address not found.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_info: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_info: {e}")


    print(f"\n\033[93m--- Testing get_account_trc20_balances for {test_user_address} ---\033[0m")
    try:
        trc20_balances = await api_client.get_account_trc20_balances(test_user_address, limit=5)
        if trc20_balances and trc20_balances.get('trc20token_balances'): 
            print("TRC20 Balances Received (first 5):")
            for token in trc20_balances['trc20token_balances'][:5]:
                print(f"  Token: {token.get('tokenName')} ({token.get('tokenAbbr')}), Balance: {token.get('balanceWithTask')}, Decimals: {token.get('tokenDecimal')}")
        elif trc20_balances:
             print(f"TRC20 Balances response (structure might vary): {trc20_balances}")
        else:
            print("Failed to get TRC20 balances.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_trc20_balances: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_trc20_balances: {e}")


    print(f"\n\033[93m--- Testing get_trc20_transaction_history for {test_user_address} (all tokens, last 5) ---\033[0m")
    try:
        history_all = await api_client.get_trc20_transaction_history(test_user_address, limit=5)
        if history_all and history_all.get("token_transfers"):
            print("TRC20 Transaction History (All Tokens, first 5):")
            for tx in history_all["token_transfers"][:5]:
                raw_timestamp_ms = tx.get('block_ts')
                human_readable_timestamp = "N/A"
                if raw_timestamp_ms is not None:
                    try:
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        datetime_object = datetime.fromtimestamp(timestamp_seconds)
                        human_readable_timestamp = datetime_object.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError) as e_ts:
                        logging.debug(f"Could not parse timestamp {raw_timestamp_ms}: {e_ts}")
                        human_readable_timestamp = "Invalid timestamp"
                
                print(
                    f"  Timestamp: {human_readable_timestamp} ({raw_timestamp_ms}), "
                    f"From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
                    f"Token: {tx.get('tokenInfo', {}).get('tokenAbbr', 'N/A')}, Amount: {tx.get('quant')}, Confirmed: {tx.get('confirmed')}"
                )
        elif history_all:
            print(f"TRC20 History (All) response (structure might vary): {history_all}")
        else:
            print("Failed to get TRC20 transaction history (all tokens).")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_trc20_transaction_history (all): {e}")
    except Exception as e:
        print(f"An error occurred during get_trc20_transaction_history (all): {e}")

    print(f"\n\033[93m--- Testing get_trc20_transaction_history for {test_user_address} (USDT only, last 3) ---\033[0m")
    try:
        history_usdt = await api_client.get_trc20_transaction_history(
            test_user_address, contract_address=usdt_trc20_contract_address, limit=3
        )
        if history_usdt and history_usdt.get("token_transfers"):
            print("TRC20 Transaction History (USDT, first 3):")
            for tx in history_usdt["token_transfers"][:3]:
                raw_timestamp_ms = tx.get('block_ts')
                human_readable_timestamp = "N/A"
                if raw_timestamp_ms is not None:
                    try:
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        datetime_object = datetime.fromtimestamp(timestamp_seconds)
                        human_readable_timestamp = datetime_object.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError) as e_ts:
                        logging.debug(f"Could not parse timestamp {raw_timestamp_ms}: {e_ts}")
                        human_readable_timestamp = "Invalid timestamp"

                print(
                    f"  TxID: {tx.get('transaction_id')[:10]}..., From: {tx.get('from_address')}, To: {tx.get('to_address')}, "
                    f"Token: {tx.get('tokenInfo', {}).get('tokenAbbr', 'N/A')}, Amount: {tx.get('quant')}, Confirmed: {tx.get('confirmed')}, "
                    f"Timestamp: {human_readable_timestamp}"
                )
        elif history_usdt:
            print(f"TRC20 History (USDT) response (structure might vary): {history_usdt}")
        else:
            print("Failed to get TRC20 transaction history (USDT).")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_trc20_transaction_history (USDT): {e}")
    except Exception as e:
        print(f"An error occurred during get_trc20_transaction_history (USDT): {e}")


    print(f"\n\033[93m--- Testing get_account_related_accounts for {test_user_address} ---\033[0m")
    try:
        related_accounts = await api_client.get_account_related_accounts(test_user_address)
        if related_accounts:
            print(f"Related Accounts ({len(related_accounts.get('data', []))}) data received (first few entries if list):")
            if isinstance(related_accounts.get('data'), list): 
                for acc_data in related_accounts['data'][:3]:
                    print(f"  Related Address: {acc_data.get('related_address')}, Tag: {acc_data.get('addressTag')}, In: {acc_data.get('inAmountUsd')}, Out: {acc_data.get('outAmountUsd')}")
            else: 
                print(related_accounts)
        else:
            print(f"Failed to get related accounts for {test_user_address}.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_related_accounts: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_related_accounts: {e}")


    print(f"\n\033[93m--- Testing get_account_tags for {test_user_address} ---\033[0m")
    try:
        account_tags = await api_client.get_account_tags(test_user_address)
        if account_tags:
            # The actual structure of account_tags can vary.
            # Example 1: {"address":"TR...","tags":[{"tag":"Whale","tag_id":1}]}
            # Example 2: {"address":"...","tag":"Exchange","tag_url":""} (if only one tag)
            # Example 3: {"address":"...","tags":[]} (if no tags)
            # Example from docs: {"TR...":{"tag":"Whale","tag_url":""}}
            print(f"Account Tags received for {test_user_address}:")
            if isinstance(account_tags.get('tags'), list): # Check for a list of tags
                 if account_tags['tags']:
                    for tag_info in account_tags['tags']:
                        print(f"  Tag: {tag_info.get('tag')}, Tag ID: {tag_info.get('tag_id')}")
                 else:
                    print("  No tags found in 'tags' list.")
            elif 'tag' in account_tags: # Check if the root object itself is a single tag
                print(f"  Tag: {account_tags.get('tag')}, URL: {account_tags.get('tag_url')}")
            # Check for the structure {"ADDRESS": {"tag": "...", "tag_url":"..."}}
            elif test_user_address in account_tags and isinstance(account_tags[test_user_address], dict):
                tag_data = account_tags[test_user_address]
                print(f"  Tag: {tag_data.get('tag')}, URL: {tag_data.get('tag_url')}")
            else: # Fallback for other structures or empty responses
                print(f"  Raw tags response: {account_tags}")
        else:
            print(f"Failed to get account tags for {test_user_address} or no tags found.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_tags: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_tags: {e}")


    print("\n\033[93m--- Testing get_stablecoin_blacklist (first 5) ---\033[0m")
    try:
        blacklist = await api_client.get_stablecoin_blacklist(limit=5)
        if blacklist and blacklist.get('data'): 
            print(f"Stablecoin Blacklist (Total: {blacklist.get('total')}, showing first {len(blacklist['data'])} of {blacklist.get('total')}):")
            for item in blacklist['data'][:5]: 
                print(f"  Address: {item.get('blackAddress')}, Token: {item.get('tokenName')}, Tx Hash: {item.get('transHash')}, Time: {datetime.fromtimestamp(item.get('time', 0)/1000) if item.get('time') else 'N/A'}")
        elif blacklist:
            print(f"Stablecoin Blacklist response (structure might vary): {blacklist}")
        else:
            print("Failed to get stablecoin blacklist.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_stablecoin_blacklist: {e}")
    except Exception as e:
        print(f"An error occurred during get_stablecoin_blacklist: {e}")


    print(f"\n\033[93m--- Testing get_account_transfer_amounts for {test_user_address} ---\033[0m")
    try:
        transfer_amounts = await api_client.get_account_transfer_amounts(test_user_address)
        if transfer_amounts:
            print(f"Account Transfer Amounts for {test_user_address}:")
            if 'transfer_out' in transfer_amounts or 'transfer_in' in transfer_amounts:
                if transfer_amounts.get('transfer_out'):
                    out_data = transfer_amounts['transfer_out']
                    print(f"  Transfer Out (Total Records: {out_data.get('total')}, Amount Total USD: {out_data.get('amountTotal')}) (first 2 entries):")
                    if isinstance(out_data.get('data'), list):
                        for item in out_data['data'][:2]:
                            print(f"    - Address: {item.get('address')}, Amount USD: {item.get('amountInUsd')}, Tag: {item.get('addressTag')}")
                            if isinstance(out_data.get('contractInfo'), dict) and item.get('address') in out_data['contractInfo']:
                                print(f"      Contract Info: {out_data['contractInfo'][item.get('address')]}")
                
                if transfer_amounts.get('transfer_in'):
                    in_data = transfer_amounts['transfer_in']
                    print(f"  Transfer In (Total Records: {in_data.get('total')}, Amount Total USD: {in_data.get('amountTotal')}) (first 2 entries):")
                    if isinstance(in_data.get('data'), list):
                        for item in in_data['data'][:2]:
                            print(f"    - Address: {item.get('address')}, Amount USD: {item.get('amountInUsd')}, Tag: {item.get('addressTag')}")
                            if isinstance(in_data.get('contractInfo'), dict) and item.get('address') in in_data['contractInfo']:
                                print(f"      Contract Info: {in_data['contractInfo'][item.get('address')]}")
            elif 'stableAmountLine' in transfer_amounts or 'stableAmount24h' in transfer_amounts:
                # ... (code for stableAmountLine/stableAmount24h as previously defined)
                print("  (Fallback to stableAmountLine/stableAmount24h structure if present)")
            elif transfer_amounts.get('receiveList') or transfer_amounts.get('sendList'):
                # ... (code for receiveList/sendList as previously defined)
                print("  (Fallback to receiveList/sendList structure if present)")
            else:
                print("  Data structure not recognized by specific formatting, printing raw (up to 400 chars):")
                raw_str = str(transfer_amounts)
                print(f"    {raw_str[:400]}{'...' if len(raw_str) > 400 else ''}")
        else:
            print(f"Failed to get account transfer amounts for {test_user_address}.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_transfer_amounts: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_transfer_amounts: {e}")


    print(f"\n\033[93m--- Testing get_account_token_big_amounts for {test_user_address} (USDT, limit 3) ---\033[0m")
    try:
        big_amounts_usdt = await api_client.get_account_token_big_amounts(test_user_address, contract_address=usdt_trc20_contract_address, limit=3)
        if big_amounts_usdt and big_amounts_usdt.get('data'):
            print(f"Big USDT Token Amounts (Total: {big_amounts_usdt.get('total', len(big_amounts_usdt['data']))}, showing first {len(big_amounts_usdt['data'][:3])}):")
            for tx_info in big_amounts_usdt['data'][:3]:
                print(f"  TxID: {tx_info.get('transaction_id')}, Amount: {tx_info.get('amount')}, To: {tx_info.get('to_address')}, From: {tx_info.get('from_address')}, Token: {tx_info.get('tokenInfo',{}).get('tokenAbbr')}")
        elif big_amounts_usdt:
            print(f"Big USDT Token Amounts response (structure might vary): {big_amounts_usdt}")
        else:
            print(f"Failed to get big USDT token amounts for {test_user_address}.")
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_account_token_big_amounts: {e}")
    except Exception as e:
        print(f"An error occurred during get_account_token_big_amounts: {e}")


    print(f"\n\033[93m--- Testing get_stablecoin_key_events (first 5, USDT AddedBlackList, sort by time desc) ---\033[0m")
    try:
        key_events = await api_client.get_stablecoin_key_events(limit=5, usdt_events="AddedBlackList", sort_by=2, direction=2)
        if key_events and key_events.get('data'):
            event_list = key_events['data']
            print(f"Stablecoin Key Events (Total in response: {key_events.get('total', len(event_list))}, showing first {len(event_list[:5])}):")
            for event in event_list[:5]:
                event_time = "N/A"
                if event.get('block_ts'):
                    try:
                        event_time = datetime.fromtimestamp(event.get('block_ts') / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    except: # pylint: disable=bare-except
                        pass # Keep N/A
                print(
                    f"  Event Name: {event.get('eventName')}, Token: {event.get('tokenSymbol')}, "
                    f"Tx Hash: {event.get('transaction_id')}, "
                    f"Time: {event_time} ({event.get('block_ts')}), "
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
    except TronScanRateLimitError as e:
        print(f"Rate limit error for get_stablecoin_key_events: {e}")
    except Exception as e:
        print(f"An error occurred during get_stablecoin_key_events: {e}")

    await api_client.close_session()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # To run this test directly:
    # Ensure you are in the /home/user0/rebot/ directory
    # Then run: python -m extapi.tronscan.test_tron_client
    # Make sure config/config.py has TRONSCAN_API_KEY set if required by endpoints.
    asyncio.run(main_test())