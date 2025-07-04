"""callback_handlers.py
Handles general callbacks, blockchain clarifications, and memo interactions.
"""

import logging
from aiogram import html, types

# from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

# from datetime import datetime  # Keep if used by any remaining handlers

from database import SessionLocal, get_or_create_user, save_crypto_address
from database.models import MemoType

# from database.queries import update_crypto_address_memo

# from .common import EXPLORER_CONFIG # Keep if used by any remaining handlers
from .states import AddressProcessingStates
from .address_processing import (
    _display_memos_for_address_blockchain,
    _orchestrate_next_processing_step,
    # _prompt_for_next_memo, # This is likely called by _orchestrate_next_processing_step
    _send_action_prompt,
)
from .helpers import _create_bot_deeplink_html  # Ensure this is imported

# Import new callback modules if they are called from here (unlikely for this structure)


async def handle_blockchain_clarification_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles blockchain clarification button presses."""
    await callback_query.answer()
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")

    if not item_being_clarified:
        logging.warning(
            "Blockchain clarification callback but no item_being_clarified in state."
        )
        await callback_query.message.answer(
            "Error: Could not determine address to clarify. Try scanning again."
        )
        await state.clear()
        return

    action = callback_query.data.split(":")[1]
    address_str = item_being_clarified["address"]
    db = SessionLocal()

    bot_info = await callback_query.bot.get_me()
    bot_username = bot_info.username
    address_deeplink = _create_bot_deeplink_html(address_str, bot_username)

    try:
        if action == "chosen":
            chosen_blockchain = callback_query.data.split(":")[2]
            logging.info(
                "User chose blockchain '%s' for address '%s'",
                chosen_blockchain,
                address_str,
            )
            addresses_for_memo_prompt_details_fsm = [
                {"address": address_str, "blockchain": chosen_blockchain}
            ]
            fsm_update_payload = {
                "addresses_for_memo_prompt_details": addresses_for_memo_prompt_details_fsm,
                "current_item_for_blockchain_clarification": None,
                "pending_blockchain_clarification": data.get(
                    "pending_blockchain_clarification", []
                ),
                "current_action_address": address_str,
                "current_action_blockchain": chosen_blockchain,
            }
            if "current_scan_db_message_id" in data:
                fsm_update_payload["current_scan_db_message_id"] = data.get(
                    "current_scan_db_message_id"
                )
            else:
                logging.error(
                    f"CRITICAL: current_scan_db_message_id missing for {address_str}. Data: {data}"
                )
            await state.update_data(**fsm_update_payload)
            await callback_query.message.edit_text(
                f"✅ Blockchain for {address_deeplink} set to <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            await _send_action_prompt(
                target_message=callback_query.message,
                address=address_str,
                blockchain=chosen_blockchain,
                state=state,
                db=db,
                acting_telegram_user_id=callback_query.from_user.id,
            )
            await state.set_state(None)
        elif action == "skip":
            logging.info(
                "User skipped blockchain clarification for address %s", address_str
            )
            await callback_query.message.edit_text(
                f"⏭️ Skipped blockchain clarification for {address_deeplink}.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            await state.update_data(current_item_for_blockchain_clarification=None)
            await _orchestrate_next_processing_step(callback_query.message, state)
        else:
            logging.warning("Unknown action in blockchain clarification: %s", action)
            await callback_query.message.answer("Invalid action. Please try again.")
    finally:
        if db.is_active:
            db.close()


async def handle_show_previous_memos_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Show Previous Memos' button click."""
    await callback_query.answer()
    data = await state.get_data()
    action_details_list = data.get("addresses_for_memo_prompt_details")

    if (
        not action_details_list
        or not isinstance(action_details_list, list)
        or not action_details_list[0]
    ):
        logging.warning(
            "Could not retrieve context for show_prev_memos. State: %s", data
        )
        await callback_query.message.answer(
            "Error: Context lost. Please try scanning again."
        )
        return

    current_action_info = action_details_list[0]
    address = current_action_info.get("address")
    blockchain = current_action_info.get("blockchain")

    if not address or not blockchain:
        logging.warning(
            "Missing address/blockchain for show_prev_memos. Info: %s",
            current_action_info,
        )
        await callback_query.message.answer(
            "Error: Could not retrieve full address details."
        )
        return

    db_session = SessionLocal()
    try:
        await _display_memos_for_address_blockchain(
            callback_query.message, address, blockchain, db_session
        )
    finally:
        if db_session.is_active:
            db_session.close()

    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        logging.debug(
            f"Clearing FSM state from {current_fsm_state} after showing memos."
        )
        await state.set_state(None)


