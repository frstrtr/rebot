"""
This module contains command handlers for the Telegram bot,
including the /start and /checkmemo commands.
"""

import logging
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandObject
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal, CryptoAddress, CryptoAddressStatus
from database.models import MemoType
from .common import (
    crypto_finder,
    TARGET_AUDIT_CHANNEL_ID,
    EXPLORER_CONFIG,
    MAX_TELEGRAM_MESSAGE_LENGTH,
)
from .address_processing import _scan_message_for_addresses_action
from .helpers import _create_bot_deeplink_html, format_user_info_for_audit, markdown_to_html


async def handle_report_deeplink(message: types.Message, report_id: int):
    """Handles a deeplink to a specific report (memo)."""
    db = SessionLocal()
    try:
        # Fetch the specific memo by its ID
        report_memo = db.query(CryptoAddress).filter(CryptoAddress.id == report_id).first()

        if not report_memo:
            await message.answer("Sorry, the requested report could not be found.")
            return

        # Security/Sanity check: only allow access to public memos via this link
        if report_memo.memo_type not in [MemoType.PUBLIC.value, None]:
             await message.answer("Sorry, you do not have permission to view this report.")
             return
        
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username
        address_deeplink = _create_bot_deeplink_html(report_memo.address, bot_username)

        response_header = (
            f"📜 <b>Public Report for Address:</b> {address_deeplink}\n"
            f"<b>Blockchain:</b> {html.quote(report_memo.blockchain.capitalize())}\n\n"
        )
        
        processed_notes = markdown_to_html(report_memo.notes if report_memo.notes else "")

        full_report_text = response_header + processed_notes
        
        if len(full_report_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
            trunc_suffix = "... (report truncated)"
            allowed_len = MAX_TELEGRAM_MESSAGE_LENGTH - len(trunc_suffix)
            full_report_text = full_report_text[:allowed_len] + trunc_suffix

        await message.answer(
            full_report_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        logging.exception(f"Error handling report deeplink for report_id {report_id}: {e}")
        await message.answer("An error occurred while fetching the report.")
    finally:
        if db.is_active:
            db.close()


async def command_start_handler(
    message: Message, command: CommandObject, state: FSMContext
) -> None:
    """
    Handles the /start command, initializing the bot interaction and processing any payload.
    If a payload is provided, it processes the address from the payload.
    If no payload is provided, it prompts the user to send a crypto address.
    """

    logging.info(
        "command_start_handler received /start from user %s.",
        message.from_user.id if message.from_user else "unknown",
    )
    await state.clear()
    user_full_name = message.from_user.full_name if message.from_user else "User"
    payload = command.args

    bot_info = await message.bot.get_me()
    bot_username = bot_info.username

    if message.from_user:
        user = message.from_user
        audit_header = "Audit: User started the bot with /start command"
        if payload:
            audit_header += f" and payload: <code>{html.quote(payload)}</code>"
        
        # Use the helper function to format user info, which includes the deeplinked ID
        formatted_user_info = format_user_info_for_audit(user)
        
        full_audit_message = f"{audit_header}\n{formatted_user_info}"

        try:
            await message.bot.send_message(
                chat_id=TARGET_AUDIT_CHANNEL_ID,
                text=full_audit_message, # MODIFIED
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logging.info(
                "/start command from user %s (payload: '%s') logged to audit channel.",
                user.id,
                payload or "None",
            )
        except TelegramAPIError as e:
            logging.error(
                "Failed to send /start audit info for user %s. Error: %s", user.id, e
            )

    if payload:
        # Handle report deeplink
        if payload.startswith("report_"):
            try:
                # Format: report_{report_id} or report_{report_id}_{address}
                # The address is for user context in the URL, only the ID is needed for lookup.
                parts = payload.split('_')
                if len(parts) < 2:
                    raise ValueError("Deeplink payload is too short")
                
                report_id_str = parts[1]
                report_id = int(report_id_str)
                await handle_report_deeplink(message, report_id)
                return # Stop further processing in start handler
            except (ValueError, IndexError):
                logging.warning(f"Invalid report deeplink payload: {payload}")
                await message.answer("Invalid report link.")
                return

        address_from_payload = payload.strip()
        logging.info(
            "Start command with payload (deep link) detected. Address: %s",
            address_from_payload,
        )
        address_deeplink = _create_bot_deeplink_html(address_from_payload, bot_username)
        await message.answer(
            f"Hello, {html.bold(user_full_name)}!\nProcessing address from link: {address_deeplink}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await _scan_message_for_addresses_action(
            message, state, text_override=address_from_payload
        )
    else:
        await message.answer(
            f"Hello, {html.bold(user_full_name)}! 👋\n\n"
            "Please send or forward 🤖me a message containing a 💸crypto address, and I'll help you with it. 🔍\n\n"
            "I'll provide a blockchain explorer ⛓️link, 📝memo book entries (public and private), "
            "and an 🤖AI analysis of the address's metadata in a multi-language report. 📈\n\n"
            "You can also use /checkmemo to see existing memos for an address. 📝\n"
            "If you'd like to skip the memo process, simply reply with /skip. ⏩"
        )


async def checkmemo_handler(message: types.Message):
    """"Handles the /checkmemo command to retrieve and display memos for a given crypto address.
    Expects the command in the format: /checkmemo <code>crypto_address</code>.
    If the address is valid, it queries the database for associated memos and displays them.
    If no memos are found, it informs the user.
    If the address is invalid or the command format is incorrect, it prompts the user with usage instructions.
    """

    logging.info("checkmemo_handler received command. Text: '%s'", message.text)
    if (
        not message.text
        or len(parts := message.text.strip().split(maxsplit=1)) < 2
        or not (address_arg := parts[1].strip())
    ):
        await message.reply(
            "Usage: /checkmemo <code>crypto_address</code>", parse_mode="HTML"
        )
        return

    db = SessionLocal()
    reply_markup_for_first_message = None
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    address_deeplink = _create_bot_deeplink_html(address_arg, bot_username)

    try:
        for blockchain_key, config_data in EXPLORER_CONFIG.items():
            if crypto_finder.validate_checksum(blockchain_key, address_arg):
                explorer_name = config_data["name"]
                url = config_data["url_template"].format(address=address_arg)
                button_text_addr = (
                    f"{address_arg[:6]}...{address_arg[-4:]}"
                    if len(address_arg) > 20
                    else address_arg
                )
                explorer_button = InlineKeyboardButton(
                    text=f"🔎 View {button_text_addr} on {explorer_name}", url=url
                )
                reply_markup_for_first_message = InlineKeyboardMarkup(
                    inline_keyboard=[[explorer_button]]
                )
                break
        results = (
            db.query(CryptoAddress)
            .filter(
                func.lower(CryptoAddress.address) == address_arg.lower(),
                CryptoAddress.notes.isnot(None),
                CryptoAddress.notes != "",
            )
            .order_by(CryptoAddress.blockchain, CryptoAddress.id)
            .all()
        )
        if not results:
            await message.reply(
                f"No memos found for address: {address_deeplink}",
                parse_mode="HTML",
                reply_markup=reply_markup_for_first_message,
                disable_web_page_preview=True
            )
            return

        response_header = (
            f"<b>Memos for Address:</b> {address_deeplink}\n\n"
        )
        memo_blocks = []
        for row in results:
            status_display = (
                row.status.value
                if isinstance(row.status, CryptoAddressStatus)
                else str(row.status or "N/A")
            )
            memo_blocks.append(
                f"<b>Blockchain:</b> {html.quote(row.blockchain.capitalize())}\n<b>Status:</b> {html.quote(status_display)}\n<b>Memo:</b> {html.quote(row.notes)}"
            )

        final_messages_to_send, active_message_parts, current_length = (
            [],
            [response_header],
            len(response_header),
        )
        for block_text in memo_blocks:
            needs_separator = (len(active_message_parts) > 1) or (
                len(active_message_parts) == 1
                and active_message_parts[0] != response_header
            )
            separator_len, block_len_val = (2 if needs_separator else 0), len(
                block_text
            )
            if (
                current_length + separator_len + block_len_val
                > MAX_TELEGRAM_MESSAGE_LENGTH
            ):
                if "".join(active_message_parts).strip():
                    final_messages_to_send.append("".join(active_message_parts))
                active_message_parts, current_length = [block_text], block_len_val
                if current_length > MAX_TELEGRAM_MESSAGE_LENGTH:
                    logging.warning(
                        "A single memo block for /checkmemo is too long (%s chars) and will be truncated.",
                        current_length,
                    )
                    trunc_suffix = "... (truncated)"
                    allowed_len = MAX_TELEGRAM_MESSAGE_LENGTH - len(trunc_suffix)
                    active_message_parts = [
                        (
                            block_text[:allowed_len] + trunc_suffix
                            if allowed_len > 0
                            else "Error: Memo content block too large."
                        )
                    ]
                    current_length = len(active_message_parts[0])
            else:
                if needs_separator:
                    active_message_parts.append("\n\n")
                    current_length += 2
                active_message_parts.append(block_text)
                current_length += block_len_val
        if (
            active_message_parts
            and "".join(active_message_parts).strip()
            and not (
                len(active_message_parts) == 1
                and active_message_parts[0] == response_header
                and not memo_blocks
            )
        ):
            final_messages_to_send.append("".join(active_message_parts))
        for i, text_to_send in enumerate(final_messages_to_send):
            if text_to_send.strip():
                await message.reply(
                    text=text_to_send,
                    parse_mode="HTML", # Added parse_mode
                    reply_markup=(reply_markup_for_first_message if i == 0 else None),
                    disable_web_page_preview=True
                )
    except (SQLAlchemyError, TelegramAPIError) as e:
        logging.exception(
            "Database or Telegram API error in checkmemo_handler for address %s: %s", html.quote(address_arg), e
        )
        await message.reply(
            text="An error occurred while retrieving memos. Please check the bot logs.",
            parse_mode="HTML" # Added parse_mode
        )
    finally:
        if db.is_active:
            db.close()
