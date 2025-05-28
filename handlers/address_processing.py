"""
addrss_processing.py
Contains functions for processing crypto addresses in messages,
including scanning messages for addresses, handling blockchain clarifications,
and prompting for memos.
"""

import logging
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    save_message,
    save_crypto_address,
    CryptoAddress,
    CryptoAddressStatus,
)
from .common import (
    crypto_finder,
    TARGET_AUDIT_CHANNEL_ID,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    EXPLORER_CONFIG,
)
from .states import AddressProcessingStates
from .helpers import get_ambiguity_group_members


async def _display_memos_for_address_blockchain(
    message_target: types.Message, address: str, blockchain: str, db: Session
):
    existing_memos_specific = (
        db.query(CryptoAddress)
        .filter(
            func.lower(CryptoAddress.address) == address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower(),
            CryptoAddress.notes.isnot(None),
            CryptoAddress.notes != "",
        )
        .order_by(CryptoAddress.id)
        .all()
    )

    if not existing_memos_specific:
        await message_target.answer(
            f"ℹ️ No previous memos found for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())}.",
            parse_mode="HTML",
        )
        return

    list_header = f"📜 <b>Previous Memos for <code>{html.quote(address)}</code> on {html.quote(blockchain.capitalize())}:</b>"

    memo_item_lines = []
    for memo_item in existing_memos_specific:
        status_display = (
            memo_item.status.value
            if isinstance(memo_item.status, CryptoAddressStatus)
            else str(memo_item.status or "N/A")
        )
        memo_item_lines.append(
            f"  • (<i>{status_display}</i>): {html.quote(memo_item.notes)}"
        )

    final_messages_to_send = []
    active_message_parts = [list_header]
    current_length = len(list_header)

    for line_block in memo_item_lines:
        separator = "\n"
        separator_len = len(separator)
        block_len = len(line_block)

        if current_length + separator_len + block_len > MAX_TELEGRAM_MESSAGE_LENGTH:
            if "".join(active_message_parts).strip():
                final_messages_to_send.append("".join(active_message_parts))

            continuation_prefix = "  ↪ "
            active_message_parts = [continuation_prefix, line_block]
            current_length = len(continuation_prefix) + block_len

            if current_length > MAX_TELEGRAM_MESSAGE_LENGTH:
                logging.warning(
                    "A single memo line for %s on %s (with cont. prefix) is too long and will be truncated.",
                    address,
                    blockchain,
                )
                truncation_suffix = "... (truncated)"
                allowed_total_len = MAX_TELEGRAM_MESSAGE_LENGTH - len(truncation_suffix)
                allowed_line_block_len = allowed_total_len - len(continuation_prefix)
                if allowed_line_block_len < 0:
                    allowed_line_block_len = 0
                truncated_line_block = line_block[:allowed_line_block_len]
                active_message_parts = [
                    continuation_prefix,
                    truncated_line_block,
                    truncation_suffix,
                ]
                current_length = len("".join(active_message_parts))
        else:
            active_message_parts.append(separator)
            current_length += separator_len
            active_message_parts.append(line_block)
            current_length += block_len

    if active_message_parts and "".join(active_message_parts).strip():
        if not (
            len(active_message_parts) == 1
            and active_message_parts[0] == list_header
            and not memo_item_lines
        ):
            final_messages_to_send.append("".join(active_message_parts))
        elif memo_item_lines:
            final_messages_to_send.append("".join(active_message_parts))

    for text_to_send in final_messages_to_send:
        if text_to_send.strip():
            await message_target.answer(text_to_send, parse_mode="HTML")


