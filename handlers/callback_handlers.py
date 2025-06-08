"""callback_handlers.py
Handles callbacks from inline buttons related to blockchain clarifications.
"""

import logging
from aiogram import html, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from datetime import datetime # Ensure datetime is imported
import io # For sending text as a file

from database import SessionLocal, get_or_create_user, save_crypto_address # Add get_or_create_user, MemoType
from database.models import MemoType
from database.queries import update_crypto_address_memo # For saving memos
from extapi.tronscan.client import TronScanAPI
from genai import VertexAIClient # Import VertexAIClient
from .address_processing import (
    _display_memos_for_address_blockchain,
    _orchestrate_next_processing_step,
    _prompt_for_next_memo,
    _send_action_prompt,  # Import the new helper
)
from .common import EXPLORER_CONFIG, TARGET_AUDIT_CHANNEL_ID # Added TARGET_AUDIT_CHANNEL_ID
from .states import AddressProcessingStates  # Ensure this is imported if not already
from .helpers import format_user_info_for_audit, send_text_to_audit_channel # ADDED/MODIFIED


async def handle_blockchain_clarification_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles blockchain clarification button presses."""
    await callback_query.answer()
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )

    if not item_being_clarified:
        logging.warning(
            "Blockchain clarification callback received but no item_being_clarified in state."
        )
        await callback_query.message.answer(
            "Error: Could not determine which address to clarify. Please try scanning again."
        )
        await state.clear()
        return

    action = callback_query.data.split(":")[1]
    address_str = item_being_clarified["address"]
    db = SessionLocal() # Create a new session

    try:
        if action == "chosen":
            chosen_blockchain = callback_query.data.split(":")[2]
            logging.info(
                "User chose blockchain '%s' for address '%s'",
                chosen_blockchain,
                address_str,
            )

            # Update FSM: this address is now the one to be actioned upon.
            # The structure for addresses_for_memo_prompt_details should be a list of dicts.
            # We are setting it directly for the current clarified address.
            addresses_for_memo_prompt_details_fsm = [
                {"address": address_str, "blockchain": chosen_blockchain}
            ]
            await state.update_data(
                addresses_for_memo_prompt_details=addresses_for_memo_prompt_details_fsm,
                current_item_for_blockchain_clarification=None,  # Clear the item being clarified
                pending_blockchain_clarification=data.get("pending_blockchain_clarification", []), # Preserve pending
                current_action_address=address_str,  # <--- ADD THIS
                current_action_blockchain=chosen_blockchain  # <--- ADD THIS
            )
            
            # Edit the clarification message to show the choice and then send the action prompt.
            await callback_query.message.edit_text(
                f"✅ Blockchain for <code>{html.quote(address_str)}</code> set to <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
                parse_mode="HTML",
                reply_markup=None, # Remove inline keyboard from clarification message
            )
            # Send the action prompt for this address
            await _send_action_prompt(
                target_message=callback_query.message,
                address=address_str,
                blockchain=chosen_blockchain,
                state=state,
                db=db,
                acting_telegram_user_id=callback_query.from_user.id # Pass acting user's telegram_id
            )
            # No need to call orchestrator here, user will interact with the new action prompt.

        elif action == "skip":
            logging.info("User skipped blockchain clarification for address %s", address_str)
            await callback_query.message.edit_text(
                f"⏭️ Skipped blockchain clarification for <code>{html.quote(address_str)}</code>.",
                parse_mode="HTML",
                reply_markup=None,
            )
            await state.update_data(current_item_for_blockchain_clarification=None)
            # Orchestrate to process next if any, or finish.
            # Need to pass the original message that triggered the scan for reply context if orchestrator needs it.
            # This might require storing the original message_id or chat_id in FSM if not already.
            # For now, assuming callback_query.message can be used as a reply target.
            await _orchestrate_next_processing_step(callback_query.message, state)
        else:
            logging.warning("Unknown action in blockchain clarification: %s", action)
            await callback_query.message.answer("Invalid action. Please try again.")
    finally:
        if db.is_active:
            db.close() # Close the session

async def handle_show_previous_memos_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Show Previous Memos' button click."""
    await callback_query.answer()
    
    data = await state.get_data()
    action_details_list = data.get("addresses_for_memo_prompt_details")

    if not action_details_list or not isinstance(action_details_list, list) or not action_details_list[0]:
        logging.warning("Could not retrieve address/blockchain from state for show_prev_memos. State: %s", data) # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer("Error: Context lost. Please try scanning the address again.")
        # Optionally, clear state fully if context is truly lost for subsequent actions
        # await state.clear() 
        return

    current_action_info = action_details_list[0]
    address = current_action_info.get("address")
    blockchain = current_action_info.get("blockchain")

    if not address or not blockchain:
        logging.warning("Missing address or blockchain in state for show_prev_memos. Info: %s", current_action_info)
        await callback_query.message.answer("Error: Could not retrieve full address details. Please try again.")
        return

    db_session = SessionLocal()
    try:
        await _display_memos_for_address_blockchain(
            callback_query.message, address, blockchain, db_session
        )
    finally:
        if db_session.is_active:
            db_session.close()
    
    # After displaying memos, set the FSM state to None.
    # This ensures the bot is not stuck in a previous state like 'awaiting_blockchain'.
    # FSM data (like addresses_for_memo_prompt_details) will be preserved.
    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        logging.debug(f"Clearing FSM state from {current_fsm_state} after showing memos.")
        await state.set_state(None)
    
    # The original action prompt message (if any) remains, allowing other actions.
    # No further orchestration is typically needed here as this is a display action.

async def handle_proceed_to_memo_stage_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Add/Manage Memo' button click from the action prompt."""
    await callback_query.answer("Loading memo options...")
    
    # The FSM state 'addresses_for_memo_prompt_details' should have been set
    # before _send_action_prompt was called.
    # _orchestrate_next_processing_step will pick it up.
    try:
        # Optionally edit the message to indicate loading, or remove buttons
        await callback_query.message.edit_reply_markup(reply_markup=None)
        # Or edit text:
        # await callback_query.message.edit_text(
        #     text=f"{callback_query.message.text}\n\nProceeding to memo options...",
        #     parse_mode="HTML",
        #     reply_markup=None 
        # )
    except TelegramAPIError as e:
        logging.warning("Could not edit message reply_markup on proceed_to_memo_stage: %s", e) # pylint:disable=logging-fstring-interpolation

    await _orchestrate_next_processing_step(callback_query.message, state)

