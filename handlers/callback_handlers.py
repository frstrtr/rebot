"""callback_handlers.py
Handles callbacks from inline buttons related to blockchain clarifications.
"""

import logging
from aiogram import html, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

from database import SessionLocal, CryptoAddress
from .address_processing import (
    _display_memos_for_address_blockchain,
    _orchestrate_next_processing_step,
    _prompt_for_next_memo,
    _send_action_prompt,  # Import the new helper
)
from .common import EXPLORER_CONFIG
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
            )
            
            # Edit the clarification message to show the choice and then send the action prompt.
            await callback_query.message.edit_text(
                f"✅ Blockchain for <code>{html.quote(address_str)}</code> set to <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
                parse_mode="HTML",
                reply_markup=None, # Remove inline keyboard from clarification message
            )
            # Send the action prompt for this address
            await _send_action_prompt(
                target_message=callback_query.message, # Send as a new message or edit an existing one
                address=address_str,
                blockchain=chosen_blockchain,
                state=state,
                db=db  # Pass the db session
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
        logging.warning("Could not retrieve address/blockchain from state for show_prev_memos. State: %s", data)
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
        logging.warning("Could not edit message reply_markup on proceed_to_memo_stage: %s", e)

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

    logging.info(f"User chose to skip further processing for address: {address_skipped} on {blockchain_skipped}")
    
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


async def handle_memo_action_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles callbacks from 'Add Memo' or 'Skip This Address' buttons."""
    await callback_query.answer()  # Acknowledge the callback

    callback_data_parts = callback_query.data.split(":")
    action = callback_data_parts[1] if len(callback_data_parts) > 1 else None

    data = await state.get_data()
    address_text = data.get("current_address_for_memo_text", "the address")
    blockchain_text = data.get("current_address_for_memo_blockchain", "N/A").capitalize()

    if not data.get("current_address_for_memo_id"):
        logging.warning("Memo action callback received but no current_address_for_memo_id in state.")
        await callback_query.message.edit_text("Error: Context for memo action lost. Please try scanning again.", reply_markup=None)
        await state.clear()
        return

    if action == "request_add":
        prompt_message = (
            f"Please reply with your memo for: <code>{html.quote(address_text)}</code> ({html.quote(blockchain_text)}).\n"
            "Or send /skip to cancel adding this memo."
        )
        # Edit the existing message (where "Add Memo" button was) or send a new one.
        # Editing is cleaner if the original message is suitable.
        try:
            await callback_query.message.edit_text(
                text=prompt_message,
                parse_mode="HTML",
                reply_markup=None,  # Remove buttons
            )
        except Exception as e:  # Fallback if edit fails (e.g. message too old)
            logging.warning(f"Failed to edit message for memo prompt, sending new: {e}")
            await callback_query.message.answer(
                text=prompt_message,
                parse_mode="HTML",
            )
        await state.set_state(AddressProcessingStates.awaiting_memo)

    elif action == "skip_current":
        pending_addresses = data.get("pending_addresses_for_memo", [])

        await callback_query.message.edit_text(
            f"Skipped adding memo for: <code>{html.quote(address_text)}</code> ({html.quote(blockchain_text)}).",
            parse_mode="HTML",
            reply_markup=None,  # Remove buttons
        )

        if pending_addresses:
            # Call _prompt_for_next_memo with the original message context (callback_query.message)
            # and the remaining list.
            await _prompt_for_next_memo(callback_query.message, state, pending_addresses)
        else:
            await callback_query.message.answer("All addresses processed. You can send new messages.")
            await state.clear()
    else:
        logging.warning(f"Unknown memo_action callback: {callback_query.data}")
        await callback_query.message.answer("Unexpected selection error.")
