"""callback_handlers.py
Handles callbacks from inline buttons related to blockchain clarifications.
"""

import logging
from aiogram import html, types
from aiogram.fsm.context import FSMContext

from database import SessionLocal
from .address_processing import (
    _display_memos_for_address_blockchain,
    _orchestrate_next_processing_step,
)


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
        chosen_blockchain = action_parts[2]
        db_session_callback = SessionLocal()
        try:
            await _display_memos_for_address_blockchain(
                callback_query.message,
                item_being_clarified["address"],
                chosen_blockchain,
                db_session_callback,
            )
        finally:
            if db_session_callback.is_active:
                db_session_callback.close()
        addresses_for_memo_prompt_details.append(
            {
                "address": item_being_clarified["address"],
                "blockchain": chosen_blockchain,
            }
        )
        await state.update_data(
            addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
            current_item_for_blockchain_clarification=None,
        )
        await callback_query.message.edit_text(
            f"Noted: <code>{html.quote(item_being_clarified['address'])}</code> on <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
            parse_mode="HTML",
            reply_markup=None,
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
