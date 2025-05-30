"""callback_handlers.py
Handles callbacks from inline buttons related to blockchain clarifications.
"""

import logging
from aiogram import html, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import SessionLocal
from .address_processing import (
    _display_memos_for_address_blockchain,
    _orchestrate_next_processing_step,
    _prompt_for_next_memo,  # Import this
)
from .common import EXPLORER_CONFIG
from .states import AddressProcessingStates  # Import this


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

        db_session_callback = SessionLocal()
        try:
            await _display_memos_for_address_blockchain(
                callback_query.message,
                address_str,
                chosen_blockchain,
                db_session_callback,
            )
        finally:
            if db_session_callback.is_active:
                db_session_callback.close()

        addresses_for_memo_prompt_details.append(
            {"address": address_str, "blockchain": chosen_blockchain}
        )
        await state.update_data(
            addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
            current_item_for_blockchain_clarification=None,
        )

        confirmation_text = f"Noted: Address <code>{html.quote(address_str)}</code> will be associated with <b>{html.quote(chosen_blockchain.capitalize())}</b>."

        reply_markup_for_confirmation = None
        if chosen_blockchain.lower() in EXPLORER_CONFIG:
            config_data = EXPLORER_CONFIG[chosen_blockchain.lower()]
            explorer_name = config_data["name"]
            url = config_data["url_template"].format(address=address_str)
            button_text_addr = (
                f"{address_str[:6]}...{address_str[-4:]}"
                if len(address_str) > 20
                else address_str
            )
            explorer_button = InlineKeyboardButton(
                text=f"🔎 View {button_text_addr} on {explorer_name}",
                url=url,
            )
            reply_markup_for_confirmation = InlineKeyboardMarkup(
                inline_keyboard=[[explorer_button]]
            )

        await callback_query.message.edit_text(
            text=confirmation_text,
            parse_mode="HTML",
            reply_markup=reply_markup_for_confirmation,  # Add the button here
        )
        await _orchestrate_next_processing_step(callback_query.message, state)

    elif param_one == "skip":
        await state.update_data(current_item_for_blockchain_clarification=None)
        await callback_query.message.edit_text(
            f"Skipped clarification for: <code>{html.quote(item_being_clarified['address'])}</code>.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await _orchestrate_next_processing_step(callback_query.message, state)
    else:
        logging.warning(
            "Unknown callback for blockchain clarification: %s", callback_query.data
        )
        await callback_query.message.answer("Unexpected selection error.")


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
