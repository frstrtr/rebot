"""
ai_callbacks.py
Handles AI-related callbacks common to different blockchain analyses.
"""
import logging
from aiogram import html, types
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
from .helpers import manual_escape_markdown_v2, format_user_info_for_audit, send_text_to_audit_channel
from .address_processing import _orchestrate_next_processing_step


async def handle_ai_language_choice_callback(callback_query: types.CallbackQuery, state: FSMContext):
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

    ai_analysis_text = "Error: AI analysis could not be performed." 

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
            f"Present the output clearly. Use Markdown for formatting if it helps readability (bold for headers, bullet points for lists)."
        )
        
        generated_text_from_ai = await vertex_ai_client.generate_text(prompt_template)

        if generated_text_from_ai:
            ai_analysis_text = generated_text_from_ai
        else:
            ai_analysis_text = f"AI analysis did not return content for {html.quote(address)}. This could be due to safety filters or other issues."
            logging.warning(f"Vertex AI returned no content for address {address} on {blockchain if blockchain != 'N/A' else 'TRON'}.")

    except RuntimeError as e: 
        logging.error(f"VertexAIClient runtime error: {e}", exc_info=True)
        ai_analysis_text = "Error: AI analysis client is not properly configured (library missing)."
    except ValueError as e: 
        logging.error(f"VertexAIClient configuration error: {e}", exc_info=True)
        ai_analysis_text = f"Error: AI analysis client configuration is incomplete. Details: {html.quote(str(e))}"
    except Exception as e:
        logging.error(f"Error during Vertex AI call for {address} on {blockchain if blockchain != 'N/A' else 'TRON'}: {e}", exc_info=True)
        ai_analysis_text = f"An unexpected error occurred during AI analysis for {html.quote(address)}."
    
    await state.update_data(ai_report_text=ai_analysis_text)

    escaped_text_for_mdv2 = manual_escape_markdown_v2(ai_analysis_text)

    if len(escaped_text_for_mdv2) > MAX_TELEGRAM_MESSAGE_LENGTH:
        parts = []
        current_pos = 0
        while current_pos < len(escaped_text_for_mdv2):
            parts.append(escaped_text_for_mdv2[current_pos : current_pos + MAX_TELEGRAM_MESSAGE_LENGTH])
            current_pos += MAX_TELEGRAM_MESSAGE_LENGTH
        for part_idx, part_content in enumerate(parts):
            try:
                await callback_query.message.answer(
                    f"AI Report (Part {part_idx + 1}/{len(parts)}):\n{part_content}", parse_mode="MarkdownV2" )
            except TelegramAPIError as e_split: 
                logging.error(f"Error sending AI report part with MarkdownV2 (manual escape): {e_split}. Falling back to no parse_mode.")
                await callback_query.message.answer(f"AI Report (Part {part_idx + 1}/{len(parts)}):\n{part_content}")
    else:
        try:
            await callback_query.message.answer(escaped_text_for_mdv2, parse_mode="MarkdownV2")
        except TelegramAPIError as e_md:
            logging.error(f"Error sending AI report with MarkdownV2 (manual escape): {e_md}. Falling back to no parse_mode.")
            await callback_query.message.answer(ai_analysis_text)

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

# Register these handlers:
# from .ai_callbacks import handle_ai_language_choice_callback, handle_ai_response_memo_action_callback
# dp.callback_query.register(handle_ai_language_choice_callback, AddressProcessingStates.awaiting_ai_language_choice, F.data.startswith("ai_lang:"))
# dp.callback_query.register(handle_ai_response_memo_action_callback, F.data.startswith("ai_memo_action:"))