async def handle_skip_address_action_stage_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles skipping the entire address processing at the action prompt stage."""
    await callback_query.answer()
    
    try:
        _prefix, address_skipped, blockchain_skipped = callback_query.data.split(":", 2)
    except ValueError:
        address_skipped = "the address" 
        blockchain_skipped = "N/A"
        logging.warning("Invalid callback data for skip_address_action_stage: %s", callback_query.data)

    logging.info(f"User chose to skip further processing for address: {address_skipped} on {blockchain_skipped}") # pylint:disable=logging-fstring-interpolation
    
    # Clear this address from being prompted for a memo.
    await state.update_data(addresses_for_memo_prompt_details=[]) 
    
    try:
        await callback_query.message.edit_text(
            text=f"Skipped further actions for address: <code>{html.quote(address_skipped)}</code>.",
            parse_mode="HTML",
            reply_markup=None 
        )
    except TelegramAPIError as e:
        logging.warning("Could not edit message on skip_address_action_stage: %s", e)
        # Fallback if edit fails
        await callback_query.message.answer(
             f"Skipped further actions for address: <code>{html.quote(address_skipped)}</code>.",
            parse_mode="HTML"
        )

    # Call orchestrator to see if other items (e.g., other pending clarifications) exist
    # or if the initial scan had more addresses (though current logic focuses on one at a time post-scan).
    await _orchestrate_next_processing_step(callback_query.message, state)


async def handle_show_public_memos_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Show Public Memos' button click."""
    await callback_query.answer()
    data = await state.get_data()
    # Assuming 'addresses_for_memo_prompt_details' holds the current address context
    # This might need adjustment if the FSM data structure for current address changes.
    action_details_list = data.get("addresses_for_memo_prompt_details")

    if not action_details_list or not isinstance(action_details_list, list) or not action_details_list[0]:
        logging.warning("Could not retrieve address/blockchain from state for show_public_memos. State: %s", data)
        await callback_query.message.answer("Error: Context lost for showing memos. Please try scanning the address again.")
        return

    current_action_info = action_details_list[0]
    address = current_action_info.get("address")
    blockchain = current_action_info.get("blockchain")

    if not address or not blockchain:
        logging.warning("Missing address or blockchain in state for show_public_memos. Info: %s", current_action_info)
        await callback_query.message.answer("Error: Could not retrieve full address details for memos. Please try again.")
        return

    db_session = SessionLocal()
    try:
        await _display_memos_for_address_blockchain(
            message_target=callback_query.message,
            address=address,
            blockchain=blockchain,
            db=db_session,
            memo_scope="public" # Explicitly public
        )
    finally:
        if db_session.is_active:
            db_session.close()
    # No FSM state change needed here, user can still interact with the action prompt

async def handle_show_private_memos_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Show My Private Memos' button click."""
    await callback_query.answer()
    data = await state.get_data()
    action_details_list = data.get("addresses_for_memo_prompt_details")

    if not action_details_list or not isinstance(action_details_list, list) or not action_details_list[0]:
        logging.warning("Could not retrieve address/blockchain from state for show_private_memos. State: %s", data)
        await callback_query.message.answer("Error: Context lost for showing private memos. Please try scanning the address again.")
        return

    current_action_info = action_details_list[0]
    address = current_action_info.get("address")
    blockchain = current_action_info.get("blockchain")
    requesting_telegram_id = callback_query.from_user.id

    if not address or not blockchain:
        logging.warning("Missing address or blockchain in state for show_private_memos. Info: %s", current_action_info)
        await callback_query.message.answer("Error: Could not retrieve full address details for private memos. Please try again.")
        return

    db_session = SessionLocal()
    try:
        # Get internal DB user ID
        db_user = get_or_create_user(db_session, callback_query.from_user) # Use the callback_query.from_user
        if not db_user:
            await callback_query.message.answer("Error: Could not identify user for private memos.")
            return
        
        await _display_memos_for_address_blockchain(
            message_target=callback_query.message,
            address=address,
            blockchain=blockchain,
            db=db_session,
            memo_scope="private_own",
            requesting_user_db_id=db_user.id
        )
    finally:
        if db_session.is_active:
            db_session.close()
    # No FSM state change needed here