async def _scan_message_for_addresses_action(
    message: Message, state: FSMContext, text_override: str = None
):
    db = SessionLocal()
    try:
        db_message = save_message(db, message)
        if db_message is None:
            logging.error("Failed to save message to database.")
            await message.reply(
                "An error occurred while processing your message (DB save failed)."
            )
            return

        text_to_scan = (text_override or message.text or message.caption or "").strip()
        if not text_to_scan:
            logging.debug(
                "Message ID %s (or override) has no text content to scan for addresses.",
                db_message.id,
            )
            if text_override and not text_to_scan:
                await message.reply(
                    "The address from the link appears to be empty. Please try again."
                )
            return

        detected_raw_addresses_map = crypto_finder.find_addresses(text_to_scan)
        logging.debug("Detected map from crypto_finder: %s", detected_raw_addresses_map)

        if detected_raw_addresses_map:
            try:
                audit_addresses_parts = [
                    "<b>🔍 Detected Crypto Addresses in User Message:</b>"
                ]
                all_detected_pairs = []
                for blockchain, addresses_list in detected_raw_addresses_map.items():
                    if addresses_list:
                        formatted_addresses_list = []
                        for addr in addresses_list:
                            formatted_addresses_list.append(
                                f"  • <code>{html.quote(addr)}</code>"
                            )
                            all_detected_pairs.append((blockchain, addr))
                        formatted_addresses_text = "\n".join(formatted_addresses_list)
                        audit_addresses_parts.append(
                            f"<b>{html.quote(blockchain.capitalize())}:</b>\n{formatted_addresses_text}"
                        )

                audit_addresses_text = "\n\n".join(audit_addresses_parts)
                reply_markup_for_audit = None
                audit_buttons_list = []
                for blockchain_key, addr_str in all_detected_pairs:
                    if blockchain_key in EXPLORER_CONFIG:
                        config_data = EXPLORER_CONFIG[blockchain_key]
                        explorer_name = config_data["name"]
                        url = config_data["url_template"].format(address=addr_str)
                        button_text_addr = addr_str
                        if len(addr_str) > 20:
                            button_text_addr = f"{addr_str[:6]}...{addr_str[-4:]}"
                        audit_buttons_list.append(
                            [
                                InlineKeyboardButton(
                                    text=f"🔎 View {button_text_addr} on {explorer_name}",
                                    url=url,
                                )
                            ]
                        )
                if audit_buttons_list:
                    reply_markup_for_audit = InlineKeyboardMarkup(
                        inline_keyboard=audit_buttons_list
                    )
                if len(audit_addresses_parts) > 1:
                    await message.bot.send_message(
                        chat_id=TARGET_AUDIT_CHANNEL_ID,
                        text=audit_addresses_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup_for_audit,
                    )
                    logging.info(
                        TARGET_AUDIT_CHANNEL_ID,
                    )
            except TelegramAPIError as e:
                logging.error(
                    "Failed to forward detected addresses to audit channel %s due to Telegram API error: %s",
                    TARGET_AUDIT_CHANNEL_ID,
                    e,
                )
            except Exception as e: # Catch other unexpected errors
                logging.error(
                    "An unexpected error occurred while trying to forward to audit channel %s. Error: %s",
                    TARGET_AUDIT_CHANNEL_ID,
                    e,
                )

        if not detected_raw_addresses_map:
            logging.debug("No crypto addresses found in message ID %s.", db_message.id)
            await message.reply(
                "No crypto addresses found in your message. Please send a message containing a crypto address."
            )
            return

        await state.update_data(current_scan_db_message_id=db_message.id)
        aggregated_detections = {}
        for bc, addr_list in detected_raw_addresses_map.items():
            for addr in addr_list:
                if addr not in aggregated_detections:
                    aggregated_detections[addr] = {"chains": set()}
                aggregated_detections[addr]["chains"].add(bc)

        ordered_addr_keys = list(aggregated_detections.keys())
        if not ordered_addr_keys:
            logging.info(
                "No processable addresses after aggregation in message ID %s.",
                db_message.id,
            )
            await message.reply(
                "No processable crypto addresses found in your message."
            )
            return

        addr_str_to_process = ordered_addr_keys[0]
        data_to_process = aggregated_detections[addr_str_to_process]

        if len(ordered_addr_keys) > 1:
            await message.reply(
                f"I found {len(ordered_addr_keys)} unique address strings in your message. "
                f"I will process the first one: <code>{html.quote(addr_str_to_process)}</code>.\n"
                "Please send other addresses in separate messages if needed."
            )

        (
            pending_blockchain_clarification,
            addresses_for_memo_prompt_details,
            addresses_for_explorer_buttons,
            detected_address_info_blocks,
        ) = ([], [], [], [])
        detected_chains_set = data_to_process["chains"]
        current_address_block_parts = []
        specific_chains_for_display = sorted(
            list(
                chain.capitalize()
                for chain in detected_chains_set
                if chain != "address"
            )
        )
        potential_chains_display = (
            ", ".join(specific_chains_for_display)
            if specific_chains_for_display
            else (
                "Generic Address (type unknown)"
                if "address" in detected_chains_set
                else "Unknown"
            )
        )
        current_address_block_parts.append(
            f"🔍 Processing: <code>{html.quote(addr_str_to_process)}</code>\n   (Detected types: {potential_chains_display})"
        )
        detected_address_info_blocks.append("\n".join(current_address_block_parts))

        specific_chains = {chain for chain in detected_chains_set if chain != "address"}
        forced_clarification_options = None
        if len(specific_chains) == 1:
            single_detected_chain = list(specific_chains)[0]
            ambiguity_group_members = get_ambiguity_group_members(single_detected_chain)
            if ambiguity_group_members:
                forced_clarification_options = sorted(list(ambiguity_group_members))
                logging.info(
                    "Address %s detected as %s, in ambiguous group. Forcing clarification: %s",
                    addr_str_to_process,
                    single_detected_chain,
                    forced_clarification_options,
                )

        if forced_clarification_options:
            pending_blockchain_clarification.append(
                {
                    "address": addr_str_to_process,
                    "detected_on_options": forced_clarification_options,
                }
            )
        elif len(specific_chains) == 1 and not forced_clarification_options:
            chosen_blockchain = list(specific_chains)[0]
            await _display_memos_for_address_blockchain(
                message, addr_str_to_process, chosen_blockchain, db
            )
            addresses_for_memo_prompt_details.append(
                {"address": addr_str_to_process, "blockchain": chosen_blockchain}
            )
            if chosen_blockchain in EXPLORER_CONFIG:
                addresses_for_explorer_buttons.append(
                    {"address": addr_str_to_process, "blockchain": chosen_blockchain}
                )
        else:
            options = sorted(list(specific_chains))
            pending_blockchain_clarification.append(
                {"address": addr_str_to_process, "detected_on_options": options}
            )

        if detected_address_info_blocks:
            initial_header_text = "<b>Address Detection:</b>\n\n"
            final_messages_to_send, active_message_parts, current_length = (
                [],
                [initial_header_text],
                len(initial_header_text),
            )
            for block_text in detected_address_info_blocks:
                needs_separator = active_message_parts and not (
                    len(active_message_parts) == 1
                    and active_message_parts[0] == initial_header_text
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
                            "A single address info block is too long (%s chars) and will be truncated.",
                            current_length,
                        )
                        trunc_suffix = "... (truncated)"
                        allowed_len = MAX_TELEGRAM_MESSAGE_LENGTH - len(trunc_suffix)
                        active_message_parts = [
                            (
                                block_text[:allowed_len] + trunc_suffix
                                if allowed_len > 0
                                else "Error: Content block too large."
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
                and (
                    not (
                        len(active_message_parts) == 1
                        and active_message_parts[0] == initial_header_text
                    )
                    or detected_address_info_blocks
                )
            ):
                final_messages_to_send.append("".join(active_message_parts))
            for text_to_send in final_messages_to_send:
                if text_to_send.strip():
                    await message.answer(text_to_send, parse_mode="HTML")

        if addresses_for_explorer_buttons:
            explorer_url_buttons_list = []
            for item in addresses_for_explorer_buttons:
                addr, blockchain_key = item["address"], item["blockchain"]
                if blockchain_key in EXPLORER_CONFIG:
                    config_data = EXPLORER_CONFIG[blockchain_key]
                    explorer_name, url = config_data["name"], config_data[
                        "url_template"
                    ].format(address=addr)
                    button_text_addr = (
                        f"{addr[:6]}...{addr[-4:]}" if len(addr) > 20 else addr
                    )
                    explorer_url_buttons_list.append(
                        [
                            InlineKeyboardButton(
                                text=f"🔎 View {button_text_addr} on {explorer_name}",
                                url=url,
                            )
                        ]
                    )
            if explorer_url_buttons_list:
                await message.answer(
                    "Direct links to blockchain explorers:",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=explorer_url_buttons_list
                    ),
                )

        await state.update_data(
            pending_blockchain_clarification=pending_blockchain_clarification,
            addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
        )
        await _orchestrate_next_processing_step(message, state)
    except ValueError as ve:
        logging.error("ValueError in address scanning: %s", ve)
        await message.reply("An error occurred while processing your message.")
    except Exception as e:
        logging.exception(
            "Unexpected error in _scan_message_for_addresses_action: %s", e
        )
        await message.reply("An unexpected error occurred.")
    finally:
        if db.is_active:
            db.close()


