"""
evm_callbacks.py
Handles EVM-specific callbacks (e.g., for Ethereum, BSC, Polygon).
"""
import logging
from aiogram import html, types
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from datetime import datetime
from decimal import Decimal, InvalidOperation

from extapi.etherscan.client import EtherscanAPI, EtherscanAPIError
from config.config import Config
from .common import EXPLORER_CONFIG
from .states import AddressProcessingStates # If EVM AI check sets states
# Import any other necessary modules like _orchestrate_next_processing_step if called directly
# from .address_processing import _orchestrate_next_processing_step
# from .ai_callbacks import manual_escape_markdown_v2 # If used directly here, but it's in helpers

# --- EVM AI Data Formatting Helpers ---
async def _format_evm_balance_for_ai(address: str, blockchain_name: str, api_client: EtherscanAPI) -> str:
    balance_summary = f"Section: Native Currency Balance ({blockchain_name.upper()})\n--------------------------\n"
    try:
        balance_wei = await api_client.get_ether_balance_single(address=address)
        if balance_wei is not None:
            try:
                balance_native = Decimal(balance_wei) / Decimal("1e18")
                balance_summary += f"Address: {html.quote(address)}\n"
                balance_summary += f"Balance: {balance_native:.8f} {blockchain_name.upper()} ({balance_wei} Wei)\n"
            except (ValueError, TypeError, InvalidOperation):
                balance_summary += f"Could not parse balance: {balance_wei}\n"
        else:
            balance_summary += f"Could not fetch balance data for {html.quote(address)}. The API might be temporarily unavailable or the address is invalid.\n"
    except EtherscanAPIError as e:
        balance_summary += f"API Error fetching balance: {html.quote(str(e.etherscan_message or e))}\n"
    except Exception as e:
        logging.error(f"Error formatting EVM balance for AI ({address} on {blockchain_name}): {e}", exc_info=True)
        balance_summary += f"Unexpected error fetching balance: {html.quote(str(e))}\n"
    balance_summary += "--------------------------\n\n"
    return balance_summary