async def handle_request_memo_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles 'Add Public Memo' or 'Add Private Memo' button clicks.
    Callback data format: "request_memo:public" or "request_memo:private"
    """
    await callback_query.answer()

    try:
        _prefix, memo_type_str = callback_query.data.split(":", 1)
        if memo_type_str not in [MemoType.PUBLIC.value, MemoType.PRIVATE.value]:
            raise ValueError("Invalid memo type")
    except ValueError:
        logging.warning(f"Invalid callback data for request_memo: {callback_query.data}") # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer("Error processing memo request. Please try again.")
        return

    data = await state.get_data()
    # Ensure 'addresses_for_memo_prompt_details' is populated correctly before this stage
    # This list should contain the single address/blockchain pair we are currently focused on.
    current_address_details_list = data.get("addresses_for_memo_prompt_details")

    if not current_address_details_list or not isinstance(current_address_details_list, list) or not current_address_details_list[0]:
        logging.error("State 'addresses_for_memo_prompt_details' is not set correctly for memo request.")
        await callback_query.message.answer("Error: Critical context missing for adding memo. Please restart the process.")
        await state.clear()
        return
        
    current_address_info = current_address_details_list[0]
    address_text = current_address_info.get("address")
    blockchain_text = current_address_info.get("blockchain", "N/A").capitalize()
    
    # We need to save the crypto_address to DB first to get its ID for FSM state,
    # if it hasn't been saved yet (e.g. if user directly clicks "Add Memo" after clarification
    # without going through an explicit save step in orchestrator for this specific purpose).
    # The _orchestrate_next_processing_step usually handles saving.
    # For now, let's assume current_scan_db_message_id is in state.
    # And that the address is saved when _orchestrate_next_processing_step is called
    # by handle_proceed_to_memo_stage_callback.
    # The `_prompt_for_next_memo` function (called by orchestrator) sets:
    # current_address_for_memo_id, current_address_for_memo_text, current_address_for_memo_blockchain

    # The `proceed_to_memo_stage` callback should have called `_orchestrate_next_processing_step`,
    # which in turn calls `_prompt_for_next_memo` if `addresses_for_memo_prompt_details` is set.
    # `_prompt_for_next_memo` shows "Add Memo" / "Skip" buttons which call `handle_memo_action_callback`.
    # This new `request_memo:public/private` comes from `_send_action_prompt`.
    # So, if user clicks "Add Public/Private Memo" from `_send_action_prompt`, we need to:
    # 1. Save the address to DB to get an ID (if not already done for this specific intent).
    # 2. Store this ID, address, blockchain, and intended_memo_type in FSM.
    # 3. Set state to awaiting_memo.

    db_session = SessionLocal()
    try:
        current_scan_db_message_id = data.get("current_scan_db_message_id")
        if not current_scan_db_message_id:
            logging.error("Cannot save address for memo: current_scan_db_message_id missing from FSM.")
            await callback_query.message.answer("Error: Missing message context. Cannot proceed.")
            await state.clear()
            return

        # Save (or get existing) CryptoAddress to ensure we have an ID
        db_crypto_address = save_crypto_address(
            db_session,
            current_scan_db_message_id,
            address_text,
            current_address_info.get("blockchain")
        )
        if not db_crypto_address or not db_crypto_address.id:
            logging.error(f"Failed to save/retrieve crypto address {address_text} for memo.") # pylint:disable=logging-fstring-interpolation
            await callback_query.message.answer("Error: Could not prepare address for memo. Please try again.")
            return
        
        await state.update_data(
            current_address_for_memo_id=db_crypto_address.id,
            current_address_for_memo_text=address_text,
            current_address_for_memo_blockchain=current_address_info.get("blockchain"),
            intended_memo_type=memo_type_str,
            pending_addresses_for_memo=[] # Clear any old pending list from other flows
        )
    finally:
        if db_session.is_active:
            db_session.close()

    prompt_message_text = (
        f"Please reply with your {memo_type_str} memo for: <code>{html.quote(address_text)}</code> ({html.quote(blockchain_text)}).\n"
        "Or send /skip to cancel adding this memo."
    )
    try:
        await callback_query.message.edit_text(
            text=prompt_message_text,
            parse_mode="HTML",
            reply_markup=None,  # Remove buttons
        )
    except Exception as e:
        logging.warning(f"Failed to edit message for memo prompt, sending new: {e}") # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer(
            text=prompt_message_text,
            parse_mode="HTML",
        )
    await state.set_state(AddressProcessingStates.awaiting_memo)


async def handle_update_report_tronscan_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'Update Report (TRC20)' button click for TronScan."""
    await callback_query.answer("Fetching TRC20 report from TronScan...")
    user_data = await state.get_data()
    address = user_data.get("current_action_address")
    # blockchain = user_data.get("current_action_blockchain") # This is implicitly TRON for this handler

    if not address:
        logging.warning(f"Could not retrieve address from state for TronScan report. UserID: {callback_query.from_user.id}") # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer("Error: Could not retrieve address for the report. Please try again.", show_alert=True)
        return

    api_client = TronScanAPI() # Uses API key from config by default
    report_content = f"TRC20 Transaction Report for Address: {address}\n"
    report_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    all_transactions = []
    current_start = 0
    # TronScan API limit is often 50, but some allow up to 200. Let's use a reasonable limit.
    # For a full report, pagination is needed. This example fetches a large batch.
    # A more robust solution would paginate until all transactions are fetched.
    # For now, let's fetch up to 200 as an example, or a configurable high number.
    # The TronScan API for transfers has a 'total' field in response, which can be used for pagination.
    # This simplified version fetches one large batch.
    fetch_limit = 200 # Max usually allowed by Tronscan for transfers per request.

    try:
        await callback_query.message.answer(f"Querying TronScan for TRC20 transfers of <code>{address}</code> (limit {fetch_limit})...", parse_mode="HTML")
        
        # Fetching all TRC20 transactions (no specific contract_address)
        # To get ALL transactions, you'd typically paginate.
        # For this example, we'll fetch a large batch (e.g., limit 200, which is often max for this endpoint)
        # and inform the user if more might exist.
        
        history_data = await api_client.get_trc20_transaction_history(
            address=address,
            limit=fetch_limit, # Fetch a large number of transactions
            start=0
        )

        if history_data and history_data.get("token_transfers"):
            transactions = history_data.get("token_transfers", [])
            total_found_api = history_data.get("total", len(transactions)) # Get total from API if available
            
            report_content += f"Found {len(transactions)} transactions in this batch (API reports total: {total_found_api}).\n"
            if total_found_api > len(transactions):
                report_content += "Note: More transactions might exist than shown in this batch due to API limits.\n"
            report_content += "--------------------------------------------------\n"

            for tx in transactions:
                raw_timestamp_ms = tx.get('block_ts')
                human_readable_timestamp = "N/A"
                if raw_timestamp_ms is not None:
                    try:
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        dt_object = datetime.fromtimestamp(timestamp_seconds)
                        human_readable_timestamp = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        human_readable_timestamp = "Invalid Timestamp"
                
                token_info = tx.get('tokenInfo', {})
                token_abbr = token_info.get('tokenAbbr', 'N/A')
                token_name = token_info.get('tokenName', 'Unknown Token')
                token_decimals = int(token_info.get('tokenDecimal', 0))
                
                quant_raw = tx.get('quant')
                amount_formatted = "N/A"
                if quant_raw is not None:
                    try:
                        amount_formatted = str(int(quant_raw) / (10**token_decimals))
                    except (ValueError, TypeError):
                        amount_formatted = f"{quant_raw} (raw)"


                report_content += (
                    f"Timestamp: {human_readable_timestamp} (Raw: {raw_timestamp_ms})\n"
                    f"TxID: {tx.get('transaction_id', 'N/A')}\n"
                    f"From: {tx.get('from_address', 'N/A')}\n"
                    f"To: {tx.get('to_address', 'N/A')}\n"
                    f"Token: {token_name} ({token_abbr})\n"
                    f"Amount: {amount_formatted} {token_abbr} (Raw Quant: {quant_raw})\n"
                    f"Confirmed: {tx.get('confirmed', 'N/A')}\n"
                    f"--------------------------------------------------\n"
                )
        elif history_data: # Response received but no token_transfers key or it's empty
            report_content += "No TRC20 transactions found or response format unexpected.\n"
            report_content += f"API Response: {str(history_data)[:500]}...\n" # Log part of the response
        else:
            report_content += "Failed to fetch TRC20 transaction history from TronScan.\n"

        # Send the report as a text file
        report_file = BufferedInputFile(report_content.encode('utf-8'), filename=f"tronscan_report_{address}.txt")
        await callback_query.message.answer_document(report_file)

    except Exception as e:
        logging.error(f"Error generating TronScan report for {address}: {e}", exc_info=True) # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer(f"Sorry, an error occurred while generating the report for {address}.")
    finally:
        await api_client.close_session() # Ensure the session is closed