async def _orchestrate_next_processing_step(
    message_to_reply_to: Message, state: FSMContext
):
    data = await state.get_data()
    pending_blockchain_clarification = data.get("pending_blockchain_clarification", [])
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )
    current_scan_db_message_id = data.get("current_scan_db_message_id")

    if not current_scan_db_message_id:
        logging.error(
            "Cannot orchestrate: current_scan_db_message_id not found in FSM state."
        )
        await message_to_reply_to.answer(
            "An internal error occurred (missing message context). Please try scanning again."
        )
        await state.clear()
        return

    db = SessionLocal()
    try:
        if pending_blockchain_clarification:
            item_to_clarify = pending_blockchain_clarification.pop(0)
            await state.update_data(
                current_item_for_blockchain_clarification=item_to_clarify,
                pending_blockchain_clarification=pending_blockchain_clarification,
            )
            await _ask_for_blockchain_clarification(
                message_to_reply_to, item_to_clarify, state
            )
        elif addresses_for_memo_prompt_details:
            ready_for_memo_prompt_with_ids = []
            for detail in addresses_for_memo_prompt_details:
                addr_str, blockchain = detail["address"], detail["blockchain"]
                db_crypto_address = save_crypto_address(
                    db, current_scan_db_message_id, addr_str, blockchain
                )
                if db_crypto_address:
                    ready_for_memo_prompt_with_ids.append(
                        {
                            "id": db_crypto_address.id,
                            "address": addr_str,
                            "blockchain": blockchain,
                        }
                    )
                else:
                    logging.error(
                        "Failed to save address %s on %s during orchestration for memo prompt.",
                        addr_str,
                        blockchain,
                    )
            await state.update_data(addresses_for_memo_prompt_details=[])
            if ready_for_memo_prompt_with_ids:
                await _prompt_for_next_memo(
                    message_to_reply_to, state, ready_for_memo_prompt_with_ids
                )
            else:
                logging.info("No addresses successfully saved to prompt for memo.")
                remaining_clarifications = await state.get_data()  # Re-fetch to be sure
                if not remaining_clarifications.get(
                    "pending_blockchain_clarification"
                ):  # Check if any clarifications were re-added or still pending
                    await message_to_reply_to.answer("Finished processing addresses.")
                    await state.clear()
        else:
            logging.info(
                "Orchestration complete: No pending clarifications or memo prompts."
            )
            await message_to_reply_to.answer("All detected addresses processed.")
            await state.clear()
    finally:
        if db.is_active:
            db.close()


