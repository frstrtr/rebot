"""
action_prompt.py
Handles sending the action prompt to the user for an identified crypto address.
"""
import logging
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_or_create_user, CryptoAddress
from database.models import MemoType
from .common import EXPLORER_CONFIG

async def _send_action_prompt(
    target_message: Message,
    address: str,
    blockchain: str,
    state: FSMContext, # state is passed and will now be used to set context
    db: Session,
    acting_telegram_user_id: int,
    edit_message: bool = False,
):
    """Sends a message with action buttons for an identified address."""
    
    # Ensure the FSM state has the current address and blockchain for the action prompt's context
    await state.update_data(
        current_action_address=address,
        current_action_blockchain=blockchain,
        # Preserve other relevant state data if necessary, for example:
        # addresses_for_memo_prompt_details=data.get("addresses_for_memo_prompt_details", []), 
        # current_scan_db_message_id=data.get("current_scan_db_message_id")
        # Be careful not to overwrite essential data if this function is called in various contexts.
        # For now, focusing on setting the action address/blockchain.
    )
    
    prompt_text = (
        f"[_send_action_prompt] Address <code>{html.quote(address)}</code> identified for <b>{html.quote(blockchain.capitalize())}</b>.\n"
        "What would you like to do?"
    )

    explorer_button = None
    if blockchain.lower() in EXPLORER_CONFIG:
        config_data = EXPLORER_CONFIG[blockchain.lower()]
        explorer_name = config_data["name"]
        url = config_data["url_template"].format(address=address)
        explorer_button = InlineKeyboardButton(
            text=f"🔎 View on {explorer_name}",
            url=url,
        )

    public_memo_count = 0
    try:
        public_memo_count = (
            db.query(func.count(CryptoAddress.id)) # pylint: disable=not-callable
            .filter(
                func.lower(CryptoAddress.address) == address.lower(),
                func.lower(CryptoAddress.blockchain) == blockchain.lower(),
                CryptoAddress.notes.isnot(None),
                CryptoAddress.notes != "",
                or_(
                    CryptoAddress.memo_type == MemoType.PUBLIC.value,
                    CryptoAddress.memo_type.is_(None)
                )
            )
            .scalar()
        ) or 0
    except Exception as e:
        logging.error(f"Error counting public memos for action prompt button: {e}") # pylint: disable=logging-fstring-interpolation

    show_public_memos_button_text = "📜 Show Public Memos"
    if public_memo_count > 0:
        show_public_memos_button_text += f" ({public_memo_count})"
    
    show_public_memos_button = InlineKeyboardButton(
        text=show_public_memos_button_text,
        callback_data="show_public_memos" # Callback data for your handler
    )

    add_public_memo_button = InlineKeyboardButton(
        text="✍️ Add Public Memo",
        callback_data="request_memo:public" # Callback data for your handler
    )

    internal_user_db_id = None
    if acting_telegram_user_id:
        # Create a temporary User object for get_or_create_user
        temp_user_for_id_lookup = types.User(id=acting_telegram_user_id, is_bot=False, first_name="TempUser")
        db_user = get_or_create_user(db, temp_user_for_id_lookup)
        if db_user:
            internal_user_db_id = db_user.id

    private_memo_count = 0
    if internal_user_db_id:
        try:
            private_memo_count = (
                db.query(func.count(CryptoAddress.id)) # pylint: disable=not-callable
                .filter(
                    func.lower(CryptoAddress.address) == address.lower(),
                    func.lower(CryptoAddress.blockchain) == blockchain.lower(),
                    CryptoAddress.notes.isnot(None),
                    CryptoAddress.notes != "",
                    CryptoAddress.memo_type == MemoType.PRIVATE.value,
                    CryptoAddress.memo_added_by_user_id == internal_user_db_id,
                )
                .scalar()
            ) or 0
        except Exception as e:
            logging.error(f"Error counting private memos for action prompt button: {e}") # pylint: disable=logging-fstring-interpolation


    show_private_memos_button_text = "🔒 Show My Private Memos"
    if private_memo_count > 0:
        show_private_memos_button_text += f" ({private_memo_count})"
    
    show_private_memos_button = InlineKeyboardButton(
        text=show_private_memos_button_text,
        callback_data="show_private_memos" # Callback data for your handler
    )

    add_private_memo_button = InlineKeyboardButton(
        text="✍️ Add Private Memo",
        callback_data="request_memo:private" # Callback data for your handler
    )

    update_report_button = None
    ai_scam_check_button = None # New button
    if blockchain.lower() == "tron":
        update_report_button = InlineKeyboardButton(
            text="📊 Get TRC20 Report",
            callback_data="update_report_tronscan" # No address needed, get from FSM
        )
        ai_scam_check_button = InlineKeyboardButton( # New button definition
            text="🤖 AI Scam Check (TRC20)",
            callback_data="ai_scam_check_tron" # Callback data for the new handler
        )

    skip_address_button = InlineKeyboardButton(
        text="⏭️ Skip Address",
        callback_data="skip_address_action_stage" # Callback data for your handler
    )

    keyboard_layout = [
        [show_public_memos_button, show_private_memos_button],
        [add_public_memo_button, add_private_memo_button],
    ]
    
    if blockchain.lower() == "tron":
        # TRON-specific layout
        third_row_tron = []
        if update_report_button:
            third_row_tron.append(update_report_button)
        if ai_scam_check_button:
            third_row_tron.append(ai_scam_check_button)
        
        if third_row_tron: # Should always be true if tron, as buttons are defined
            keyboard_layout.append(third_row_tron)

        fourth_row_tron = []
        if explorer_button: # This will be "View on TronScan"
            fourth_row_tron.append(explorer_button)
        fourth_row_tron.append(skip_address_button)
        keyboard_layout.append(fourth_row_tron)
    else:
        # Generic layout for other blockchains
        third_row_generic = []
        if explorer_button:
            third_row_generic.append(explorer_button)
        third_row_generic.append(skip_address_button) # Always add skip button
        
        if third_row_generic: # Should always be true as skip is always there
            keyboard_layout.append(third_row_generic)


    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

    try:
        if edit_message:
            await target_message.edit_text(
                text=prompt_text, parse_mode="HTML", reply_markup=reply_markup
            )
        else:
            await target_message.answer(
                text=prompt_text, parse_mode="HTML", reply_markup=reply_markup
            )
    except TelegramAPIError as e:
        logging.warning(f"Failed to send/edit action prompt, API error: {e}") # pylint: disable=logging-fstring-interpolation
        # Fallback for edit failure
        if edit_message:
            await target_message.answer(
                text=f"[_send_action_prompt] (fallback) {prompt_text}", parse_mode="HTML", reply_markup=reply_markup
            )