"""
ai_callbacks.py
Handles AI-related callbacks common to different blockchain analyses.
"""
import logging
from aiogram import html, types, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from datetime import datetime

from genai import VertexAIClient
from config.config import Config
from database import SessionLocal, get_or_create_user, save_crypto_address
from database.models import MemoType
from database.queries import update_crypto_address_memo
from .common import MAX_TELEGRAM_MESSAGE_LENGTH, TARGET_AUDIT_CHANNEL_ID
from .states import AddressProcessingStates # For setting state if needed
# Ensure markdown_to_html is imported from helpers
from .helpers import format_user_info_for_audit, send_text_to_audit_channel, replace_addresses_with_deeplinks, markdown_to_html 
from .address_processing import _orchestrate_next_processing_step


async def handle_ai_language_choice_callback(callback_query: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot parameter
    """Handles AI report language selection and triggers AI analysis."""
    await callback_query.answer()
    chosen_lang_code = callback_query.data.split(":")[1]
    lang_map = {"en": "English", "ru": "Russian"}
    chosen_lang_name = lang_map.get(chosen_lang_code, "the selected language")

    user_fsm_data = await state.get_data()
    enriched_data_for_ai = user_fsm_data.get("ai_enriched_data")
    address = user_fsm_data.get("current_action_address") 
    blockchain = user_fsm_data.get("current_action_blockchain", "N/A") # EVM might set this, TRON implies it

    if not enriched_data_for_ai or not address:
        logging.error("Missing enriched_data_for_ai or address in FSM for AI language choice.")
        await callback_query.message.answer("Error: Missing data for AI analysis. Please try again.")
        await state.set_state(None)
        return

    await callback_query.message.edit_text(
        text=f"Got it! Preparing AI analysis in {chosen_lang_name} for <code>{html.quote(address)}</code> ({html.quote(blockchain.capitalize() if blockchain != 'N/A' else 'TRON')})... This may take a moment.",
        parse_mode="HTML",
        reply_markup=None
    )

    # Send "typing..." action as a progress indicator for the AI analysis
    try:
        await bot.send_chat_action(chat_id=callback_query.from_user.id, action="typing")
    except TelegramAPIError as e_chat_action:
        logging.warning(f"Could not send typing action due to Telegram API error: {e_chat_action}")

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
            f"Data:\n{enriched_data_for_ai}\n\n"
            f"Based on this data, please provide your analysis in {chosen_lang_name}, focusing on:\n"
            f"1. Overall risk level (e.g., Low, Medium, High, Very High, Suspicious).\n"
            f"2. Key observations and red flags (e.g., interactions with known scam addresses, unusual transaction patterns, token characteristics if applicable, lack of activity, etc.).\n"
            f"3. A brief summary conclusion.\n"
            # Instruct AI to use Markdown for formatting
            f"Present the output clearly. Use Markdown for formatting (e.g. **bold**, *italic*, `code`, lists, tables if appropriate)."
        )
        
        # generated_text_from_ai is expected to be Markdown
        generated_text_from_ai = await vertex_ai_client.generate_text(prompt_template)

        if generated_text_from_ai:
            # Get bot username for deeplinks
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            
            # Step 1: Insert HTML deeplinks into the AI's (Markdown) text
            text_with_html_deeplinks = replace_addresses_with_deeplinks(generated_text_from_ai, bot_username)
            
            # Step 2: Convert the Markdown (which now contains HTML deeplinks) to final HTML
            final_html_report = markdown_to_html(text_with_html_deeplinks)
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
    
    await state.update_data(ai_report_text=final_html_report) # final_html_report now contains the fully processed HTML

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
    # For TRON, blockchain might not be explicitly in FSM for this stage, default or derive.
    # For EVM, it should be there.
    blockchain_for_update = user_fsm_data.get("current_action_blockchain", "tron") # Default to tron if not specified
    current_scan_db_message_id = user_fsm_data.get("current_scan_db_message_id")

    if not ai_report_text or not address_to_update: # Blockchain can be defaulted for TRON
        logging.error("Missing AI report text or address context for saving memo.")
        await callback_query.message.answer("Error: Could not process memo action due to missing context.")
        return

    audit_report_header = (
        f"<b>🤖 AI Scam Analysis Report</b>\n"
        f"<b>Address:</b> <code>{html.quote(address_to_update)}</code>\n"
        f"<b>Blockchain:</b> {html.quote(blockchain_for_update.capitalize())}\n"
        f"<b>Requested by:</b> {format_user_info_for_audit(callback_query.from_user)}\n"
        f"------------------------------------\n"
    )
    full_audit_text = audit_report_header + html.quote(ai_report_text) 
    
    if len(full_audit_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
        audit_intro_text = audit_report_header + "Report is too long. See user chat/logs. First part:\n" + html.quote(ai_report_text[:MAX_TELEGRAM_MESSAGE_LENGTH - len(audit_report_header) - 100]) + "..."
        await send_text_to_audit_channel(callback_query.bot, audit_intro_text, parse_mode="HTML")
        try:
            report_file = BufferedInputFile(ai_report_text.encode('utf-8'), filename=f"AI_Report_{address_to_update}_{blockchain_for_update}.txt")
            await callback_query.bot.send_document(TARGET_AUDIT_CHANNEL_ID, report_file, caption=f"Full AI Report for {address_to_update}")
        except Exception as e_audit_file:
            logging.error(f"Failed to send full AI report as file to audit channel: {e_audit_file}")
    else:
        await send_text_to_audit_channel(callback_query.bot, full_audit_text, parse_mode="HTML")

    if action == "skip":
        await callback_query.message.edit_text(
            f"AI report for <code>{html.quote(address_to_update)}</code> was not saved. Logged to audit.",
            parse_mode="HTML", reply_markup=None
        )
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
            memo_user_db_id = None
            if memo_type_to_save == MemoType.PRIVATE.value:
                db_user = get_or_create_user(db, callback_query.from_user)
                if db_user: memo_user_db_id = db_user.id
                if not memo_user_db_id:
                    logging.warning(f"Cannot save private AI memo for {address_to_update}: user ID failed.")
                    await callback_query.message.answer("Error: Could not ID user for private memo. Not saved.")
                    db.close()
                    return
            ai_memo_prefix = f"[AI Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n"
            final_memo_text = ai_memo_prefix + ai_report_text
            updated_address = update_crypto_address_memo(
                db=db, address_id=db_crypto_address.id, notes=final_memo_text,
                memo_type=memo_type_to_save, user_id=memo_user_db_id
            )
            if updated_address:
                await callback_query.message.edit_text(
                    f"✅ AI report for <code>{html.quote(address_to_update)}</code> saved as {action} memo.",
                    parse_mode="HTML", reply_markup=None
                )
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
