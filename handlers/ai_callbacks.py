"""
ai_callbacks.py
Handles AI-related callbacks common to different blockchain analyses.
"""
import logging
from aiogram import html, types, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
import asyncio # Ensure asyncio is imported
from aiogram.exceptions import TelegramAPIError
from datetime import datetime
from sqlalchemy import func 
from sqlalchemy.orm import Session # Import Session

from genai import VertexAIClient
from config.config import Config
from database import SessionLocal, get_or_create_user, save_crypto_address
from database.models import MemoType, CryptoAddress, User # MODIFIED: Import User model
from database.queries import update_crypto_address_memo
from .common import MAX_TELEGRAM_MESSAGE_LENGTH, TARGET_AUDIT_CHANNEL_ID
from .states import AddressProcessingStates # For setting state if needed
from .helpers import ( # MODIFIED: Ensure process_ai_markdown_to_html_with_deeplinks is imported
    format_user_info_for_audit, 
    send_text_to_audit_channel, 
    markdown_to_html, # Keep if used directly elsewhere, though new func uses it internally
    send_typing_periodically,
    process_ai_markdown_to_html_with_deeplinks # New helper
)
from .address_processing import _orchestrate_next_processing_step
import asyncio # Ensure asyncio is imported

async def handle_ai_language_choice_callback(callback_query: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Handles AI report language selection and triggers AI analysis."""
    await callback_query.answer()
    chosen_lang_code = callback_query.data.split(":")[1]
    lang_map = {"en": "English", "ru": "Russian"}
    chosen_lang_name = lang_map.get(chosen_lang_code, "the selected language")

    user_fsm_data = await state.get_data()
    enriched_data_for_ai = user_fsm_data.get("ai_enriched_data", "") 
    address = user_fsm_data.get("current_action_address") 
    blockchain = user_fsm_data.get("current_action_blockchain", "N/A") 
    requesting_user = callback_query.from_user

    if not address: 
        logging.error("Missing address in FSM for AI language choice.")
        await callback_query.message.answer("Error: Missing address data for AI analysis. Please try again.")
        await state.set_state(None)
        return
    
    expert_memo_content_str = ""
    db: Session = SessionLocal() # type: ignore
    try:
        admin_telegram_ids = Config.ADMINS
        if not admin_telegram_ids:
            logging.info("No admin Telegram IDs configured in Config.ADMINS. Skipping fetch for admin expert memos.")
        else:
            # Fetch DB User objects for all configured admin Telegram IDs
            admin_db_users = db.query(User).filter(User.telegram_id.in_(admin_telegram_ids)).all() # MODIFIED
            admin_db_ids = [u.id for u in admin_db_users if u and u.id]

            logging.debug(
                f"AI Language Choice: Attempting to fetch expert memos from ADMINS. "
                f"Configured Admin Telegram IDs: {admin_telegram_ids}. "
                f"Found Admin DB IDs: {admin_db_ids}. "
                f"For Address: '{address}', Blockchain: '{blockchain}'"
            )

            if admin_db_ids:
                expert_memos = db.query(CryptoAddress).filter(
                    func.lower(CryptoAddress.address) == address.lower(),
                    func.lower(CryptoAddress.blockchain) == blockchain.lower(), 
                    CryptoAddress.memo_type == MemoType.PRIVATE.value,
                    CryptoAddress.memo_added_by_user_id.in_(admin_db_ids), # Fetch memos added by ANY of the admin DB IDs
                    func.lower(CryptoAddress.notes).like("expert%") 
                ).order_by(CryptoAddress.memo_updated_at.desc()).all()
                logging.debug(f"Found {len(expert_memos)} potential 'expert' memos from DB query for admin DB IDs {admin_db_ids}.")

                if expert_memos:
                    expert_notes_list = []
                    for i, memo in enumerate(expert_memos):
                        logging.debug(f"  Processing admin expert memo item {i+1}/{len(expert_memos)}, DB Memo ID: {memo.id}, Added by User DB ID: {memo.memo_added_by_user_id}, Notes (start): '{memo.notes[:100] if memo.notes else 'N/A'}...'")
                        if memo.notes:
                            expert_keyword_pos = memo.notes.lower().find("expert")
                            logging.debug(f"    Keyword 'expert' found at notes position: {expert_keyword_pos}")
                            
                            if expert_keyword_pos != -1:
                                content_after_expert = memo.notes[expert_keyword_pos + len("expert"):].lstrip(' :-').strip()
                                logging.debug(f"    Content after 'expert' (lstripped ' :-' and stripped): '{content_after_expert[:100]}...'")
                                if content_after_expert:
                                    expert_notes_list.append(content_after_expert)
                                    logging.debug(f"    Appended to expert_notes_list. Current list size: {len(expert_notes_list)}")
                                else:
                                    logging.debug(f"    Content after 'expert' is empty after stripping. Not appended.")
                            else:
                                logging.warning(f"    'expert' keyword not found in memo.notes via find(), though DB query `like 'expert%'` matched. Memo ID: {memo.id}. This is unexpected.")
                        else:
                            logging.debug(f"    Admin Memo ID: {memo.id} has no notes content. Skipped.")
                    
                    if expert_notes_list:
                        expert_memo_content_str = (
                            "Additional Administrator-Provided Observations (to be integrated into the overall analysis):\n" 
                            + "\n\n---\n".join(expert_notes_list) 
                            + "\n\n---\n\n"
                        )
                        logging.info(f"{len(expert_notes_list)} Admin-provided 'expert' memo piece(s) included for AI analysis of {address} (requested by user {requesting_user.id}). Total expert_memo_content_str length: {len(expert_memo_content_str)}")
                    else:
                        logging.info(f"No valid content extracted from {len(expert_memos)} potential admin 'expert' memos for address {address}.")
                else:
                    logging.info(f"No 'expert' memos found in DB that match all criteria for configured admin users, address {address}, blockchain {blockchain}.")
            else:
                logging.info("No admin users (with DB IDs) found in DB for the configured admin Telegram IDs. Cannot fetch admin expert memos.")
    except Exception as e_db:
        logging.error(f"Error fetching admin 'expert' private memos for {address}: {e_db}", exc_info=True)
    finally:
        if db.is_active:
            db.close()

    final_enriched_data = expert_memo_content_str + enriched_data_for_ai

    if not final_enriched_data.strip(): 
        logging.warning(f"No data (neither enriched nor expert) to send for AI analysis for address {address}.")
        await callback_query.message.edit_text(
            text=f"No data available to perform AI analysis for <code>{html.quote(address)}</code>. Please ensure there is information to analyze.",
            parse_mode="HTML",
            reply_markup=None
        )
        await state.set_state(None) 
        return

    await callback_query.message.edit_text(
        text=f"Got it! Preparing AI analysis in {chosen_lang_name} for <code>{html.quote(address)}</code> ({html.quote(blockchain.capitalize() if blockchain != 'N/A' else 'TRON')})... This may take a moment.",
        parse_mode="HTML",
        reply_markup=None
    )

    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(bot, callback_query.from_user.id, stop_typing_event)
    )

    final_html_report = "Error: AI analysis could not be performed."

    try:
        if not Config.VERTEX_AI_PROJECT_ID or not Config.VERTEX_AI_LOCATION or not Config.VERTEX_AI_MODEL_NAME:
            raise ValueError("Vertex AI Project ID, Location, or Model Name is not configured in Config.")
        
        vertex_ai_client = VertexAIClient() 

        prompt_template = (
            f"You are a cryptocurrency scam and risk analysis expert. "
            f"Analyze the following data for the address {html.quote(address)} on the {html.quote(blockchain.capitalize() if blockchain != 'N/A' else 'TRON')} blockchain. "
            f"Provide a concise risk assessment and identify any potential red flags or suspicious activities. "
            f"The user has requested the report in {chosen_lang_name}.\n\n"
            f"Data (this may include prior expert observations; integrate all provided information into your analysis):\n{final_enriched_data}\n\n"
            f"Based on ALL the provided data, please provide your analysis in {chosen_lang_name}, focusing on:\n"
            f"1. Overall risk level (e.g., Low, Medium, High, Very High, Suspicious).\n"
            f"2. Key observations and red flags (e.g., interactions with known scam addresses, unusual transaction patterns, token characteristics if applicable, lack of activity, etc.).\n"
            f"3. A brief summary conclusion.\n"
            f"Present the output clearly. Use Markdown for formatting (e.g. **bold**, *italic*, `code`, lists, tables if appropriate)."
        )
        
        generated_text_from_ai = await vertex_ai_client.generate_text(prompt_template) # This is Markdown

        if generated_text_from_ai:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            
            # Use the new helper function to convert AI's Markdown to HTML with deeplinks
            final_html_report = process_ai_markdown_to_html_with_deeplinks(generated_text_from_ai, bot_username)
        else:
            final_html_report = f"AI analysis did not return content for {html.quote(address)}. This could be due to safety filters or other issues."
            logging.warning(f"Vertex AI returned no content for address {address} on {blockchain if blockchain != 'N/A' else 'TRON'}.")

    except RuntimeError as e: 
        logging.error(f"VertexAIClient runtime error: {e}", exc_info=True)
        final_html_report = "Error: AI analysis client is not properly configured (library missing)."
    except ValueError as e: 
        logging.error(f"VertexAIClient configuration error: {e}", exc_info=True)
        final_html_report = f"Error: AI analysis client configuration is incomplete. Details: {html.quote(str(e))}"
    except Exception as e:
        logging.error(f"Error during Vertex AI call for {address} on {blockchain if blockchain != 'N/A' else 'TRON'}: {e}", exc_info=True)
        final_html_report = f"An unexpected error occurred during AI analysis for {html.quote(address)}."
    finally:
        stop_typing_event.set()
        try:
            await typing_task 
        except asyncio.CancelledError:
            logging.info(f"Typing task for chat {callback_query.from_user.id} was cancelled.")
        except Exception as e_task_await:
            logging.error(f"Error awaiting typing task for chat {callback_query.from_user.id}: {e_task_await}", exc_info=True)
    
    await state.update_data(ai_report_text=final_html_report)

    # --- Send AI Report to Audit Channel ---
    if TARGET_AUDIT_CHANNEL_ID:
        try:
            bot_info_for_audit = await bot.get_me()
            bot_username_for_audit = bot_info_for_audit.username

            address_deeplink_for_audit = f"<a href=\"https://t.me/{bot_username_for_audit}?start={html.quote(address)}\">{html.quote(address)}</a>"
            formatted_user_info_for_audit = format_user_info_for_audit(requesting_user)

            audit_report_header = (
                f"<b>🤖 AI Scam Analysis Report Generated</b>\n"
                f"<b>Address:</b> {address_deeplink_for_audit}\n"
                f"<b>Blockchain:</b> {html.quote(blockchain.capitalize() if blockchain != 'N/A' else 'TRON')}\n"
                f"<b>Requested by:</b> {formatted_user_info_for_audit}\n"
                f"------------------------------------\n"
            )
            full_audit_text = audit_report_header + final_html_report # final_html_report is already HTML

            if len(full_audit_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
                preview_text_slice = final_html_report[:MAX_TELEGRAM_MESSAGE_LENGTH - len(audit_report_header) - 150] # Ensure space for header and ellipsis
                audit_intro_text = (
                    audit_report_header +
                    "Report is too long. Full report attached as a file. First part of the report:\n" +
                    preview_text_slice + "..." # Removed html.quote() here
                )
                await send_text_to_audit_channel(bot, audit_intro_text, parse_mode="HTML")
                try:
                    report_file = BufferedInputFile(final_html_report.encode('utf-8'), filename=f"AI_Report_{address}_{blockchain if blockchain != 'N/A' else 'TRON'}.html")
                    await bot.send_document(TARGET_AUDIT_CHANNEL_ID, report_file, caption=f"Full AI Report for {html.quote(address)} on {html.quote(blockchain.capitalize() if blockchain != 'N/A' else 'TRON')}")
                except Exception as e_audit_file:
                    logging.error(f"Failed to send full AI report as file to audit channel: {e_audit_file}")
            else:
                await send_text_to_audit_channel(bot, full_audit_text, parse_mode="HTML")
        except Exception as e_audit_main:
            logging.error(f"Failed to send AI report to audit channel: {e_audit_main}", exc_info=True)
    # --- End Send AI Report to Audit Channel ---

    # Send the report using HTML parse mode
    if len(final_html_report) > MAX_TELEGRAM_MESSAGE_LENGTH:
        parts = []
        current_pos = 0
        while current_pos < len(final_html_report):
            split_at = current_pos + MAX_TELEGRAM_MESSAGE_LENGTH
            if split_at < len(final_html_report):
                last_newline = final_html_report.rfind('\n', current_pos, split_at)
                if last_newline != -1 and last_newline > current_pos:
                    split_at = last_newline + 1 
                # else, split at MAX_TELEGRAM_MESSAGE_LENGTH
            
            parts.append(final_html_report[current_pos:split_at])
            current_pos = split_at
            
        for part_idx, part_content in enumerate(parts):
            try:
                await callback_query.message.answer(
                    f"<b>AI Report (Part {part_idx + 1}/{len(parts)}):</b>\n{part_content}", 
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )
            except TelegramAPIError as e_split: 
                logging.error(f"Error sending AI report part with HTML: {e_split}. Falling back to no parse_mode for this part.")
                await callback_query.message.answer(f"AI Report (Part {part_idx + 1}/{len(parts)} - display error, raw content):\n{part_content}")
    else:
        try:
            await callback_query.message.answer(
                final_html_report, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
        except TelegramAPIError as e_html:
            logging.error(f"Error sending AI report with HTML: {e_html}. Falling back to no parse_mode.")
            await callback_query.message.answer(final_html_report) # Send raw if HTML fails

    memo_action_buttons = [
        [
            InlineKeyboardButton(text="💾 Save as Public Memo", callback_data="ai_memo_action:public"),
            InlineKeyboardButton(text="🔐 Save as Private Memo", callback_data="ai_memo_action:private"),
        ],
        [InlineKeyboardButton(text="⏩ Skip Saving Memo", callback_data="ai_memo_action:skip")]
    ]
    reply_markup_memo_actions = InlineKeyboardMarkup(inline_keyboard=memo_action_buttons)
    await callback_query.message.answer(
        f"What would you like to do with this AI report for <code>{html.quote(address)}</code>?",
        reply_markup=reply_markup_memo_actions, parse_mode="HTML"
    )
    await state.set_state(None)


async def handle_ai_response_memo_action_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Handles user's choice to save or skip saving the AI-generated report as a memo."""
    await callback_query.answer()
    action = callback_query.data.split(":")[1] 

    user_fsm_data = await state.get_data()
    ai_report_text = user_fsm_data.get("ai_report_text") 
    address_to_update = user_fsm_data.get("current_action_address")
    blockchain_for_update = user_fsm_data.get("current_action_blockchain", "tron") 
    current_scan_db_message_id = user_fsm_data.get("current_scan_db_message_id")
    # requesting_user = callback_query.from_user # No longer needed here for report audit

    if not ai_report_text or not address_to_update: 
        logging.error("Missing AI report text or address context for saving memo.")
        await callback_query.message.answer("Error: Could not process memo action due to missing context.")
        return

    # The following audit log section for the report content is now removed.
    # bot_info = await callback_query.bot.get_me()
    # bot_username = bot_info.username
    # address_deeplink = f"<a href=\"https://t.me/{bot_username}?start={html.quote(address_to_update)}\">{html.quote(address_to_update)}</a>"
    # formatted_user_info = format_user_info_for_audit(requesting_user)
    # audit_report_header = (
    #     f"<b>🤖 AI Scam Analysis Report</b>\n"
    #     f"<b>Address:</b> {address_deeplink}\n"
    #     f"<b>Blockchain:</b> {html.quote(blockchain_for_update.capitalize())}\n"
    #     f"<b>Requested by:</b> {formatted_user_info}\n"
    #     f"------------------------------------\n"
    # )
    # full_audit_text = audit_report_header + ai_report_text
    # if len(full_audit_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
    #     # ... (logic for sending file)
    # else:
    #     await send_text_to_audit_channel(callback_query.bot, full_audit_text, parse_mode="HTML")

    if action == "skip":
        await callback_query.message.edit_text(
            f"AI report for <code>{html.quote(address_to_update)}</code> was not saved. Logged to audit.",
            parse_mode="HTML", reply_markup=None
        )
        # Optionally, send a simpler audit message about the skip action
        if TARGET_AUDIT_CHANNEL_ID:
            user_info_for_skip_audit = format_user_info_for_audit(callback_query.from_user)
            skip_audit_text = (
                f"📝 <b>AI Memo Action: Skipped</b>\n"
                f"<b>Address:</b> <code>{html.quote(address_to_update)}</code>\n"
                f"<b>Blockchain:</b> {html.quote(blockchain_for_update.capitalize())}\n"
                f"<b>Action by:</b> {user_info_for_skip_audit}"
            )
            await send_text_to_audit_channel(callback_query.bot, skip_audit_text, parse_mode="HTML")
    else: 
        memo_type_to_save = MemoType.PUBLIC.value if action == "public" else MemoType.PRIVATE.value
        db = SessionLocal()
        try:
            db_crypto_address = save_crypto_address(db, current_scan_db_message_id, address_to_update, blockchain_for_update)
            if not db_crypto_address or db_crypto_address.id is None:
                logging.error(f"Failed to save/retrieve address {address_to_update} on {blockchain_for_update} for AI memo.")
                await callback_query.message.answer("Error: Could not save address to DB for memo.")
                db.close()
                return

            # Get user ID for memo_added_by_user_id for both public and private AI memos
            memo_user_db_id = None
            db_user = get_or_create_user(db, callback_query.from_user)
            if db_user:
                memo_user_db_id = db_user.id
            
            if not memo_user_db_id: # If user could not be identified in DB
                logging.error(f"Cannot save AI memo for {address_to_update}: User ID for {callback_query.from_user.id} could not be retrieved/created in DB.")
                await callback_query.message.answer("Error: Could not identify your user account. AI Memo not saved.")
                db.close()
                return

            # Specific check if it's a private memo and user ID failed (should be caught above, but as a safeguard)
            if memo_type_to_save == MemoType.PRIVATE.value and not memo_user_db_id:
                logging.warning(f"Cannot save private AI memo for {address_to_update}: user ID failed despite earlier check.")
                await callback_query.message.answer("Error: Could not ID user for private memo. Not saved as private.")
                db.close()
                return

            ai_memo_prefix = f"[AI Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n"
            final_memo_text = ai_memo_prefix + ai_report_text
            updated_address = update_crypto_address_memo(
                db=db, address_id=db_crypto_address.id, notes=final_memo_text,
                memo_type=memo_type_to_save, user_id=memo_user_db_id # Pass the user_id here
            )
            if updated_address:
                await callback_query.message.edit_text(
                    f"✅ AI report for <code>{html.quote(address_to_update)}</code> saved as {action} memo.",
                    parse_mode="HTML", reply_markup=None
                )
                # Optionally, send a simpler audit message about the save action
                if TARGET_AUDIT_CHANNEL_ID:
                    user_info_for_save_audit = format_user_info_for_audit(callback_query.from_user)
                    save_audit_text = (
                        f"💾 <b>AI Memo Action: Saved as {action.capitalize()}</b>\n"
                        f"<b>Address:</b> <code>{html.quote(address_to_update)}</code>\n"
                        f"<b>Blockchain:</b> {html.quote(blockchain_for_update.capitalize())}\n"
                        f"<b>Action by:</b> {user_info_for_save_audit}"
                    )
                    await send_text_to_audit_channel(callback_query.bot, save_audit_text, parse_mode="HTML")
            else:
                logging.error(f"Failed to update AI memo for address ID {db_crypto_address.id}")
                await callback_query.message.answer("Error: Could not save AI report as memo.")
        except Exception as e:
            logging.error(f"Error saving AI memo for {address_to_update}: {e}", exc_info=True)
            await callback_query.message.answer("Unexpected error saving AI memo.")
        finally:
            if db.is_active: db.close()

    await state.update_data(
        ai_enriched_data=None, ai_report_text=None, addresses_for_memo_prompt_details=[]
    )
    await _orchestrate_next_processing_step(callback_query.message, state)