async def _format_evm_normal_transactions_for_ai(address: str, blockchain_name: str, api_client: EtherscanAPI, max_tx: int = 5) -> str:
    tx_summary = f"Section: Recent Normal Transactions (Max {max_tx} shown, newest first)\n--------------------------\n"
    try:
        transactions = await api_client.get_normal_transactions(
            address=address, page=1, offset=max_tx, sort="desc"
        )
        if transactions:
            for tx in transactions:
                tx_timestamp = int(tx.get("timeStamp", "0"))
                tx_date = datetime.utcfromtimestamp(tx_timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')
                value_native = Decimal(tx.get("value", "0")) / Decimal("1e18")
                direction = "OUT" if tx.get("from", "").lower() == address.lower() else "IN"
                tx_summary += (
                    f"Date: {tx_date}, Hash: {tx.get('hash')}\n"
                    f"  Direction: {direction}, From: {tx.get('from')}, To: {tx.get('to')}\n"
                    f"  Value: {value_native:.8f} {blockchain_name.upper()}\n"
                    f"  GasUsed: {tx.get('gasUsed')}, GasPrice: {tx.get('gasPrice')} Wei\n"
                    f"  Status: {'Success' if tx.get('txreceipt_status') == '1' else 'Failed' if tx.get('txreceipt_status') == '0' else 'N/A (check isError)'}\n"
                    f"  IsError: {tx.get('isError', 'N/A')} (0=No Error, 1=Error)\n"
                    "  ---\n"
                )
        elif transactions == []:
            tx_summary += "No normal transactions found.\n"
        else:
            tx_summary += "Could not fetch normal transaction data. The API might be temporarily unavailable or the address is invalid.\n"
    except EtherscanAPIError as e:
        tx_summary += f"API Error fetching normal transactions: {html.quote(str(e.etherscan_message or e))}\n"
    except Exception as e:
        logging.error(f"Error formatting EVM normal transactions for AI ({address} on {blockchain_name}): {e}", exc_info=True)
        tx_summary += f"Unexpected error fetching normal transactions: {html.quote(str(e))}\n"
    tx_summary += "--------------------------\n\n"
    return tx_summary

async def _format_evm_erc20_transfers_for_ai(address: str, blockchain_name: str, api_client: EtherscanAPI, max_tx: int = 10) -> str:
    erc20_summary = f"Section: Recent ERC20 Token Transfers (Max {max_tx} shown, newest first)\n--------------------------\n"
    try:
        transfers = await api_client.get_erc20_token_transfers(
            address=address, page=1, offset=max_tx, sort="desc"
        )
        if transfers:
            for tx in transfers:
                tx_timestamp = int(tx.get("timeStamp", "0"))
                tx_date = datetime.utcfromtimestamp(tx_timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')
                token_symbol = tx.get("tokenSymbol", "N/A")
                token_name = tx.get("tokenName", "Unknown Token")
                try:
                    decimals = int(tx.get("tokenDecimal", "18"))
                    value_token = Decimal(tx.get("value", "0")) / (Decimal("10") ** decimals)
                except (ValueError, TypeError, InvalidOperation):
                    value_token = "N/A"
                direction = "OUT" if tx.get("from", "").lower() == address.lower() else "IN"
                erc20_summary += (
                    f"Date: {tx_date}, Hash: {tx.get('hash')}\n"
                    f"  Token: {token_name} ({token_symbol}), Contract: {tx.get('contractAddress')}\n"
                    f"  Direction: {direction}, From: {tx.get('from')}, To: {tx.get('to')}\n"
                    f"  Amount: {value_token} {token_symbol}\n"
                    "  ---\n"
                )
        elif transfers == []:
            erc20_summary += "No ERC20 token transfers found.\n"
        else:
            erc20_summary += "Could not fetch ERC20 transfer data. The API might be temporarily unavailable or the address is invalid.\n"
    except EtherscanAPIError as e:
        erc20_summary += f"API Error fetching ERC20 transfers: {html.quote(str(e.etherscan_message or e))}\n"
    except Exception as e:
        logging.error(f"Error formatting EVM ERC20 transfers for AI ({address} on {blockchain_name}): {e}", exc_info=True)
        erc20_summary += f"Unexpected error fetching ERC20 transfers: {html.quote(str(e))}\n"
    erc20_summary += "--------------------------\n\n"
    return erc20_summary

async def handle_show_token_transfers_evm_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Token Transfers' button click for EVM chains."""
    await callback_query.answer("Fetching token transfers...")
    try:
        data = await state.get_data()
        address = data.get("current_action_address")
        blockchain = data.get("current_action_blockchain")

        if not address or not blockchain:
            logging.error("Could not get address/blockchain from state for token transfers.")
            await callback_query.message.answer("Error: Missing context for token transfers. Please try again.")
            return

        logging.info(f"User {callback_query.from_user.id} requested token transfers for {address} on {blockchain}.")

        chain_config = EXPLORER_CONFIG.get(blockchain.lower())
        if not chain_config:
            logging.error(f"No EXPLORER_CONFIG found for blockchain: {blockchain}")
            await callback_query.message.answer(f"Configuration error: Explorer details for {blockchain.capitalize()} not found.")
            return

        api_base_url = chain_config.get("api_base_url")
        api_key_name_in_config = chain_config.get("api_key_name_in_config") 
        api_key = getattr(Config, api_key_name_in_config, None) if api_key_name_in_config else None
        
        if not api_base_url:
            logging.error(f"API base URL not configured for {blockchain} in EXPLORER_CONFIG.")
            await callback_query.message.answer(f"Configuration error: API URL for {blockchain.capitalize()} not set.")
            return
        
        chain_id_for_client = chain_config.get("chain_id")
        api_client = EtherscanAPI(api_key=api_key, base_url=api_base_url, chain_id=str(chain_id_for_client) if chain_id_for_client is not None else None)
        
        report_content = f"ERC20 Token Transfer Report for Address: {address}\n"
        report_content += f"Blockchain: {blockchain.capitalize()}\n" # Added blockchain to report
        report_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        
        fetch_limit = 50 

        try:
            await callback_query.message.answer(f"Querying {chain_config.get('name', 'Explorer')} for ERC20 transfers of <code>{address}</code> (limit {fetch_limit})...", parse_mode="HTML")
            
            transactions = await api_client.get_erc20_token_transfers(
                address=address,
                page=1,
                offset=fetch_limit,
                sort="desc"
            )

            transactions_found_in_batch = False
            if transactions is not None:
                transactions_found_in_batch = bool(transactions)
                report_content += f"Found {len(transactions)} ERC20 token transfers in this batch.\n"
                if len(transactions) == fetch_limit:
                    report_content += f"Note: Displaying up to {fetch_limit} transactions. More may exist if the limit was reached.\n"
                report_content += "--------------------------------------------------\n"

                for tx in transactions:
                    tx_timestamp = int(tx.get("timeStamp", "0"))
                    tx_date = datetime.utcfromtimestamp(tx_timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')
                    token_symbol = tx.get("tokenSymbol", "N/A")
                    token_name = tx.get("tokenName", "Unknown Token")
                    from_addr = tx.get("from", "N/A")
                    to_addr = tx.get("to", "N/A")
                    
                    try:
                        value = int(tx.get("value", "0"))
                        decimals = int(tx.get("tokenDecimal", "18"))
                        amount = Decimal(value) / (Decimal("10") ** decimals)
                        amount_str = f"{amount:.8f}".rstrip('0').rstrip('.')
                    except (ValueError, TypeError, InvalidOperation):
                        amount_str = "N/A (error parsing amount)"

                    direction = "OUT" if from_addr.lower() == address.lower() else "IN"
                    
                    report_content += (
                        f"Date: {tx_date}\n"
                        f"Direction: {direction}\n"
                        f"From: {from_addr}\n"
                        f"To: {to_addr}\n"
                        f"Token: {token_name} ({token_symbol})\n"
                        f"Amount: {amount_str} {token_symbol}\n"
                        f"Hash: {tx.get('hash', 'N/A')}\n"
                        f"Contract: {tx.get('contractAddress', 'N/A')}\n"
                        f"----------------------------\n"
                    )
            
            if not transactions_found_in_batch:
                report_content += "No ERC20 token transfers found for this address in the fetched batch.\n"

            file_name = f"{address}_{blockchain}_token_transfers.txt"
            report_file = BufferedInputFile(report_content.encode('utf-8'), filename=file_name)
            await callback_query.message.answer_document(report_file)
            await callback_query.message.answer(f"Token transfer report for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())} sent as a file.", parse_mode="HTML")

        except EtherscanAPIError as e_api:
            logging.error(f"Etherscan API error in handle_show_token_transfers_evm_callback for {address} on {blockchain}: {e_api}", exc_info=True)
            await callback_query.message.answer(f"Sorry, an API error occurred while generating the report for {address}: {html.quote(str(e_api.etherscan_message or e_api))}")
        except Exception as e_inner: # Renamed to avoid conflict with outer 'e'
            logging.error(f"Error generating Etherscan report for {address}: {e_inner}", exc_info=True)
            await callback_query.message.answer(f"Sorry, an unexpected error occurred while generating the report for {address}.")
    finally:
        if 'api_client' in locals() and api_client:
            await api_client.close_session()

async def handle_ai_scam_check_evm_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'AI Scam Check (EVM)' button click. Gathers EVM data and prompts for language."""
    await callback_query.answer("Initiating EVM AI Scam Check...")
    user_fsm_data = await state.get_data()
    address = user_fsm_data.get("current_action_address")
    blockchain = user_fsm_data.get("current_action_blockchain")

    if not address or not blockchain:
        logging.error("Could not get address/blockchain from state for EVM AI scam check.")
        await callback_query.message.answer("Error: Missing context for EVM AI scam check. Please try again.")
        return
    
    logging.info(f"User {callback_query.from_user.id} requested EVM AI Scam Check for {address} on {blockchain}.")

    try:
        await callback_query.message.edit_text(
            text=f"🤖 Gathering data for EVM AI Scam Check on <code>{html.quote(address)}</code> ({html.quote(blockchain.capitalize())})... Please wait.",
            parse_mode="HTML",
            reply_markup=None
        )
    except TelegramAPIError as e:
        logging.warning(f"Failed to edit message for AI EVM check data gathering: {e}")

    chain_config = EXPLORER_CONFIG.get(blockchain.lower())
    if not chain_config:
        logging.error(f"No EXPLORER_CONFIG found for blockchain: {blockchain}")
        await callback_query.message.answer(f"Configuration error: Explorer details for {blockchain.capitalize()} not found.")
        return

    api_base_url = chain_config.get("api_base_url")
    api_key_name_in_config = chain_config.get("api_key_name_in_config")
    api_key = getattr(Config, api_key_name_in_config, None) if api_key_name_in_config else None
    chain_id_for_client = chain_config.get("chain_id") 

    if not api_base_url:
        logging.error(f"API base URL not configured for {blockchain} in EXPLORER_CONFIG.")
        await callback_query.message.answer(f"Configuration error: API URL for {blockchain.capitalize()} not set.")
        return

    evm_api_client = EtherscanAPI(api_key=api_key, base_url=api_base_url, chain_id=str(chain_id_for_client) if chain_id_for_client is not None else None)
    
    enriched_data_for_ai = f"Comprehensive AI Scam Analysis Request for EVM Address: {html.quote(address)} on Blockchain: {html.quote(blockchain.capitalize())}\n"
    enriched_data_for_ai += f"Report requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"

    try:
        enriched_data_for_ai += await _format_evm_balance_for_ai(address, blockchain, evm_api_client)
        enriched_data_for_ai += await _format_evm_normal_transactions_for_ai(address, blockchain, evm_api_client, max_tx=5)
        enriched_data_for_ai += await _format_evm_erc20_transfers_for_ai(address, blockchain, evm_api_client, max_tx=10)
    except Exception as e:
        logging.error(f"Error during EVM data aggregation for AI ({address} on {blockchain}): {e}", exc_info=True)
        enriched_data_for_ai += f"\nAn error occurred during data aggregation: {html.quote(str(e))}\n"
    finally:
        await evm_api_client.close_session()

    update_payload = {"ai_enriched_data": enriched_data_for_ai}
    if "current_scan_db_message_id" in user_fsm_data:
         update_payload["current_scan_db_message_id"] = user_fsm_data.get("current_scan_db_message_id")

    await state.update_data(**update_payload)

    # This part will be handled by ai_callbacks.py after this function sets the state
    # For now, we assume the state transition to awaiting_ai_language_choice is correct
    # and the ai_callbacks.py will pick up from there.
    # The actual language prompt should be in ai_callbacks.py or a shared function.
    # For simplicity in this refactor, we'll assume this function now just prepares data
    # and the next step (language prompt) is triggered by the state change.
    # However, the original code directly sends the language prompt here.
    # To keep it functional for now, we'll include the prompt here, but ideally, it's centralized.

    language_buttons = [
        [
            types.InlineKeyboardButton(text="🇬🇧 English", callback_data="ai_lang:en"),
            types.InlineKeyboardButton(text="🇷🇺 Русский", callback_data="ai_lang:ru"),
        ]
    ]
    reply_markup_lang = types.InlineKeyboardMarkup(inline_keyboard=language_buttons)
    
    await callback_query.message.answer( 
        text=(
            f"Data gathering for EVM AI Scam Check on <code>{html.quote(address)}</code> complete.\n"
            "📊 Please choose the report language:"
        ),
        parse_mode="HTML",
        reply_markup=reply_markup_lang
    )
    await state.set_state(AddressProcessingStates.awaiting_ai_language_choice)

# Register these handlers with your dispatcher, e.g., in __init__.py or main bot file:
# from .evm_callbacks import handle_show_token_transfers_evm_callback, handle_ai_scam_check_evm_callback
# dp.callback_query.register(handle_show_token_transfers_evm_callback, F.data == "show_token_transfers_evm")
# dp.callback_query.register(handle_ai_scam_check_evm_callback, F.data == "ai_scam_check_evm")