async def _ask_for_blockchain_clarification(
    message_to_reply_to: Message, item_to_clarify: dict, state: FSMContext
):
    address = item_to_clarify["address"]
    detected_options = item_to_clarify["detected_on_options"]
    keyboard_buttons_rows = []
    db = SessionLocal()
    try:
        if detected_options:
            current_row = []
            for i, option in enumerate(detected_options):
                memo_count = (
                    db.query(
                        func.count(CryptoAddress.id) # pylint: disable=not-callable
                    )  
                    .filter(
                        func.lower(CryptoAddress.address) == address.lower(),
                        func.lower(CryptoAddress.blockchain) == option.lower(),
                        CryptoAddress.notes.isnot(None),
                        CryptoAddress.notes != "",
                    )
                    .scalar()
                )
                button_text_parts = [option.capitalize()]
                if option.lower() in EXPLORER_CONFIG:
                    chain_config = EXPLORER_CONFIG[option.lower()]
                    token_standard = chain_config.get("token_standard_display")
                    if token_standard:
                        button_text_parts.append(f"({token_standard})")
                if memo_count > 0:
                    button_text_parts.append(
                        f"[{memo_count} memo{'s' if memo_count > 1 else ''}]"
                    )
                final_button_text = " ".join(button_text_parts)
                current_row.append(
                    InlineKeyboardButton(
                        text=f"⛓️ {final_button_text}",
                        callback_data=f"clarify_bc:chosen:{option.lower()}",
                    )
                )
                if len(current_row) == 2 or i == len(detected_options) - 1:
                    keyboard_buttons_rows.append(current_row)
                    current_row = []
    finally:
        if db.is_active:
            db.close()
    keyboard_buttons_rows.append(
        [
            InlineKeyboardButton(
                text="⏭️ Skip this address", callback_data="clarify_bc:skip"
            )
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons_rows)
    prompt_text = (
        f"For address: <code>{html.quote(address)}</code>\nWhich blockchain network does this address belong to?\nPlease select from the options below."
        if detected_options
        else f"For address: <code>{html.quote(address)}</code>\nI couldn't auto-detect specific blockchain networks for this address. If you know the network, you might need to send the address again, perhaps with more context. For now, you can choose to skip processing this address."
    )
    await message_to_reply_to.answer(
        prompt_text, reply_markup=keyboard, parse_mode="HTML"
    )
    await state.set_state(AddressProcessingStates.awaiting_blockchain)


async def _handle_blockchain_reply(message: Message, state: FSMContext):
    # This function is noted as potentially unused.
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")
    if not item_being_clarified:
        logging.info(
            "Received blockchain reply but no item_being_clarified in state. Ignoring."
        )
        return
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )
    chosen_blockchain = (message.text or "").strip().lower()
    if not chosen_blockchain:
        await message.reply(
            "Blockchain name cannot be empty. Please try again, or use /skip."
        )  # Adjusted skip command
        return
    addresses_for_memo_prompt_details.append(
        {"address": item_being_clarified["address"], "blockchain": chosen_blockchain}
    )
    await state.update_data(
        addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
        current_item_for_blockchain_clarification=None,
    )
    await message.reply(
        f"Noted: Address <code>{html.quote(item_being_clarified['address'])}</code> will be associated with <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
        parse_mode="HTML",
    )
    await _orchestrate_next_processing_step(message, state)


