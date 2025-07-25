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
from sqlalchemy.exc import SQLAlchemyError

from database import get_or_create_user, CryptoAddress
from database.models import MemoType
from .common import EXPLORER_CONFIG  # , ADMINS
from .helpers import _create_bot_deeplink_html  # MODIFIED: Import the helper function

# pylint: disable=logging-fstring-interpolation

async def _send_action_prompt(
    target_message: Message,
    address: str,
    blockchain: str,
    state: FSMContext,  # state is passed and will now be used to set context
    db: Session,
    acting_telegram_user_id: int,
    edit_message: bool = False,
):
    """Sends a message with action buttons for an identified address."""

    # Ensure the FSM state has the current address and blockchain for the action prompt's context
    # Also preserve current_scan_db_message_id if it exists in the current state data
    current_state_data = await state.get_data()
    update_payload = {
        "current_action_address": address,
        "current_action_blockchain": blockchain,
    }
    if "current_scan_db_message_id" in current_state_data:
        update_payload["current_scan_db_message_id"] = current_state_data.get(
            "current_scan_db_message_id"
        )

    await state.update_data(**update_payload)

    bot_info = await target_message.bot.get_me()
    bot_username = bot_info.username
    address_deeplink = _create_bot_deeplink_html(address, bot_username)

    # --- Fetch Risk Score from DB ---
    risk_score_html = ""
    try:
        address_record = (
            db.query(CryptoAddress)
            .filter(
                func.lower(CryptoAddress.address) == address.lower(),
                func.lower(CryptoAddress.blockchain) == blockchain.lower(),
            )
            .first()
        )

        if address_record and address_record.risk_score is not None:
            updated_at_str = address_record.updated_at.strftime("%Y-%m-%d %H:%M")
            risk_score_html = (
                f"<b>Risk Score:</b> {address_record.risk_score:.2f} "
                f"<i>(Updated: {updated_at_str} UTC)</i>\n"
            )
    except SQLAlchemyError as e:
        logging.error(f"DB Error fetching risk score for action prompt: {e}")

    prompt_text = (
        f"<b>Address:</b> <code>{address}</code>\n"
        f"<b>Blockchain:</b> {html.quote(blockchain.capitalize())}\n"
        f"{risk_score_html}"
        f"----------------------------------------\n"
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
            db.query(func.count(CryptoAddress.id))  # pylint: disable=not-callable
            .filter(
                func.lower(CryptoAddress.address) == address.lower(),
                func.lower(CryptoAddress.blockchain) == blockchain.lower(),
                CryptoAddress.notes.isnot(None),
                CryptoAddress.notes != "",
                or_(
                    CryptoAddress.memo_type == MemoType.PUBLIC.value,
                    CryptoAddress.memo_type.is_(None),
                ),
            )
            .scalar()
        ) or 0
    except SQLAlchemyError as e:
        logging.error(
            f"Error counting public memos for action prompt button: {e}"
        )  # pylint: disable=logging-fstring-interpolation

    show_public_memos_button_text = "📜 Show Public Memos"
    show_public_memos_button_text = "📜 Show Public Memos"
    if public_memo_count > 0:
        show_public_memos_button_text += f" ({public_memo_count})"

    show_public_memos_button = InlineKeyboardButton(
        text=show_public_memos_button_text,
        callback_data="show_public_memos",  # Callback data for your handler
    )

    add_public_memo_button = InlineKeyboardButton(
        text="✍️ Add Public Memo",
        callback_data="request_memo:public",  # Callback data for your handler
    )

    internal_user_db_id = None
    if acting_telegram_user_id:
        # Create a temporary User object for get_or_create_user
        temp_user_for_id_lookup = types.User(
            id=acting_telegram_user_id, is_bot=False, first_name="TempUser"
        )
        db_user = get_or_create_user(db, temp_user_for_id_lookup)
        if db_user:
            internal_user_db_id = db_user.id

    private_memo_count = 0
    if internal_user_db_id:
        try:
            private_memo_count = (
                db.query(func.count(CryptoAddress.id))  # pylint: disable=not-callable
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
        except SQLAlchemyError as e:
            logging.error(f"Error counting private memos for action prompt button: {e}")

    show_private_memos_button_text = "🔒 Show My Private Memos"
    if private_memo_count > 0:
        show_private_memos_button_text += f" ({private_memo_count})"

    show_private_memos_button = InlineKeyboardButton(
        text=show_private_memos_button_text,
        callback_data="show_private_memos",  # Callback data for your handler
    )

    add_private_memo_button = InlineKeyboardButton(
        text="✍️ Add Private Memo",
        callback_data="request_memo:private",  # Callback data for your handler
    )

    update_report_button = None
    ai_scam_check_button = None
    token_transfers_button = None  # New button
    ai_scam_check_evm_button = None  # New button

    # Check if the acting user is an admin XXX for the future, if needed
    # For now, we assume all users can see the buttons, but you can uncomment this if needed
    # acting_telegram_user_id = target_message.from_user.id
    # ADMINS is a list of Telegram user IDs who are admins
    # is_admin = acting_telegram_user_id in ADMINS

    if (
        blockchain.lower() == "tron"
    ):  # and is_admin: # XXX Show these buttons only for TRON and if user is admin
        update_report_button = InlineKeyboardButton(
            text="📊 Get TRC20 Report",
            callback_data="update_report_tronscan",  # No address needed, get from FSM
        )
        ai_scam_check_button = InlineKeyboardButton(  # New button definition
            text="🤖 AI Scam Check (TRC20)",
            callback_data="ai_scam_check_tron",  # Callback data for the new handler
        )
        watch_new_memo_button = InlineKeyboardButton(
            text="👀 Watch Memos", callback_data="watch_new_memo"
        )
        watch_blockchain_events_button = InlineKeyboardButton(
            text="🔔 Watch TXs", callback_data="watch_blockchain_events"
        )
    elif blockchain.lower() in [
        "ethereum",
        "bsc",
    ]:  # Conditional buttons for other EVM chains
        token_transfers_button = InlineKeyboardButton(
            text="📜 Token Transfers EVM",
            callback_data="show_token_transfers",  # MODIFIED
        )
        ai_scam_check_evm_button = InlineKeyboardButton(
            text="🤖 AI Scam Check EVM", callback_data="ai_scam_check_evm"  # MODIFIED
        )

    skip_address_button = InlineKeyboardButton(
        text="⏭️ Skip Address", callback_data="skip_address_action_stage"  # MODIFIED
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

        if third_row_tron:  # Should always be true if tron, as buttons are defined
            keyboard_layout.append(third_row_tron)

        # Add new buttons before explorer and skip
        fourth_row_tron = []
        if watch_blockchain_events_button:  # Watch for new transactions/transfers
            fourth_row_tron.append(watch_blockchain_events_button)
        fourth_row_tron.append(watch_new_memo_button)
        keyboard_layout.append(fourth_row_tron)

        fifth_row_tron = []
        if explorer_button:  # This will be "View on TronScan"
            fifth_row_tron.append(explorer_button)
        fifth_row_tron.append(skip_address_button)
        keyboard_layout.append(fifth_row_tron)

    else:
        # Generic layout for other blockchains (including Ethereum, BSC)
        third_row_other_evm = []
        if token_transfers_button:
            third_row_other_evm.append(token_transfers_button)
        if ai_scam_check_evm_button:
            third_row_other_evm.append(ai_scam_check_evm_button)

        if third_row_other_evm:
            keyboard_layout.append(third_row_other_evm)

        fourth_row_generic = []
        if explorer_button:
            fourth_row_generic.append(explorer_button)
        fourth_row_generic.append(skip_address_button)  # Always add skip button

        if fourth_row_generic:  # Should always be true as skip is always there
            keyboard_layout.append(fourth_row_generic)

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_layout)

    try:
        if edit_message:
            await target_message.edit_text(
                text=prompt_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        else:
            await target_message.answer(
                text=prompt_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
    except TelegramAPIError as e:
        logging.warning(f"Failed to send/edit action prompt, API error: {e}")
        # Fallback for edit failure
        if edit_message:
            # Construct fallback text ensuring deeplink is used if possible
            fallback_prompt_text = (
                f"[_send_action_prompt] (fallback) Address {address_deeplink} identified for <b>{html.quote(blockchain.capitalize())}</b>.\n"
                "What would you like to do?"
            )
            await target_message.answer(
                text=fallback_prompt_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
