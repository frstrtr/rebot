"""callback_handlers.py
Handles callbacks from inline buttons related to blockchain clarifications.
"""

import logging
from aiogram import html, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

from database import SessionLocal
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
    """Handles callbacks from inline buttons related to blockchain clarifications.
    This function processes the callback data to either confirm a blockchain choice
    or skip the clarification for a specific address.
    It updates the state with the chosen blockchain or skips the clarification,
    and orchestrates the next processing step based on the user's choice.
    """

    await callback_query.answer()
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )

    if not item_being_clarified:
        await callback_query.message.answer(
            "Error: Could not determine which address this choice is for. Please try scanning again."
        )
        await state.clear()
        return
    if callback_query.data is None:
        logging.warning("Callback with None data in blockchain clarification.")
        await callback_query.message.answer("An error occurred (no data).")
        return

    action_parts = callback_query.data.split(":")
    if len(action_parts) < 2:
        logging.warning("Invalid callback data: %s", callback_query.data)
        await callback_query.message.answer("An error occurred (invalid format).")
        return

    param_one = action_parts[1]
    if param_one == "chosen":
        if len(action_parts) < 3:
            logging.warning("Invalid 'chosen' callback: %s", callback_query.data)
            await callback_query.message.answer("Error (missing choice).")
            return

        chosen_blockchain = action_parts[
            2
        ]  # This is the blockchain key (e.g., 'ethereum', 'tron')
        address_str = item_being_clarified["address"]

        # This address is now the one to be actioned upon if user proceeds to memo.
        addresses_for_memo_fsm = [{"address": address_str, "blockchain": chosen_blockchain}]
        await state.update_data(
            addresses_for_memo_prompt_details=addresses_for_memo_fsm,
            current_item_for_blockchain_clarification=None,
        )

        # Send the new action prompt, editing the previous message
        await _send_action_prompt(
            callback_query.message, address_str, chosen_blockchain, state, edit_message=True
        )
        # No direct orchestration here; user interaction drives it.

    elif param_one == "skip":  # Skips blockchain clarification for this item
        await state.update_data(current_item_for_blockchain_clarification=None)
        await callback_query.message.edit_text(
            f"Skipped blockchain clarification for: <code>{html.quote(item_being_clarified['address'])}</code>.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await _orchestrate_next_processing_step(callback_query.message, state)  # Check if other items need clarification
    else:
        logging.warning(
            "Unknown callback for blockchain clarification: %s", callback_query.data
        )
        await callback_query.message.answer("Unexpected selection error.")


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