async def _format_account_info_for_ai(address: str, api_client: TronScanAPI) -> str:
    info_summary = "Section: Account Overview\n--------------------------\n"
    try:
        account_info = await api_client.get_account_info(address)
        if account_info:
            trx_balance_sun = account_info.get('balance', 0)
            trx_balance = trx_balance_sun / 1_000_000
            account_name = account_info.get('account_name', 'N/A')
            create_time_ms = account_info.get('create_time')
            creation_time_str = "N/A"
            if create_time_ms:
                try:
                    creation_time_str = datetime.fromtimestamp(create_time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S UTC')
                except: # pylint: disable=bare-except
                    pass # Keep N/A
            total_tx_count = account_info.get('total_transaction_count', 'N/A')
            
            info_summary += (
                f"Address: {html.quote(address)}\n"
                f"TRX Balance: {trx_balance:.6f} TRX\n"
                f"Account Name: {html.quote(account_name)}\n"
                f"Creation Time: {creation_time_str}\n"
                f"Total Transactions: {total_tx_count}\n"
            )
        else:
            info_summary += "Could not retrieve basic account information.\n"
    except Exception as e:
        logging.error(f"Error fetching account info for AI for {address}: {e}")
        info_summary += f"Error fetching account info: {html.quote(str(e))}\n"
    info_summary += "--------------------------\n\n"
    return info_summary

async def _format_account_tags_for_ai(address: str, api_client: TronScanAPI) -> str:
    tags_summary = "Section: Account Tags\n--------------------------\n"
    try:
        tags_data = await api_client.get_account_tags(address)
        found_tags = []
        if tags_data:
            if isinstance(tags_data.get('tags'), list) and tags_data['tags']:
                for tag_info in tags_data['tags']:
                    found_tags.append(tag_info.get('tag', 'Unknown Tag'))
            elif tags_data.get('tag'): # Single tag structure
                found_tags.append(tags_data.get('tag'))
            elif address in tags_data and isinstance(tags_data[address], dict) and tags_data[address].get('tag'): # Address as key
                found_tags.append(tags_data[address]['tag'])

        if found_tags:
            tags_summary += f"Tags: {html.quote(', '.join(list(set(found_tags))))}\n"
        else:
            tags_summary += "No specific tags found for this address.\n"
    except Exception as e:
        logging.error(f"Error fetching account tags for AI for {address}: {e}")
        tags_summary += f"Error fetching account tags: {html.quote(str(e))}\n"
    tags_summary += "(Note: Tags can indicate exchange, scammer, whale, etc.)\n--------------------------\n\n"
    return tags_summary

async def _format_trc20_balances_for_ai(address: str, api_client: TronScanAPI, max_to_show: int = 5) -> str:
    balances_summary = f"Section: Top TRC20 Token Balances (Max {max_to_show} shown)\n--------------------------\n"
    try:
        balances_data = await api_client.get_account_trc20_balances(address, limit=50) # Fetch up to 50
        if balances_data and balances_data.get('trc20token_balances'):
            tokens = balances_data['trc20token_balances']
            if tokens:
                for i, token in enumerate(tokens[:max_to_show]):
                    token_name = token.get('tokenName', 'N/A')
                    token_abbr = token.get('tokenAbbr', 'N/A')
                    balance_raw = token.get('balance') # Using 'balance' which is typically unscaled
                    token_decimals = int(token.get('tokenDecimal', 0))
                    balance_formatted = "N/A"
                    if balance_raw is not None:
                        try:
                            balance_formatted = f"{int(balance_raw) / (10**token_decimals):.6f}"
                        except: # pylint: disable=bare-except
                            balance_formatted = f"{balance_raw} (raw)"
                    balances_summary += f"  - {html.quote(token_name)} ({html.quote(token_abbr)}): {html.quote(balance_formatted)}\n"
                if len(tokens) > max_to_show:
                    balances_summary += f"(Showing top {max_to_show} balances out of {len(tokens)} found in API batch of up to 50)\n"
                elif not tokens:
                    balances_summary += "No TRC20 token balances found.\n"
            else:
                balances_summary += "No TRC20 token balances found.\n"
        else:
            balances_summary += "Could not retrieve TRC20 token balances.\n"
    except Exception as e:
        logging.error(f"Error fetching TRC20 balances for AI for {address}: {e}")
        balances_summary += f"Error fetching TRC20 balances: {html.quote(str(e))}\n"
    balances_summary += "--------------------------\n\n"
    return balances_summary

async def _format_account_transfer_amounts_for_ai(address: str, api_client: TronScanAPI, max_details_to_show: int = 2) -> str:
    amounts_summary = "Section: Account Fund Flow Summary (USD)\n--------------------------\n"
    try:
        transfer_amounts = await api_client.get_account_transfer_amounts(address)
        if transfer_amounts:
            if transfer_amounts.get('transfer_in'):
                in_data = transfer_amounts['transfer_in']
                amounts_summary += "Transfer In:\n"
                amounts_summary += f"  Total Records: {in_data.get('total', 'N/A')}\n"
                amounts_summary += f"  Total USD Amount: {in_data.get('amountTotal', 'N/A')}\n"
                if isinstance(in_data.get('data'), list) and in_data['data']:
                    amounts_summary += f"  Top Senders (Max {max_details_to_show} shown):\n"
                    for item in in_data['data'][:max_details_to_show]:
                        amounts_summary += f"    - Address: {html.quote(item.get('address','N/A'))}, Amount USD: {item.get('amountInUsd','N/A')}, Tag: {html.quote(item.get('addressTag','N/A'))}\n"
            else:
                amounts_summary += "No 'transfer_in' data found.\n"
            
            amounts_summary += "\n"
            if transfer_amounts.get('transfer_out'):
                out_data = transfer_amounts['transfer_out']
                amounts_summary += "Transfer Out:\n"
                amounts_summary += f"  Total Records: {out_data.get('total', 'N/A')}\n"
                amounts_summary += f"  Total USD Amount: {out_data.get('amountTotal', 'N/A')}\n"
                if isinstance(out_data.get('data'), list) and out_data['data']:
                    amounts_summary += f"  Top Receivers (Max {max_details_to_show} shown):\n"
                    for item in out_data['data'][:max_details_to_show]:
                        amounts_summary += f"    - Address: {html.quote(item.get('address','N/A'))}, Amount USD: {item.get('amountInUsd','N/A')}, Tag: {html.quote(item.get('addressTag','N/A'))}\n"
            else:
                amounts_summary += "No 'transfer_out' data found.\n"
        else:
            amounts_summary += "Could not retrieve account fund flow summary.\n"
    except Exception as e:
        logging.error(f"Error fetching account transfer amounts for AI for {address}: {e}")
        amounts_summary += f"Error fetching account fund flow summary: {html.quote(str(e))}\n"
    amounts_summary += "--------------------------\n\n"
    return amounts_summary

async def _format_blacklist_status_for_ai(address_to_check: str, full_blacklist_entries: list, for_related: bool = False) -> str:
    """
    Checks a given address against a pre-fetched list of blacklisted entries.
    Returns a formatted string for AI consumption.
    If for_related is True, the output is more concise.
    """
    if not full_blacklist_entries:
        if not for_related:
            return f"Section: Blacklist Status for {html.quote(address_to_check)}\n--------------------------\nCould not check blacklist (no data provided).\n--------------------------\n\n"
        return "" # No data to check against for related account

    found_on_blacklist = False
    blacklist_details = ""

    for entry in full_blacklist_entries:
        if entry.get('blackAddress') == address_to_check:
            token_name = entry.get('tokenName', 'N/A')
            reason = entry.get('remark', 'No specific reason provided')
            entry_time_ms = entry.get('time')
            entry_time_str = "N/A"
            if entry_time_ms:
                try:
                    entry_time_str = datetime.fromtimestamp(entry_time_ms / 1000).strftime('%Y-%m-%d %H:%M:%S UTC')
                except: # pylint: disable=bare-except
                    pass
            
            if for_related:
                blacklist_details = f" (<b>WARNING: ON STABLECOIN BLACKLIST</b> - Token: {html.quote(token_name)})"
            else:
                blacklist_details = (
                    f"WARNING: Address is ON the stablecoin blacklist.\n"
                    f"  Token: {html.quote(token_name)}\n"
                    f"  Reason/Remark: {html.quote(reason)}\n"
                    f"  Blacklisted On: {entry_time_str}\n"
                    f"  Transaction Hash (related to blacklisting): {html.quote(entry.get('transHash', 'N/A'))}\n"
                )
            found_on_blacklist = True
            break 
    
    if for_related:
        return blacklist_details # Return only the concise note for related accounts

    # For primary address check:
    blacklist_summary = f"Section: Stablecoin Blacklist Status for {html.quote(address_to_check)}\n--------------------------\n"
    if found_on_blacklist:
        blacklist_summary += blacklist_details
    else:
        blacklist_summary += "Address is NOT found on the stablecoin blacklist.\n"
    blacklist_summary += "--------------------------\n\n"
    return blacklist_summary

async def _format_related_accounts_for_ai(address: str, api_client: TronScanAPI, full_blacklist_entries: list, max_to_show: int = 5) -> str:
    related_summary = f"Section: Top Related Accounts (Interacted With - Max {max_to_show} shown)\n--------------------------\n"
    try:
        related_data = await api_client.get_account_related_accounts(address)
        if related_data and isinstance(related_data.get('data'), list):
            accounts = related_data['data']
            if accounts:
                for acc_data in accounts[:max_to_show]:
                    related_address = acc_data.get('related_address', 'N/A')
                    # Get concise blacklist status for the related address
                    blacklist_note = await _format_blacklist_status_for_ai(related_address, full_blacklist_entries, for_related=True)
                    
                    related_summary += (
                        f"  - Address: {html.quote(related_address)}{blacklist_note}, "
                        f"Tag: {html.quote(acc_data.get('addressTag', 'N/A'))}, "
                        f"In USD: {acc_data.get('inAmountUsd', 'N/A')}, "
                        f"Out USD: {acc_data.get('outAmountUsd', 'N/A')}\n"
                    )
                if len(accounts) > max_to_show:
                    related_summary += f"(Showing top {max_to_show} related accounts out of {len(accounts)} found)\n"
            else:
                related_summary += "No related accounts found.\n"
        else:
            related_summary += "Could not retrieve related accounts information.\n"
    except Exception as e:
        logging.error(f"Error fetching related accounts for AI for {address}: {e}")
        related_summary += f"Error fetching related accounts: {html.quote(str(e))}\n"
    related_summary += "--------------------------\n\n"
    return related_summary

async def handle_ai_scam_check_tron_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'AI Scam Check (TRC20)' button click. Gathers data and prompts for language."""
    await callback_query.answer("Performing AI Scam Check for TRC20 transactions...")
    user_data = await state.get_data()
    address = user_data.get("current_action_address")

    if not address:
        logging.warning(f"Could not retrieve address from state for AI Scam Check. UserID: {callback_query.from_user.id}")
        await callback_query.message.answer("Error: Could not retrieve address for the AI report. Please try again.", show_alert=True)
        return

    # Edit the message from which the button was pressed to remove buttons and show "Gathering data..."
    try:
        await callback_query.message.edit_text(
            text=f"{callback_query.message.text}\n\n🔄 Gathering comprehensive data for <code>{html.quote(address)}</code>. This may take a moment...",
            parse_mode="HTML",
            reply_markup=None # Remove original buttons
        )
    except TelegramAPIError as e:
        logging.warning(f"Could not edit message text/markup in handle_ai_scam_check_tron_callback: {e}")
        # If edit fails, send a new message
        await callback_query.message.answer(f"🔄 Gathering comprehensive data for <code>{html.quote(address)}</code> for AI analysis. This may take a moment...", parse_mode="HTML")


    tron_api_client = TronScanAPI()
    enriched_data_for_ai = f"Comprehensive AI Scam Analysis Request for TRON Address: {html.quote(address)}\n"
    enriched_data_for_ai += f"Report requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    
    fetch_limit_trc20_history = 50
    full_blacklist_entries = []

    try:
        # 0. Fetch Stablecoin Blacklist (once)
        try:
            blacklist_response = await tron_api_client.get_stablecoin_blacklist(limit=100000) 
            if blacklist_response and isinstance(blacklist_response.get('data'), list):
                full_blacklist_entries = blacklist_response['data']
                logging.info(f"Fetched {len(full_blacklist_entries)} entries from stablecoin blacklist for AI check of {address}.")
            else:
                logging.warning(f"Could not fetch or parse stablecoin blacklist for AI check of {address}. Response: {blacklist_response}")
        except Exception as e_bl:
            logging.error(f"Error fetching stablecoin blacklist for AI for {address}: {e_bl}")
            enriched_data_for_ai += f"Section: Blacklist Status\n--------------------------\nError fetching stablecoin blacklist: {html.quote(str(e_bl))}\n--------------------------\n\n"

        # 1. Account Info
        enriched_data_for_ai += await _format_account_info_for_ai(address, tron_api_client)
        # 1.5. Blacklist status for the main address
        enriched_data_for_ai += await _format_blacklist_status_for_ai(address, full_blacklist_entries)
        # 2. Account Tags
        enriched_data_for_ai += await _format_account_tags_for_ai(address, tron_api_client)
        # 3. TRC20 Balances
        enriched_data_for_ai += await _format_trc20_balances_for_ai(address, tron_api_client, max_to_show=5)
        # 4. Account Transfer Amounts (Fund Flow Summary)
        enriched_data_for_ai += await _format_account_transfer_amounts_for_ai(address, tron_api_client, max_details_to_show=3)
        # 5. Related Accounts (now includes blacklist check)
        enriched_data_for_ai += await _format_related_accounts_for_ai(address, tron_api_client, full_blacklist_entries, max_to_show=5)
        # 6. TRC20 Transaction History
        trc20_history_summary = f"Section: Recent TRC20 Transactions (Limit {fetch_limit_trc20_history})\n--------------------------\n"
        history_data = await tron_api_client.get_trc20_transaction_history(
            address=address, limit=fetch_limit_trc20_history, start=0
        )
        if history_data and history_data.get("token_transfers"):
            transactions = history_data.get("token_transfers", [])
            total_found_api = history_data.get("total", len(transactions))
            trc20_history_summary += f"Found {len(transactions)} transactions in this batch (API reports total: {total_found_api}).\n"
            if total_found_api > len(transactions) and len(transactions) == fetch_limit_trc20_history:
                trc20_history_summary += f"Note: Analyzing the latest {fetch_limit_trc20_history} transactions. More transactions might exist.\n"
            if not transactions:
                 trc20_history_summary += "No TRC20 transactions found in the fetched batch.\n"
            else:
                for tx_idx, tx in enumerate(transactions):
                    raw_timestamp_ms = tx.get('block_ts')
                    human_readable_timestamp = "N/A"
                    if raw_timestamp_ms is not None:
                        try:
                            human_readable_timestamp = datetime.fromtimestamp(float(raw_timestamp_ms) / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError): human_readable_timestamp = "Invalid Timestamp"
                    token_info = tx.get('tokenInfo', {})
                    token_abbr = token_info.get('tokenAbbr', 'N/A')
                    token_name = token_info.get('tokenName', 'Unknown Token')
                    token_decimals = int(token_info.get('tokenDecimal', 0))
                    quant_raw = tx.get('quant')
                    amount_formatted = "N/A"
                    if quant_raw is not None:
                        try: amount_formatted = str(int(quant_raw) / (10**token_decimals))
                        except (ValueError, TypeError): amount_formatted = f"{quant_raw} (raw)"
                    trc20_history_summary += (
                        f"Tx {tx_idx + 1}:\n"
                        f"  Time: {human_readable_timestamp}, TxID: {html.quote(tx.get('transaction_id', 'N/A'))}\n"
                        f"  From: {html.quote(tx.get('from_address', 'N/A'))}, To: {html.quote(tx.get('to_address', 'N/A'))}\n"
                        f"  Token: {html.quote(token_name)} ({html.quote(token_abbr)}), Amount: {html.quote(amount_formatted)} {html.quote(token_abbr)}\n"
                        f"  Confirmed: {tx.get('confirmed', 'N/A')}\n---\n"
                    )
        elif history_data: trc20_history_summary += "No TRC20 transactions found or response format unexpected for history.\n"
        else: trc20_history_summary += "Failed to fetch TRC20 transaction history from TronScan.\n"
        trc20_history_summary += "--------------------------\n\n"
        enriched_data_for_ai += trc20_history_summary
        
        if "Could not retrieve" in enriched_data_for_ai and "Failed to fetch" in enriched_data_for_ai and "No TRC20 transactions found" in enriched_data_for_ai:
            await callback_query.message.answer("Could not fetch sufficient transaction data for AI analysis. Please try again later or check the address on an explorer.")
            return

        # Store data in FSM for the next step (language choice)
        await state.update_data(
            ai_enriched_data=enriched_data_for_ai,
            current_action_address=address # Ensure address is in state for the next handler
        )

        language_buttons = [
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="ai_lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="ai_lang:ru"),
            ]
        ]
        reply_markup_lang = InlineKeyboardMarkup(inline_keyboard=language_buttons)
        
        # Edit the message to ask for language choice
        await callback_query.message.edit_text(
            text=f"Data gathered for <code>{html.quote(address)}</code>.\n📊 Please choose the report language:",
            parse_mode="HTML",
            reply_markup=reply_markup_lang
        )
        await state.set_state(AddressProcessingStates.awaiting_ai_language_choice)

    except Exception as e:
        logging.error(f"Error during AI Scam Check data gathering for {address}: {e}", exc_info=True)
        await callback_query.message.answer(f"Sorry, an error occurred while gathering data for {html.quote(address)}.")
    finally:
        await tron_api_client.close_session()


async def handle_ai_language_choice_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles AI report language selection and triggers AI analysis."""
    await callback_query.answer()
    chosen_lang_code = callback_query.data.split(":")[1]
    lang_map = {"en": "English", "ru": "Russian"}
    chosen_lang_name = lang_map.get(chosen_lang_code, "the selected language")

    user_data = await state.get_data()
    enriched_data_for_ai = user_data.get("ai_enriched_data")
    address = user_data.get("current_action_address") # Retrieve address from state

    if not enriched_data_for_ai or not address:
        logging.warning(f"Missing enriched_data_for_ai or address in state for language choice. UserID: {callback_query.from_user.id}")
        await callback_query.message.edit_text("Error: Critical data missing for AI analysis. Please try again.", reply_markup=None)
        await state.set_state(None) # Clear state
        return

    await callback_query.message.edit_text(
        text=f"Got it! Preparing AI analysis in {chosen_lang_name} for <code>{html.quote(address)}</code>...",
        parse_mode="HTML",
        reply_markup=None
    )

    vertex_ai_client = None
    ai_analysis_text = None
    try:
        vertex_ai_client = VertexAIClient()
        
        ai_prompt = (
            f"You are a cryptocurrency transaction analyst specializing in identifying suspicious or potentially scam-related activities on the TRON blockchain. "
            f"Please analyze the following comprehensive data for the provided TRON address. "
            f"The data includes: Account Overview (TRX balance, creation time, etc.), Stablecoin Blacklist Status for the primary address, Account Tags (e.g., Exchange, Scammer), "
            f"Top TRC20 Token Balances, a Summary of USD Fund Flows (In/Out), Top Related Accounts interacted with (including their stablecoin blacklist status), and a list of Recent TRC20 Transactions. "
            f"Focus on patterns that might indicate scams, such as: \n"
            f"- The address itself being on the stablecoin blacklist (MAJOR RED FLAG).\n"
            f"- Interactions with addresses that are on the stablecoin blacklist (MAJOR RED FLAG).\n"
            f"- Unusual token types or balances (e.g., many obscure tokens, sudden large influx of unknown token).\n"
            f"- Interactions with addresses having suspicious tags.\n"
            f"- Discrepancies in fund flow (e.g., large inflows followed by rapid outflows to multiple new addresses).\n"
            f"- Connections to known scam-related addresses or patterns in related accounts.\n"
            f"- Specific transaction patterns in TRC20 history (e.g., dusting, small initial test transactions followed by larger ones, specific scam contract interactions if identifiable from patterns).\n"
            f"- Consider various scam schemes: Ponzi, Pump and Dump, Rug Pulls, Fake ICOs, Airdrop Scams, HYIPs, Phishing, Impersonation, Giveaway Scams, Romance Scams, Pig Butchering, Blackmail/Extortion, Address Poisoning, Fake Platforms/Wallets, Cloud Mining Scams, Smurfing, Mixing, Wash Trading.\n"
            f"- High frequency of small dusting transactions, or other red flags based on the combined data.\n\n"
            f"Provide a concise summary of your findings, a risk assessment (e.g., Low, Medium, High, Very High Risk) with clear justification based on the provided data points, and if possible, suggest the type of suspicious activity if any is detected. "
            f"Your report should be analytical and directly reference the data sections if they contribute to your assessment. "
            f"The final report should not exceed 1000 symbols.\n"
            f"IMPORTANT: Please provide your entire response in {chosen_lang_name.upper()}.\n\n"
            f"Comprehensive Data for Analysis:\n"
            f"{enriched_data_for_ai}"
        )

        logging.info(f"Length of prompt for AI ({chosen_lang_name}): {len(ai_prompt)} characters for address {address}.")
        ai_analysis_text = await vertex_ai_client.generate_text(prompt=ai_prompt, max_output_tokens=1024)

        response_message_text = ""
        if ai_analysis_text:
            # Audit log for AI report generation - SEND FULL AI REPORT HERE
            if TARGET_AUDIT_CHANNEL_ID and callback_query.from_user:
                user_info_audit_str = format_user_info_for_audit(callback_query.from_user)
                audit_report_text = (
                    f"📊 <b>AI Analysis Generated</b>\n"
                    f"{user_info_audit_str}\n"
                    f"<b>Address:</b> <code>{html.quote(address)}</code>\n"
                    f"<b>Blockchain:</b> TRON\n"  # Assuming this handler is TRON specific for AI check
                    f"<b>Language:</b> {html.quote(chosen_lang_name)}\n\n"
                    f"<b>Full AI Analysis:</b>\n{html.quote(ai_analysis_text)}" # Use html.escape for safety
                )
                try:
                    await send_text_to_audit_channel(callback_query.bot, audit_report_text)
                except Exception as e_audit:
                    logging.error(f"Failed to send AI report generation audit log: {e_audit}")

            report_title = f"<b>AI Scam Check Report for Address:</b> <code>{html.quote(address)}</code> ({chosen_lang_name})\n"
            report_title += f"<i>Analysis requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>\n\n"
            response_message_text = report_title + "<b><u>AI Analysis:</u></b>\n" + html.quote(ai_analysis_text)
        else:
            response_message_text = (
                f"<b>AI Scam Check Report for Address:</b> <code>{html.quote(address)}</code> ({chosen_lang_name})\n"
                f"<i>Analysis requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>\n\n"
                "The AI service did not return an analysis. This could be due to content filters, an issue with the AI model, "
                "or no specific concerns found based on the provided data. "
                "You can use the 'Get TRC20 Report' button to view raw transaction data."
            )

        if len(response_message_text) > 4096:
            logging.warning(f"AI Scam Check report for {address} ({chosen_lang_name}) is too long ({len(response_message_text)} chars). Truncating.")
            response_message_text = response_message_text[:4090] + "\n<b>[Report Truncated]</b>"
        
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="✍️ Save As Public Memo", callback_data="ai_memo_action:save_public"),
                InlineKeyboardButton(text="✍️ Save As Private Memo", callback_data="ai_memo_action:save_private"),
            ],
            [
                InlineKeyboardButton(text="⏭️ Skip Saving Memo", callback_data="ai_memo_action:skip"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Edit the "Preparing analysis..." message to show the actual report
        ai_response_message = await callback_query.message.edit_text(response_message_text, parse_mode="HTML", reply_markup=reply_markup)
        
        await state.update_data(
            ai_response_text_for_memo=ai_analysis_text, 
            ai_response_message_id=ai_response_message.message_id,
            # current_action_address and current_action_blockchain should still be in state from previous steps
            # ai_enriched_data can be cleared if no longer needed
            ai_enriched_data=None 
        )
        await state.set_state(None) # Clear the awaiting_ai_language_choice state

    except Exception as e:
        logging.error(f"Error during AI analysis or response display for {address} ({chosen_lang_name}): {e}", exc_info=True)
        try:
            await callback_query.message.edit_text(f"Sorry, an error occurred while performing the AI Scam Check for {html.quote(address)} in {chosen_lang_name}.", reply_markup=None)
        except TelegramAPIError: # If editing fails (e.g. message too old)
             await callback_query.message.answer(f"Sorry, an error occurred while performing the AI Scam Check for {html.quote(address)} in {chosen_lang_name}.")
        await state.set_state(None) # Clear state on error
    # finally:
        # VertexAIClient does not have an explicit close session method like aiohttp.ClientSession


async def handle_ai_response_memo_action_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles actions for saving AI response as memo or skipping."""
    await callback_query.answer()
    action = callback_query.data.split(":")[1] # save_public, save_private, skip

    data = await state.get_data()
    ai_response_text = data.get("ai_response_text_for_memo")
    original_message_id = data.get("ai_response_message_id")
    address_text = data.get("current_action_address")
    blockchain_text = data.get("current_action_blockchain")
    scan_message_id = data.get("current_scan_db_message_id") # Original message ID that triggered scan

    if not original_message_id or not address_text or not blockchain_text:
        logging.warning("Missing critical data in FSM for AI memo action.")
        await callback_query.message.answer("Error: Context lost for saving AI memo. Please try again.")
        return

    db = SessionLocal()
    try:
        if action == "skip":
            await callback_query.bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=original_message_id,
                text=callback_query.message.text + "\n\n<i>Skipped saving this analysis as a memo.</i>",
                parse_mode="HTML",
                reply_markup=None
            )
            logging.info(f"User skipped saving AI analysis as memo for {address_text} on {blockchain_text}")
            # Audit log for skipping memo
            if TARGET_AUDIT_CHANNEL_ID and callback_query.from_user:
                user_info_audit_str = format_user_info_for_audit(callback_query.from_user)
                audit_skip_text = (
                    f"⏭️ <b>AI Analysis Memo Action</b>\n"
                    f"{user_info_audit_str}\n"
                    f"<b>Address:</b> <code>{html.quote(address_text)}</code>\n"
                    f"<b>Blockchain:</b> {html.quote(blockchain_text.capitalize())}\n"
                    f"<b>Status:</b> AI Analysis Not Saved (Skipped by User)"
                )
                try:
                    await send_text_to_audit_channel(callback_query.bot, audit_skip_text)
                except Exception as e_audit:
                    logging.error(f"Failed to send AI memo skip audit log: {e_audit}")

        elif action in ["save_public", "save_private"]:
            if not ai_response_text:
                await callback_query.message.answer("Error: AI analysis text not found to save as memo.")
                db.close()
                return
            if not scan_message_id:
                logging.error(f"Cannot save memo for AI response: current_scan_db_message_id missing from FSM for {address_text}.")
                await callback_query.message.answer("Error: Missing original message context. Cannot save memo.")
                db.close()
                return

            memo_type = MemoType.PUBLIC if action == "save_public" else MemoType.PRIVATE
            user_db_id = None
            if memo_type == MemoType.PRIVATE:
                if callback_query.from_user:
                    db_user = get_or_create_user(db, callback_query.from_user)
                    if db_user:
                        user_db_id = db_user.id
                if not user_db_id:
                    logging.warning(f"Cannot save private AI memo for {address_text}: user identification failed.")
                    await callback_query.message.answer("Error: Could not identify user to save private memo. Memo not saved.")
                    db.close()
                    return
            
            # Ensure CryptoAddress entry exists
            crypto_address_entry = save_crypto_address(
                db,
                message_id=scan_message_id,
                address=address_text,
                blockchain=blockchain_text
            )
            if not crypto_address_entry or not crypto_address_entry.id:
                logging.error(f"Failed to save/retrieve crypto address {address_text} for AI memo.")
                await callback_query.message.answer("Error: Could not prepare address for saving AI memo.")
                db.close()
                return

            updated_address = update_crypto_address_memo(
                db=db,
                address_id=crypto_address_entry.id,
                notes=ai_response_text,
                memo_type=memo_type.value,
                user_id=user_db_id
            )

            if updated_address:
                confirmation_text = f"✅ AI analysis saved as {memo_type.value} memo for <code>{html.quote(address_text)}</code>."
                await callback_query.bot.edit_message_text(
                    chat_id=callback_query.message.chat.id,
                    message_id=original_message_id,
                    text=callback_query.message.text + f"\n\n<i>{confirmation_text}</i>",
                    parse_mode="HTML",
                    reply_markup=None
                )
                logging.info(f"AI analysis saved as {memo_type.value} memo for {address_text} by user {callback_query.from_user.id}")

                # Audit Log
                if callback_query.from_user and TARGET_AUDIT_CHANNEL_ID:
                    user_info_audit_str = format_user_info_for_audit(callback_query.from_user) # Use helper
                    
                    audit_message_text = f"""<b>📝 AI Analysis Memo Action</b>
{user_info_audit_str}
<b>Address:</b> <code>{html.quote(address_text)}</code>
<b>Blockchain:</b> {html.quote(blockchain_text.capitalize())}
<b>Status:</b> Saved as {memo_type.value.capitalize()} Memo""" # Removed AI report snippet
                    try:
                        await send_text_to_audit_channel(callback_query.bot, audit_message_text) # Use helper
                    except Exception as e_audit:
                        logging.error(f"Failed to send AI memo save audit log: {e_audit}") # pylint: disable=logging-fstring-interpolation
            else:
                logging.error(f"Failed to update memo with AI analysis for address ID {crypto_address_entry.id}") # pylint: disable=logging-fstring-interpolation
                await callback_query.message.answer("Error: Could not save the AI analysis as memo.")
        
        # Clear related FSM data
        await state.update_data(
            ai_response_text_for_memo=None,
            ai_response_message_id=None
        )

    except TelegramAPIError as e:
        logging.error(f"Telegram API error in handle_ai_response_memo_action_callback: {e}") # pylint: disable=logging-fstring-interpolation
        await callback_query.message.answer("An error occurred while processing your request. Buttons might still be visible.")
    except Exception as e:
        logging.exception(f"Error in handle_ai_response_memo_action_callback: {e}") # pylint: disable=logging-fstring-interpolation
        await callback_query.message.answer("An unexpected error occurred.")
    finally:
        if db.is_active:
            db.close()
