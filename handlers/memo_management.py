"""
memo_management.py
Deals with displaying, adding, and processing memos for addresses.
"""
import logging
from typing import Optional
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    get_or_create_user,
    CryptoAddress,
    CryptoAddressStatus,
)
from database.models import MemoType # Assuming MemoType is in database.models
from database.queries import update_crypto_address_memo # For saving memos
from .common import MAX_TELEGRAM_MESSAGE_LENGTH, TARGET_AUDIT_CHANNEL_ID
# from .states import AddressProcessingStates # Not directly setting states here, but might be needed by callers

async def _display_memos_for_address_blockchain(
    message_target: types.Message, # Can be Message or CallbackQuery.message
    address: str,
    blockchain: str,
    db: Session,
    memo_scope: str = "public",
    requesting_user_db_id: Optional[int] = None,
):
    query = db.query(CryptoAddress).filter(
        func.lower(CryptoAddress.address) == address.lower(),
        func.lower(CryptoAddress.blockchain) == blockchain.lower(),
        CryptoAddress.notes.isnot(None),
        CryptoAddress.notes != "",
    )

    header_scope_text = "Previous Public Memos"
    if memo_scope == "private_own":
        if not requesting_user_db_id:
            logging.error("User ID not provided for private memos in _display_memos.")
            await message_target.answer(
                "[_display_memos] Error: User ID missing for private memo display.", parse_mode="HTML"
            )
            return
        query = query.filter(
            CryptoAddress.memo_type == MemoType.PRIVATE.value,
            CryptoAddress.memo_added_by_user_id == requesting_user_db_id,
        )
        header_scope_text = "Your Private Memos"
    else:  # Default to public
        query = query.filter(
            or_(
                CryptoAddress.memo_type == MemoType.PUBLIC.value,
                CryptoAddress.memo_type.is_(None),
            )
        )

    existing_memos_specific = query.order_by(CryptoAddress.id.desc()).all() # Show newest first

    if not existing_memos_specific:
        no_memos_message = f"ℹ️ No {header_scope_text.lower()} found for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())}."
        if memo_scope == "private_own":
            no_memos_message = f"ℹ️ You have no private memos for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())}."
        await message_target.answer(no_memos_message, parse_mode="HTML")
        return

    list_header = f"📜 <b>{header_scope_text} for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())}:</b>"
    memo_item_lines = []
    for memo_item in existing_memos_specific:
        status_display = memo_item.status.value if isinstance(memo_item.status, CryptoAddressStatus) else str(memo_item.status or "N/A")
        # Consider adding timestamp: html.quote(memo_item.timestamp.strftime('%Y-%m-%d %H:%M'))
        memo_item_lines.append(f"  • (<i>{status_display}</i>): {html.quote(memo_item.notes)}")

    # Message splitting logic (simplified for brevity, original logic was complex)
    current_message = list_header
    for line in memo_item_lines:
        if len(current_message) + len(line) + 1 > MAX_TELEGRAM_MESSAGE_LENGTH:
            await message_target.answer(current_message, parse_mode="HTML")
            current_message = line # Start new message with the line itself
        else:
            current_message += "\n" + line
    
    if current_message: # Send the last part
        await message_target.answer(current_message, parse_mode="HTML")


async def _prompt_for_next_memo( # This is more like _prompt_for_action_on_saved_address
    message_to_reply_to: Message, state: FSMContext, pending_list: list
):
    if not pending_list:
        await state.clear() # Assuming orchestrator handles final "all processed" message
        return

    next_address_info = pending_list.pop(0) # Get first item
    address_text = next_address_info['address']
    blockchain_text = next_address_info['blockchain'].capitalize()
    address_db_id = next_address_info['id'] # Assuming 'id' is the DB ID of CryptoAddress record

    await state.update_data(
        current_address_for_memo_id=address_db_id,
        current_address_for_memo_text=address_text,
        current_address_for_memo_blockchain=next_address_info['blockchain'],
        pending_addresses_for_memo=pending_list, # Remaining items
    )

    # This prompt is generic for actions on a saved address, not just memo.
    # The original _send_action_prompt is for newly scanned/clarified ones.
    # This one is for items that are already saved and now we are iterating.
    # For simplicity, let's reuse a similar structure to _send_action_prompt
    # or make this specifically for "Add Memo / Skip" after clarification.
    # The original code had a simpler prompt here.
    
    prompt_text = (
        f"[_prompt_for_next_memo] Processing saved address: <code>{html.quote(address_text)}</code> ({html.quote(blockchain_text)}).\n"
        "What would you like to do next for this address?"
    )
    
    # Simplified buttons for this stage, assuming it's post-clarification, pre-memo decision
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="✍️ Add Memo", callback_data="memo_action:request_add"),
            InlineKeyboardButton(text="⏭️ Skip This Address", callback_data="memo_action:skip_current"),
        ]
        # Potentially add "Show Memos" or "View on Explorer" here too if needed for this stage
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await message_to_reply_to.answer(prompt_text, reply_markup=keyboard, parse_mode="HTML")
    # State for awaiting memo text is set by the "Add Memo" callback handler