async def handle_proceed_to_memo_stage_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Add/Manage Memo' button click from the action prompt."""
    await callback_query.answer("Loading memo options...")
    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError as e:
        logging.warning(
            "Could not edit message reply_markup on proceed_to_memo_stage: %s", e
        )
    await _orchestrate_next_processing_step(callback_query.message, state)


async def handle_skip_address_action_stage_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles skipping the entire address processing at the action prompt stage."""
    await callback_query.answer()
    data = await state.get_data()
    address_skipped = data.get("current_action_address")
    blockchain_skipped = data.get("current_action_blockchain")

    bot_info = await callback_query.bot.get_me()
    bot_username = bot_info.username

    if not address_skipped or not blockchain_skipped:
        logging.warning(
            f"User {callback_query.from_user.id} - SkipAction: Missing context. Callback: {callback_query.data}. State: {data}"
        )
        try:
            await callback_query.message.edit_text(
                "Could not determine address to skip. Continuing...", reply_markup=None
            )
        except TelegramAPIError as e_edit:
            logging.error(
                f"Failed to edit message on skip_address_action_stage context error: {e_edit}"
            )
        await _orchestrate_next_processing_step(callback_query.message, state)
        return

    address_deeplink_skipped = _create_bot_deeplink_html(address_skipped, bot_username)
    logging.info(
        f"User {callback_query.from_user.id} skipped further processing for {address_skipped} on {blockchain_skipped}"
    )
    try:
        await callback_query.message.edit_text(
            f"⏭️ Skipped actions for {address_deeplink_skipped} on {html.quote(blockchain_skipped.capitalize())}.",
            parse_mode="HTML",
            reply_markup=None,
            disable_web_page_preview=True,
        )
    except TelegramAPIError as e:
        logging.warning(f"Failed to edit message on skip action: {e}")
        await callback_query.message.answer(
            f"⏭️ Skipped actions for {address_deeplink_skipped} on {html.quote(blockchain_skipped.capitalize())}.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await state.update_data(addresses_for_memo_prompt_details=[])
    await _orchestrate_next_processing_step(callback_query.message, state)


async def handle_show_public_memos_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Show Public Memos' button click."""
    await callback_query.answer()
    data = await state.get_data()
    action_details_list = data.get("addresses_for_memo_prompt_details")
    if (
        not action_details_list
        or not isinstance(action_details_list, list)
        or not action_details_list[0]
    ):
        logging.warning("Context lost for show_public_memos. State: %s", data)
        await callback_query.message.answer(
            "Error: Context lost. Please try scanning again."
        )
        return
    current_action_info = action_details_list[0]
    address = current_action_info.get("address")
    blockchain = current_action_info.get("blockchain")
    if not address or not blockchain:
        logging.warning(
            "Missing address/blockchain for show_public_memos. Info: %s",
            current_action_info,
        )
        await callback_query.message.answer(
            "Error: Could not retrieve full address details."
        )
        return
    db_session = SessionLocal()
    try:
        await _display_memos_for_address_blockchain(
            message_target=callback_query.message,
            address=address,
            blockchain=blockchain,
            db=db_session,
            memo_scope="public",
            requesting_telegram_user_id=callback_query.from_user.id,  # Added this line
        )
    finally:
        if db_session.is_active:
            db_session.close()


