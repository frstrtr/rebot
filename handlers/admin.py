"""
Admin-specific command and callback handlers for the bot.
"""

import logging
from aiogram import Bot, html, types
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import Session

from database import SessionLocal, get_or_create_user # MODIFIED: Added get_or_create_user
from database.models import CryptoAddress, MemoType # MODIFIED: Added MemoType
from config.config import Config
from .common import (
    TARGET_AUDIT_CHANNEL_ID,
)  # Uncomment if audit log for memo removal is needed


async def handle_admin_request_delete_memo_callback(
    callback_query: types.CallbackQuery, bot: Bot
):
    """Asks for confirmation before deleting a memo.
    Admins can delete any public memo or their own private memos.
    """
    await callback_query.answer()

    if callback_query.from_user.id not in Config.ADMINS:
        try:
            # Try to edit the original message if possible
            await callback_query.message.edit_text(
                "⚠️ This action is for admins only.", reply_markup=None, disable_web_page_preview=True
            )
        except TelegramAPIError:
            # If edit fails (e.g., message too old, or not the bot's own message), send a new one
            await callback_query.message.answer("⚠️ This action is for admins only.", disable_web_page_preview=True)
        return

    try:
        memo_id_to_request_delete = int(callback_query.data.split(":")[1])
    except (IndexError, ValueError):
        logging.warning(
            f"Invalid callback data for admin_request_delete_memo: {callback_query.data}"
        )
        await callback_query.message.edit_text(
            "Error: Invalid memo ID in callback.", reply_markup=None, disable_web_page_preview=True
        )
        return

    db: Session = SessionLocal()
    try:
        memo_item = (
            db.query(CryptoAddress)
            .filter(CryptoAddress.id == memo_id_to_request_delete)
            .first()
        )
        if not memo_item:
            await callback_query.message.edit_text(
                f"Error: Memo ID <code>{memo_id_to_request_delete}</code> not found.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            return

        # Authorization check
        admin_can_delete = False
        if memo_item.memo_type == MemoType.PUBLIC.value:
            admin_can_delete = True
        elif memo_item.memo_type == MemoType.PRIVATE.value:
            admin_db_user = get_or_create_user(db, callback_query.from_user)
            if admin_db_user and memo_item.memo_added_by_user_id == admin_db_user.id:
                admin_can_delete = True
        
        if not admin_can_delete:
            await callback_query.message.edit_text(
                f"⚠️ You are not authorized to delete this memo (ID: <code>{memo_item.id}</code>).\n"
                f"Admins can delete public memos or their own private memos.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            return

        confirmation_buttons = [
            [
                InlineKeyboardButton(
                    text=f"✅ Yes, Delete Memo {memo_item.id}",
                    callback_data=f"admin_confirm_delete_memo:{memo_item.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"admin_cancel_delete_memo:{memo_item.id}",
                ),
            ]
        ]
        confirmation_markup = InlineKeyboardMarkup(inline_keyboard=confirmation_buttons)

        # Preview of the memo to be deleted
        notes_preview = (
            (memo_item.notes[:100] + "...")
            if memo_item.notes and len(memo_item.notes) > 100
            else memo_item.notes
        )
        notes_preview_html = html.quote(notes_preview if notes_preview else "N/A")

        await callback_query.message.edit_text(
            f"⚠️ <b>Confirm Deletion</b> ⚠️\n\n"
            f"Are you sure you want to delete Memo ID <code>{memo_item.id}</code> "
            f"for address <code>{html.quote(memo_item.address)}</code> ({html.quote(memo_item.blockchain.capitalize() if memo_item.blockchain else 'N/A')})?\n\n"
            f"<i>Preview:</i>\n{notes_preview_html}",
            reply_markup=confirmation_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.exception(
            f"Error in handle_admin_request_delete_memo_callback for memo_id {memo_id_to_request_delete}: {e}"
        )
        await callback_query.message.edit_text(
            "An error occurred while preparing memo deletion confirmation.",
            reply_markup=None,
            disable_web_page_preview=True,
        )
    finally:
        if db.is_active:
            db.close()


async def handle_admin_confirm_delete_memo_callback(
    callback_query: types.CallbackQuery, bot: Bot
):
    """Handles admin confirmation to remove a specific memo.
    Admins can delete any public memo or their own private memos.
    """
    await callback_query.answer("Processing removal...")

    if callback_query.from_user.id not in Config.ADMINS:
        await callback_query.message.edit_text(
            "⚠️ This action is for admins only.", reply_markup=None, disable_web_page_preview=True
        )
        return

    try:
        memo_id_to_remove = int(callback_query.data.split(":")[1])
    except (IndexError, ValueError):
        logging.warning(
            f"Invalid callback data for admin_confirm_delete_memo: {callback_query.data}"
        )
        await callback_query.message.edit_text(
            "Error: Invalid memo ID in callback.", reply_markup=None, disable_web_page_preview=True
        )
        return

    db: Session = SessionLocal()
    try:
        memo_to_delete = (
            db.query(CryptoAddress)
            .filter(CryptoAddress.id == memo_id_to_remove)
            .first()
        )
        if not memo_to_delete:
            logging.warning(
                f"Admin {callback_query.from_user.id} tried to confirm removal of non-existent memo ID {memo_id_to_remove}."
            )
            await callback_query.message.edit_text(
                f"Error: Memo ID <code>{memo_id_to_remove}</code> not found or already removed.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            return

        # Authorization check
        admin_can_delete = False
        if memo_to_delete.memo_type == MemoType.PUBLIC.value:
            admin_can_delete = True
        elif memo_to_delete.memo_type == MemoType.PRIVATE.value:
            admin_db_user = get_or_create_user(db, callback_query.from_user)
            if admin_db_user and memo_to_delete.memo_added_by_user_id == admin_db_user.id:
                admin_can_delete = True
        
        if not admin_can_delete:
            await callback_query.message.edit_text(
                f"⚠️ You are not authorized to delete this memo (ID: <code>{memo_to_delete.id}</code>).\n"
                f"Admins can delete public memos or their own private memos.",
                parse_mode="HTML",
                reply_markup=None,
                disable_web_page_preview=True,
            )
            return

        # Proceed with deletion if authorized
        address_display = memo_to_delete.address
        blockchain_display = (
            memo_to_delete.blockchain.capitalize()
            if memo_to_delete.blockchain
            else "N/A"
        )
        notes_preview_for_audit = (
            (memo_to_delete.notes[:75] + "...")
            if memo_to_delete.notes and len(memo_to_delete.notes) > 75
            else memo_to_delete.notes
        )

        db.delete(memo_to_delete)
        db.commit()

        logging.info(
            f"Admin {callback_query.from_user.id} confirmed removal of memo ID {memo_id_to_remove} for address {address_display}."
        )

        final_message = (
            f"🗑️ Memo ID <code>{memo_id_to_remove}</code> for <code>{html.quote(address_display)}</code> "
            f"({html.quote(blockchain_display)}) has been <b>permanently removed</b> by admin."
        )
        await callback_query.message.edit_text(
            final_message, parse_mode="HTML", reply_markup=None, disable_web_page_preview=True
        )

        # Send to audit channel if configured
        if TARGET_AUDIT_CHANNEL_ID:
            user = callback_query.from_user
            user_info_parts = [f"ID: <code>{user.id}</code>"]
            name_parts = [
                html.quote(n) for n in [user.first_name, user.last_name] if n
            ]
            if name_parts:
                user_info_parts.append(f"Name: {' '.join(name_parts)}")
            if user.username:
                user_info_parts.append(f"Username: @{html.quote(user.username)}")
            user_info_audit_str = "\n".join(
                ["<b>👤 Admin Details:</b>"] + user_info_parts
            )

            audit_log_text = (
                f"🗑️ <b>Memo Deleted by Admin</b>\n"
                f"{user_info_audit_str}\n"
                f"<b>Memo ID:</b> {memo_id_to_remove}\n"
                f"<b>Address:</b> <code>{html.quote(address_display)}</code>\n"
                f"<b>Blockchain:</b> {html.quote(blockchain_display)}\n"
                f"<i>Original Memo (preview):</i> {html.quote(notes_preview_for_audit if notes_preview_for_audit else 'N/A')}"
            )
            try:
                await bot.send_message(
                    TARGET_AUDIT_CHANNEL_ID,
                    audit_log_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e_audit:
                logging.error(f"Failed to send memo removal audit log: {e_audit}")
    
    except Exception as e:
        logging.exception(
            f"Error in handle_admin_confirm_delete_memo_callback for memo_id {memo_id_to_remove}: {e}"
        )
        await callback_query.message.edit_text(
            "An error occurred while trying to remove the memo.", reply_markup=None, disable_web_page_preview=True
        )
    finally:
        if db.is_active:
            db.close()


async def handle_admin_cancel_delete_memo_callback(
    callback_query: types.CallbackQuery, bot: Bot
):
    """Handles admin cancellation of memo deletion."""
    await callback_query.answer()
    if callback_query.from_user.id not in Config.ADMINS:
        await callback_query.message.edit_text(
            "⚠️ This action is for admins only.", reply_markup=None, disable_web_page_preview=True
        )
        return

    try:
        memo_id_cancelled = int(callback_query.data.split(":")[1])
    except (IndexError, ValueError):  # Should not happen if callback data is correct
        logging.warning(
            f"Invalid callback data for admin_cancel_delete_memo: {callback_query.data}"
        )
        await callback_query.message.edit_text(
            "Error: Invalid memo ID in cancellation callback.", reply_markup=None, disable_web_page_preview=True
        )
        return

    await callback_query.message.edit_text(
        f"❌ Deletion of Memo ID <code>{memo_id_cancelled}</code> cancelled.",
        parse_mode="HTML",
        reply_markup=None,
        disable_web_page_preview=True,
    )
