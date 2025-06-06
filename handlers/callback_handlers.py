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


async def handle_ai_scam_check_tron_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles the 'AI Scam Check (TRC20)' button click."""
    await callback_query.answer("Performing AI Scam Check for TRC20 transactions...")
    user_data = await state.get_data()
    address = user_data.get("current_action_address")
    blockchain = user_data.get("current_action_blockchain", "tron") # Should be set by _send_action_prompt

    if not address:
        logging.warning(f"Could not retrieve address from state for AI Scam Check. UserID: {callback_query.from_user.id}") # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer("Error: Could not retrieve address for the AI report. Please try again.", show_alert=True)
        return

    tron_api_client = TronScanAPI()
    vertex_ai_client = None 

    raw_transactions_summary = f"TRC20 Transaction Data for Address: {address}\n"
    raw_transactions_summary += f"Report requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    fetch_limit = 50 

    ai_response_message = None # To store the message object for later editing

    try:
        await callback_query.message.answer(f"Querying TronScan for recent TRC20 transfers of <code>{html.quote(address)}</code> (limit {fetch_limit})...", parse_mode="HTML")
        
        history_data = await tron_api_client.get_trc20_transaction_history(
            address=address,
            limit=fetch_limit,
            start=0
        )

        if history_data and history_data.get("token_transfers"):
            transactions = history_data.get("token_transfers", [])
            total_found_api = history_data.get("total", len(transactions))
            
            raw_transactions_summary += f"Found {len(transactions)} transactions in this batch (API reports total: {total_found_api}).\n"
            if total_found_api > len(transactions) and len(transactions) == fetch_limit:
                raw_transactions_summary += f"Note: Analyzing the latest {fetch_limit} transactions. More transactions might exist.\n"
            raw_transactions_summary += "--------------------------------------------------\n"

            for tx_idx, tx in enumerate(transactions):
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

                raw_transactions_summary += (
                    f"Transaction {tx_idx + 1}:\n"
                    f"  Timestamp: {human_readable_timestamp}\n"
                    f"  TxID: {tx.get('transaction_id', 'N/A')}\n"
                    f"  From: {tx.get('from_address', 'N/A')}\n"
                    f"  To: {tx.get('to_address', 'N/A')}\n"
                    f"  Token: {token_name} ({token_abbr})\n"
                    f"  Amount: {amount_formatted} {token_abbr}\n"
                    f"  Confirmed: {tx.get('confirmed', 'N/A')}\n"
                    f"--------------------------------------------------\n"
                )
            
            if not transactions:
                 raw_transactions_summary += "No TRC20 transactions found in the fetched batch.\n"
        
        elif history_data:
            raw_transactions_summary += "No TRC20 transactions found or response format unexpected.\n"
        else:
            raw_transactions_summary += "Failed to fetch TRC20 transaction history from TronScan.\n"
            await callback_query.message.answer("Could not fetch transaction data for AI analysis.")
            return 

        await callback_query.message.answer("Sending transaction data to AI for analysis...")
        
        try:
            vertex_ai_client = VertexAIClient() 
        except Exception as e:
            logging.error(f"Failed to initialize VertexAIClient for AI Scam Check: {e}", exc_info=True) 
            await callback_query.message.answer("Error: Could not initialize the AI service. Please try again later.")
            return

        ai_prompt = (
            "You are a cryptocurrency transaction analyst specializing in identifying suspicious or potentially scam-related activities. "
            "Please analyze the following TRC20 transaction data for the address provided. "
            "Focus on patterns that might indicate scams, such as unusual token transfers, "
            "interactions with known scam contracts (if you have such knowledge, otherwise infer from patterns), "
            "various known scam schemes (e.g., dusting attacks, Ponzi schemes, decimal point manipulation, "
            "pig butchering, money laundering, Ponzi Schemes, Pump and Dump Schemes, Rug Pulls, Fake ICOs (Initial Coin Offerings), "
            "Airdrop Scams, High-Yield Investment Programs (HYIPs), Phishing Scams, Impersonation Scams, Giveaway Scams, Romance Scams, "
            "Pig Butchering Scams, Blackmail/Extortion Scams, Address Poisoning/Spoofing, Fake Exchanges/Platforms, Fake Wallets/Apps, "
            "Cloud Mining Scams, Smurfing (Structuring), Mixing/Tumblers, Wash Trading), "
            "high frequency of small dusting transactions, or other red flags. "
            "Provide a brief summary of your findings and a risk assessment (e.g., Low, Medium, High Risk) with justification. "
            "Report should not exceed 1000 symbols.\n\n"
            "Transaction Data:\n"
            f"{raw_transactions_summary}"
        )

        ai_analysis_text = await vertex_ai_client.generate_text(prompt=ai_prompt, max_output_tokens=1024) 

        response_message_text = ""
        if ai_analysis_text:
            report_title = f"<b>AI Scam Check Report for Address:</b> <code>{html.quote(address)}</code>\n"
            report_title += f"<i>Analysis requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>\n\n"
            response_message_text = report_title + "<b><u>AI Analysis:</u></b>\n" + html.quote(ai_analysis_text)
        else:
            response_message_text = (
                f"<b>AI Scam Check Report for Address:</b> <code>{html.quote(address)}</code>\n"
                f"<i>Analysis requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>\n\n"
                "The AI service did not return an analysis. This could be due to content filters, an issue with the AI model, "
                "or no specific concerns found based on the provided data. "
                "You can use the 'Get TRC20 Report' button to view raw transaction data."
            )

        if len(response_message_text) > 4096:
            logging.warning(f"AI Scam Check report for {address} is too long ({len(response_message_text)} chars) for a single Telegram message. Truncating.") 
            response_message_text = response_message_text[:4090] + "\n<b>[Report Truncated]</b>"
        
        # Prepare buttons for saving memo
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

        ai_response_message = await callback_query.message.answer(response_message_text, parse_mode="HTML", reply_markup=reply_markup)
        
        # Store necessary info in FSM for the memo action handler
        await state.update_data(
            ai_response_text_for_memo=ai_analysis_text, # Store the actual AI analysis
            ai_response_message_id=ai_response_message.message_id,
            # current_action_address and current_action_blockchain are already in state
            # current_scan_db_message_id should also be in state from earlier flow
        )

    except Exception as e:
        logging.error(f"Error during AI Scam Check for {address}: {e}", exc_info=True) # pylint:disable=logging-fstring-interpolation
        await callback_query.message.answer(f"Sorry, an error occurred while performing the AI Scam Check for {address}.")
    finally:
        await tron_api_client.close_session()


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
                    user = callback_query.from_user
                    user_info_parts = [f"ID: <code>{user.id}</code>"]
                    name_parts = [html.quote(n) for n in [user.first_name, user.last_name] if n]
                    if name_parts: user_info_parts.append(f"Name: {' '.join(name_parts)}")
                    if user.username: user_info_parts.append(f"Username: @{html.quote(user.username)}")
                    user_info_audit_str = "\n".join(["<b>👤 User Details:</b>"] + user_info_parts)
                    
                    audit_message_text = f"""<b>📝 AI Analysis Saved as Memo</b>
{user_info_audit_str}
<b>Address:</b> <code>{html.quote(address_text)}</code>
<b>Blockchain:</b> {html.quote(blockchain_text.capitalize())}
<b>Memo Type:</b> {memo_type.value.capitalize()}
<b>Memo (AI Analysis):</b> {html.quote(ai_response_text[:1000])}{'...' if len(ai_response_text) > 1000 else ''}"""
                    try:
                        await callback_query.bot.send_message(TARGET_AUDIT_CHANNEL_ID, audit_message_text, parse_mode="HTML")
                    except Exception as e_audit:
                        logging.error(f"Failed to send AI memo audit log: {e_audit}")
            else:
                logging.error(f"Failed to update memo with AI analysis for address ID {crypto_address_entry.id}")
                await callback_query.message.answer("Error: Could not save the AI analysis as memo.")
        
        # Clear related FSM data
        await state.update_data(
            ai_response_text_for_memo=None,
            ai_response_message_id=None
        )

    except TelegramAPIError as e:
        logging.error(f"Telegram API error in handle_ai_response_memo_action_callback: {e}")
        await callback_query.message.answer("An error occurred while processing your request. Buttons might still be visible.")
    except Exception as e:
        logging.exception(f"Error in handle_ai_response_memo_action_callback: {e}")
        await callback_query.message.answer("An unexpected error occurred.")
    finally:
        if db.is_active:
            db.close()
