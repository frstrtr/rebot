"""
address_scanning.py
Contains the core logic for scanning messages for crypto addresses.
"""
import logging
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

from database import SessionLocal, save_message
from .common import (
    crypto_finder,
    TARGET_AUDIT_CHANNEL_ID,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    EXPLORER_CONFIG,
)
from .helpers import get_ambiguity_group_members, _create_bot_deeplink_html # MODIFIED: Import _create_bot_deeplink_html
from utils.colors import Colors

# Import functions from other refactored modules
from .action_prompt import _send_action_prompt
from .orchestration import _orchestrate_next_processing_step


async def _scan_message_for_addresses_action(
    message: Message, state: FSMContext, text_override: str = None
):
    db = SessionLocal()
    saved_db_message_id = None
    try:
        db_message_instance = save_message(db, message)

        if db_message_instance is None or db_message_instance.id is None:
            logging.error("Failed to save message to database or get its ID.")
            await message.reply(
                "An error occurred while processing your message (DB save failed)."
            )
            db.close()
            return
        saved_db_message_id = db_message_instance.id
        
        text_to_scan = (text_override or message.text or message.caption or "").strip()
        if not text_to_scan:
            logging.debug(
                "Message ID %s (or override) has no text content to scan.",
                saved_db_message_id,
            )
            if text_override and not text_to_scan:
                await message.reply(
                    "The address from the link appears to be empty."
                )
            db.close()
            return

        logging.info(
            f"Scanning message ID %s. Text: '{Colors.GREEN}%s{Colors.RESET}'",
            saved_db_message_id,
            text_to_scan,
        )
        
        detected_raw_addresses_map = crypto_finder.find_addresses(text_to_scan)
        logging.debug("Detected map from crypto_finder: %s", detected_raw_addresses_map)

        if detected_raw_addresses_map:
            try:
                audit_addresses_parts = [
                    "<b>🔍 Detected Crypto Addresses in User Message:</b>"
                ]
                all_detected_pairs = []
                bot_info = await message.bot.get_me() # Get bot info for username
                bot_username = bot_info.username

                for blockchain, addresses_list in detected_raw_addresses_map.items():
                    if addresses_list:
                        # MODIFIED: Use _create_bot_deeplink_html for addresses in audit log
                        formatted_addresses_list = [
                            f"  • {_create_bot_deeplink_html(addr, bot_username)}" 
                            for addr in addresses_list
                        ]
                        all_detected_pairs.extend([(blockchain, addr) for addr in addresses_list])
                        audit_addresses_parts.append(
                            f"<b>{html.quote(blockchain.capitalize())}:</b>\n" + "\n".join(formatted_addresses_list)
                        )

                if len(audit_addresses_parts) > 1: # Found some addresses
                    audit_addresses_text = "\n\n".join(audit_addresses_parts)
                    audit_buttons_list = []
                    for blockchain_key, addr_str in all_detected_pairs:
                        if blockchain_key in EXPLORER_CONFIG:
                            config_data = EXPLORER_CONFIG[blockchain_key]
                            explorer_name = config_data["name"]
                            url = config_data["url_template"].format(address=addr_str)
                            button_text_addr = f"{addr_str[:6]}...{addr_str[-4:]}" if len(addr_str) > 20 else addr_str
                            audit_buttons_list.append(
                                [InlineKeyboardButton(text=f"🔎 View {button_text_addr} on {explorer_name}", url=url)]
                            )
                    reply_markup_for_audit = InlineKeyboardMarkup(inline_keyboard=audit_buttons_list) if audit_buttons_list else None
                    
                    await message.bot.send_message(
                        chat_id=TARGET_AUDIT_CHANNEL_ID,
                        text=audit_addresses_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup_for_audit,
                        disable_web_page_preview=True,
                    )
                    logging.info("Audit log for detected addresses sent to channel ID: %s", TARGET_AUDIT_CHANNEL_ID)
            except Exception as e:
                logging.error("Error sending audit log for detected addresses: %s", e, exc_info=True)


        if not detected_raw_addresses_map:
            logging.debug("No crypto addresses found in message ID %s.", saved_db_message_id)
            await message.reply(
                "No crypto addresses found in your message."
            )
            db.close()
            return

        await state.update_data(current_scan_db_message_id=saved_db_message_id)
        aggregated_detections = {}
        for bc, addr_list in detected_raw_addresses_map.items():
            for addr in addr_list:
                aggregated_detections.setdefault(addr, {"chains": set()})["chains"].add(bc)

        ordered_addr_keys = list(aggregated_detections.keys())
        if not ordered_addr_keys:
            logging.info("No processable addresses after aggregation in message ID %s.", saved_db_message_id)
            await message.reply("No processable crypto addresses found.")
            db.close()
            return

        addr_str_to_process = ordered_addr_keys[0]
        data_to_process = aggregated_detections[addr_str_to_process]

        if len(ordered_addr_keys) > 1:
            await message.reply(
                f"Found {len(ordered_addr_keys)} unique addresses. "
                f"Processing first: <code>{html.quote(addr_str_to_process)}</code>.\n"
                "Send others separately if needed."
            )

        pending_blockchain_clarification = []
        addresses_for_memo_prompt_details_fsm = []
        addresses_for_explorer_buttons = [] # For the summary message
        
        detected_chains_set = data_to_process["chains"]
        specific_chains_for_display = sorted([chain.capitalize() for chain in detected_chains_set if chain != "address"])
        potential_chains_display = ", ".join(specific_chains_for_display) or \
                                   ("Generic Address (type unknown)" if "address" in detected_chains_set else "Unknown")
        
        # Initial detection summary (optional, can be removed if too verbose)
        # await message.answer(
        #     f"🔍 Processing: <code>{html.quote(addr_str_to_process)}</code>\n   (Detected types: {potential_chains_display})",
        #     parse_mode="HTML"
        # )

        specific_chains = {chain for chain in detected_chains_set if chain != "address"}
        forced_clarification_options = None

        if len(specific_chains) == 1:
            single_detected_chain = list(specific_chains)[0]
            ambiguity_group_members = get_ambiguity_group_members(single_detected_chain)
            if ambiguity_group_members:
                forced_clarification_options = sorted(list(ambiguity_group_members))
                logging.info(
                    "Address %s detected as %s (ambiguous group). Forcing clarification: %s",
                    addr_str_to_process, single_detected_chain, forced_clarification_options,
                )

        if forced_clarification_options:
            pending_blockchain_clarification.append({
                "address": addr_str_to_process,
                "detected_on_options": forced_clarification_options,
            })
            await state.update_data(pending_blockchain_clarification=pending_blockchain_clarification)
        elif len(specific_chains) == 1: # Unambiguous single chain
            chosen_blockchain = list(specific_chains)[0]
            addresses_for_memo_prompt_details_fsm = [{"address": addr_str_to_process, "blockchain": chosen_blockchain}]
            await state.update_data(
                addresses_for_memo_prompt_details=addresses_for_memo_prompt_details_fsm,
                pending_blockchain_clarification=[]
            )
            await _send_action_prompt(
                message, addr_str_to_process, chosen_blockchain, state, db,
                acting_telegram_user_id=message.from_user.id
            )
            # No immediate orchestration needed; user interaction will drive next step via callbacks.
        else: # Multiple specific chains or only generic "address"
            options = sorted(list(specific_chains)) if specific_chains else ["Unknown"] # Should not be "Unknown" if specific_chains is empty and "address" was found
            if not specific_chains and "address" in detected_chains_set: # Only generic "address" type
                 # This case might need special handling, perhaps a different prompt or skip.
                 # For now, treat as needing clarification among "Unknown" or let user type.
                 # Or, if you have a list of common chains, present them.
                 # For simplicity, we'll let it go to clarification with "Unknown".
                 logging.info("Address %s is generic. Prompting for clarification with options: %s", addr_str_to_process, options)

            pending_blockchain_clarification.append({
                "address": addr_str_to_process,
                "detected_on_options": options if options else ["Unknown"], # Ensure options is not empty
            })
            await state.update_data(pending_blockchain_clarification=pending_blockchain_clarification)

        # If clarification is needed, orchestrate. Otherwise, action prompt was sent.
        if pending_blockchain_clarification:
            await _orchestrate_next_processing_step(message, state)
        # If unambiguous, the action prompt is shown, and we wait for user callback.

    except ValueError as ve:
        logging.error("ValueError in address scanning: %s", ve)
        await message.reply("Error processing message.")
    except Exception as e:
        logging.exception("Unexpected error in _scan_message_for_addresses_action: %s", e)
        await message.reply("Unexpected error.")
    finally:
        if db and db.is_active:
            db.close()