async def handle_show_private_memos_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Show Private Memos' button click."""
    await callback_query.answer("Fetching your private memos...")
    user_fsm_data = await state.get_data()
    address = user_fsm_data.get("current_action_address")
    blockchain = user_fsm_data.get("current_action_blockchain")

    if not address or not blockchain:
        logging.error(
            "Address or blockchain missing in state for showing private memos."
        )
        await callback_query.message.answer(
            "Error: Context missing. Cannot show private memos."
        )
        return

    db = SessionLocal()
    try:
        requesting_user_from_callback = callback_query.from_user
        db_user = get_or_create_user(db, requesting_user_from_callback)

        if not db_user:
            logging.error(
                f"Could not get/create DB user for Telegram ID {requesting_user_from_callback.id}"
            )
            await callback_query.message.answer(
                "Error: Could not identify user in database."
            )
            return

        # Call _display_memos_for_address_blockchain with all required parameters
        await _display_memos_for_address_blockchain(
            message_target=callback_query.message,
            address=address,
            blockchain=blockchain,
            db=db,
            memo_scope="private_own",
            requesting_user_db_id=db_user.id,
            requesting_telegram_user_id=requesting_user_from_callback.id,  # Ensure this is passed
        )
    except Exception as e:
        logging.exception(f"Error in handle_show_private_memos_callback: {e}")
        await callback_query.message.answer(
            "An error occurred while fetching your private memos."
        )
    finally:
        if db.is_active:
            db.close()


async def handle_request_memo_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles 'Add Public Memo' or 'Add Private Memo' button clicks."""
    await callback_query.answer()
    try:
        _prefix, memo_type_str = callback_query.data.split(":", 1)
        if memo_type_str not in [MemoType.PUBLIC.value, MemoType.PRIVATE.value]:
            raise ValueError("Invalid memo type")
    except ValueError:
        logging.warning(
            f"Invalid callback data for request_memo: {callback_query.data}"
        )
        await callback_query.message.answer(
            "Error processing memo request. Please try again."
        )
        return

    data = await state.get_data()
    current_address_details_list = data.get("addresses_for_memo_prompt_details")
    if (
        not current_address_details_list
        or not isinstance(current_address_details_list, list)
        or not current_address_details_list[0]
    ):
        logging.error(
            "State 'addresses_for_memo_prompt_details' not set correctly for memo request."
        )
        await callback_query.message.answer(
            "Error: Critical context missing. Please restart."
        )
        await state.clear()
        return

    current_address_info = current_address_details_list[0]
    address_text = current_address_info.get("address")
    blockchain_text = current_address_info.get("blockchain", "N/A").capitalize()

    bot_info = await callback_query.bot.get_me()
    bot_username = bot_info.username
    address_deeplink = _create_bot_deeplink_html(address_text, bot_username)

    db_session = SessionLocal()
    try:
        current_scan_db_message_id = data.get("current_scan_db_message_id")
        if not current_scan_db_message_id:
            logging.error(
                "Cannot save address for memo: current_scan_db_message_id missing."
            )
            await callback_query.message.answer("Error: Missing message context.")
            await state.clear()
            return
        db_crypto_address = save_crypto_address(
            db_session,
            current_scan_db_message_id,
            address_text,
            current_address_info.get("blockchain"),
        )
        if not db_crypto_address or not db_crypto_address.id:
            logging.error(
                f"Failed to save/retrieve crypto address {address_text} for memo."
            )
            await callback_query.message.answer(
                "Error: Could not prepare address for memo."
            )
            return
        await state.update_data(
            current_address_for_memo_id=db_crypto_address.id,
            current_address_for_memo_text=address_text,
            current_address_for_memo_blockchain=current_address_info.get("blockchain"),
            intended_memo_type=memo_type_str,
            pending_addresses_for_memo=[],
        )
    finally:
        if db_session.is_active:
            db_session.close()

    prompt_message_text = (
        f"Please reply with your {memo_type_str} memo for: {address_deeplink} ({html.quote(blockchain_text)}).\n"
        "Or send /skip to cancel adding this memo."
    )
    try:
        await callback_query.message.edit_text(
            text=prompt_message_text,
            parse_mode="HTML",
            reply_markup=None,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.warning(f"Failed to edit message for memo prompt, sending new: {e}")
        await callback_query.message.answer(
            text=prompt_message_text, parse_mode="HTML", disable_web_page_preview=True
        )
    await state.set_state(AddressProcessingStates.awaiting_memo)