async def _process_memo_action(message: Message, state: FSMContext):
    db = SessionLocal()
    try:
        data = await state.get_data()
        address_id_to_update = data.get("current_address_for_memo_id")
        address_text_for_display = data.get("current_address_for_memo_text", "the address")
        blockchain_for_display = data.get("current_address_for_memo_blockchain", "N/A")
        pending_addresses = data.get("pending_addresses_for_memo", [])
        intended_memo_type_str = data.get("intended_memo_type", MemoType.PUBLIC.value)

        if not address_id_to_update:
            logging.warning("Attempted to process memo without address_id in state.")
            await message.answer("Error: Could not determine which address to update. Please try again.")
            await state.clear()
            db.close()
            return

        memo_text = message.text.strip()
        if not memo_text:
            await message.reply("Memo cannot be empty. Please provide a memo or use a skip command.")
            db.close()
            return

        # Get internal DB user ID for memo_added_by_user_id
        memo_user_db_id = None
        if intended_memo_type_str == MemoType.PRIVATE.value:
            if message.from_user:
                db_user = get_or_create_user(db, message.from_user)
                if db_user:
                    memo_user_db_id = db_user.id
            if not memo_user_db_id: # If still None (e.g. message.from_user was None or db_user failed)
                logging.warning("Cannot save private memo: user identification failed.")
                await message.answer("Error: Could not identify user to save private memo. Memo not saved as private.")
                # Fallback or clear state. For now, let it proceed but it won't be private if memo_user_db_id is None.
                # Or more strictly:
                # await state.clear()
                # db.close()
                # return
        
        updated_address = update_crypto_address_memo(
            db=db,
            address_id=address_id_to_update, # This should be the ID of an existing CryptoAddress record
            notes=memo_text,
            memo_type=intended_memo_type_str, # Pass the string value
            user_id=memo_user_db_id # This is memo_added_by_user_id
        )

        if updated_address:
            await message.answer(
                f"📝 {intended_memo_type_str.capitalize()} memo saved for <code>{html.quote(address_text_for_display)}</code> ({html.quote(blockchain_for_display.capitalize())}).",
                parse_mode="HTML",
            )
            # Audit Log
            if message.from_user:
                user = message.from_user
                user_info_parts = [f"ID: <code>{user.id}</code>"]
                name_parts = [html.quote(n) for n in [user.first_name, user.last_name] if n]
                if name_parts: user_info_parts.append(f"Name: {' '.join(name_parts)}")
                if user.username: user_info_parts.append(f"Username: @{html.quote(user.username)}")
                user_info_audit_str = "\n".join(["<b>👤 User Details:</b>"] + user_info_parts)
                
                audit_message_text = f"""<b>📝 New Memo Added</b>
{user_info_audit_str}
<b>Address:</b> <code>{html.quote(address_text_for_display)}</code>
<b>Blockchain:</b> {html.quote(blockchain_for_display.capitalize())}
<b>Memo:</b> {html.quote(memo_text)}"""
                try:
                    await message.bot.send_message(TARGET_AUDIT_CHANNEL_ID, audit_message_text, parse_mode="HTML")
                except Exception as e_audit:
                    logging.error(f"Failed to send new memo audit log: {e_audit}")
        else:
            logging.error(f"Failed to update memo for address ID {address_id_to_update}")
            await message.answer("Error: Could not save the memo details.")

        # Clear memo-specific state, but keep pending_addresses
        await state.set_state(None) # Or a general "processing_complete_for_item" state
        await state.update_data(current_address_for_memo_id=None, 
                                current_address_for_memo_text=None,
                                current_address_for_memo_blockchain=None,
                                intended_memo_type=None)


        if pending_addresses:
            await _prompt_for_next_memo(message, state, pending_addresses)
        else:
            await message.answer("All addresses processed. You can send new messages.")
            await state.clear()
            
    except Exception as e:
        logging.exception("Error in _process_memo_action: %s", e)
        await message.reply("An error occurred while saving the memo.")
        await state.clear() # Clear state on unexpected error
    finally:
        if db.is_active:
            db.close()


async def _skip_memo_action(message: Message, state: FSMContext): # Or CallbackQuery
    data = await state.get_data()
    address_text_for_display = data.get("current_address_for_memo_text", "the current address")
    pending_addresses = data.get("pending_addresses_for_memo", [])

    # Determine if called from Message or CallbackQuery
    reply_target = message if isinstance(message, Message) else message.message

    await reply_target.answer(
        f"Skipped memo for <code>{html.quote(address_text_for_display)}</code>.", parse_mode="HTML"
    )
    
    # Clear memo-specific state
    await state.set_state(None)
    await state.update_data(current_address_for_memo_id=None, 
                            current_address_for_memo_text=None,
                            current_address_for_memo_blockchain=None,
                            intended_memo_type=None)

    if pending_addresses:
        await _prompt_for_next_memo(reply_target, state, pending_addresses)
    else:
        await reply_target.answer("All addresses processed. You can send new messages.")
        await state.clear()