async def _prompt_for_next_memo(
    message_to_reply_to: Message, state: FSMContext, pending_list: list
):
    if not pending_list:
        # await message_to_reply_to.answer("All memos processed. You can send new messages with addresses.") # This message is better sent by orchestrator
        await state.clear()
        return
    next_address_info = pending_list.pop(0)
    await state.update_data(
        current_address_for_memo_id=next_address_info["id"],
        current_address_for_memo_text=next_address_info["address"],
        current_address_for_memo_blockchain=next_address_info["blockchain"],
        pending_addresses_for_memo=pending_list,
    )
    await message_to_reply_to.answer(
        f"Next, provide a memo for: <code>{next_address_info['address']}</code> ({next_address_info['blockchain'].capitalize()}).\nPlease reply with your memo, or send /skip.",
        parse_mode="HTML",
    )
    await state.set_state(AddressProcessingStates.awaiting_memo)


async def _process_memo_action(message: Message, state: FSMContext):
    db = SessionLocal()
    try:
        data = await state.get_data()
        address_id_to_update = data.get("current_address_for_memo_id")
        address_text_for_display = data.get(
            "current_address_for_memo_text", "the address"
        )
        blockchain_for_display = data.get("current_address_for_memo_blockchain", "N/A")
        pending_addresses = data.get("pending_addresses_for_memo", [])

        if not address_id_to_update:
            logging.warning("Attempted to process memo without address_id in state.")
            await message.answer(
                "Error: Could not determine which address to update. Please try scanning again."
            )
            await state.clear()
            return
        memo_text = message.text.strip()
        if not memo_text:
            await message.reply(
                "Memo cannot be empty. Please provide a memo or send /skip."
            )
            return

        addr_record = (
            db.query(CryptoAddress)
            .filter(CryptoAddress.id == address_id_to_update)
            .first()
        )
        if addr_record:
            addr_record.notes = memo_text
            db.commit()
            await message.answer(
                f"📝 Memo saved for <code>{html.quote(address_text_for_display)}</code> ({html.quote(blockchain_for_display.capitalize())}).",
                parse_mode="HTML",
            )
            if message.from_user:  # Audit log
                user = message.from_user
                user_info_parts_audit = [
                    "<b>👤 User Details:</b>",
                    f"ID: <code>{user.id}</code>",
                ]
                name_parts_audit = [
                    html.quote(n) for n in [user.first_name, user.last_name] if n
                ]
                if name_parts_audit:
                    user_info_parts_audit.append(f"Name: {' '.join(name_parts_audit)}")
                if user.username:
                    user_info_parts_audit.append(
                        f"Username: @{html.quote(user.username)}"
                    )
                audit_message_text = (
                    f"<b>📝 New Memo Added to Audit Log</b>\n\n{'\n'.join(user_info_parts_audit)}\n\n"
                    f"<b>Address Details:</b>\nAddress: <code>{html.quote(address_text_for_display)}</code>\nBlockchain: {html.quote(blockchain_for_display.capitalize())}\n\n"
                    f"<b>Memo Text:</b>\n{html.quote(memo_text)}"
                )
                try:
                    await message.bot.send_message(
                        chat_id=TARGET_AUDIT_CHANNEL_ID,
                        text=audit_message_text,
                        parse_mode="HTML",
                    )
                    logging.info(
                        "New memo audit log sent for address %s",
                        address_text_for_display,
                    )
                except Exception as e_audit:
                    logging.error(
                        "Failed to send new memo audit log. Error: %s", e_audit
                    )
            else:
                logging.warning("Could not send new memo audit log: no from_user info.")
        else:
            logging.error(
                "Could not find CryptoAddress with id %s to save memo.",
                address_id_to_update,
            )
            await message.answer("Error: Could not find the address to save the memo.")
            await state.clear()
            return
        if pending_addresses:
            await _prompt_for_next_memo(message, state, pending_addresses)
        else:
            await message.answer(
                "All memos processed. You can send new messages with addresses."
            )
            await state.clear()
    except Exception as e:
        logging.exception("Error in _process_memo_action: %s", e)
        await message.reply("An error occurred while saving the memo.")
        await state.clear()
    finally:
        if db.is_active:
            db.close()


async def _skip_memo_action(message: Message, state: FSMContext):
    data = await state.get_data()
    address_text_for_display = data.get(
        "current_address_for_memo_text", "the current address"
    )
    pending_addresses = data.get("pending_addresses_for_memo", [])
    await message.answer(
        f"Skipped memo for <code>{address_text_for_display}</code>.", parse_mode="HTML"
    )
    if pending_addresses:
        await _prompt_for_next_memo(message, state, pending_addresses)
    else:
        await message.answer(
            "All memos processed. You can send new messages with addresses."
        )
        await state.clear()
