import logging
import json
from aiogram import html, F, types
from aiogram.types import (
    Message,
    ChatMemberUpdated,
    # Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from sqlalchemy import func

from config.config import Config  # Ensure Config class is imported
from config.credentials import Credentials 
from synapsifier.crypto_address import CryptoAddressFinder
from database import (
    SessionLocal,
    save_message,
    save_crypto_address,
    CryptoAddress,
    CryptoAddressStatus,
)

# Instantiate Credentials
credentials = Credentials()
TARGET_AUDIT_CHANNEL_ID = credentials.get_target_audit_channel_id() 

crypto_finder = CryptoAddressFinder()


# Define FSM States for memo processing
class AddressProcessingStates(StatesGroup):
    awaiting_blockchain = State()
    awaiting_memo = State()


async def command_start_handler(message: Message, state: FSMContext) -> None:
    """
    This handler receives messages with `/start` command
    """
    logging.info(f"command_start_handler received /start from user.")

    user_full_name = message.from_user.full_name if message.from_user else "there"
    await message.answer(
        f"Hello, {html.bold(user_full_name)}!\n\n Please send me a message containing a crypto address, and I will help you with it.\n\n"
        "You can also use /checkmemo to check existing memos for a crypto address.\n"
        "If you want to skip the memo process, just reply with /skip.\n"
    )
    await state.clear()

    # Send user details to audit channel
    if message.from_user:
        user = message.from_user
        user_info_parts = ["Audit: User started the bot with /start command."]
        user_info_parts.append(f"User ID: (<code>{user.id}</code>)")

        name_parts = []
        if user.first_name:
            name_parts.append(html.quote(user.first_name))
        if user.last_name:
            name_parts.append(html.quote(user.last_name))
        if name_parts:
            user_info_parts.append(f"Name: {' '.join(name_parts)}")

        if user.username:
            user_info_parts.append(f"Username: @{html.quote(user.username)}")

        audit_details_text = "\n".join(user_info_parts)

        try:
            await message.bot.send_message(
                chat_id=TARGET_AUDIT_CHANNEL_ID,
                text=audit_details_text,
                parse_mode="HTML",
            )
            logging.info(
                f"/start command from user {user.id} logged to audit channel {TARGET_AUDIT_CHANNEL_ID}"
            )
        except Exception as e:
            logging.error(
                f"Failed to send /start audit info to audit channel {TARGET_AUDIT_CHANNEL_ID} for user {user.id}. Error: {e}"
            )


async def _forward_to_audit_channel(message: Message):
    """
    Forwards the message to the audit channel and sends sender's details.
    """
    if not message.from_user:
        logging.warning("Cannot forward message: no from_user info.")
        return

    user = message.from_user
    user_info_parts = ["👤 Message received from:"]
    user_info_parts.append(f"ID: (<code>{user.id}</code>)")

    name_parts = []
    if user.first_name:
        name_parts.append(html.quote(user.first_name))
    if user.last_name:
        name_parts.append(html.quote(user.last_name))
    if name_parts:
        user_info_parts.append(f"Name: {' '.join(name_parts)}")

    if user.username:
        user_info_parts.append(f"Username: @{html.quote(user.username)}")

    user_details_text = "\n".join(user_info_parts)

    try:
        if message.text != "/skip":
            await message.forward(chat_id=TARGET_AUDIT_CHANNEL_ID)
            await message.bot.send_message(
                chat_id=TARGET_AUDIT_CHANNEL_ID,
                text=user_details_text,
                parse_mode="HTML",
            )
            logging.info(
                f"Message from {user.id} forwarded to audit channel {TARGET_AUDIT_CHANNEL_ID}"
            )
        else:
            logging.info(f"Message from {user.id} was a /skip command, not forwarded.")
    except Exception as e:
        logging.error(
            f"Failed to forward message or send user info to audit channel {TARGET_AUDIT_CHANNEL_ID} for user {user.id}. Error: {e}"
        )


async def handle_message_with_potential_crypto_address(
    message: Message, state: FSMContext
):
    """
    Handles incoming messages. If not in a specific state, scans for crypto addresses.
    If in 'awaiting_memo' state, processes the user's reply as a memo or a skip command.
    If in 'awaiting_blockchain' state, processes the user's reply as blockchain choice.
    Also forwards the message to an audit channel, unless it's a memo submission.
    """
    current_fsm_state = await state.get_state()

    # Forward message and user info to the audit channel first,
    # UNLESS it's a direct reply when awaiting a memo.
    if current_fsm_state != AddressProcessingStates.awaiting_memo:
        await _forward_to_audit_channel(message)
    # For memo submissions, a custom audit message will be sent by _process_memo_action

    logging.info(
        f"Handling message in handle_message_with_potential_crypto_address. \033[93mText: '{message.text}'\033[0m"
    )
    # current_fsm_state = await state.get_state() # Already got this above

    if current_fsm_state == AddressProcessingStates.awaiting_memo:
        if message.text and message.text.lower() == "/skip":
            await _skip_memo_action(message, state)
        elif message.text:
            await _process_memo_action(message, state)
        else:
            await message.reply("Please provide a text memo or send /skip.")
    elif current_fsm_state == AddressProcessingStates.awaiting_blockchain:
        await _handle_blockchain_reply(message, state)
    else:
        await _scan_message_for_addresses_action(message, state)


async def _scan_message_for_addresses_action(message: Message, state: FSMContext):
    """
    Scans the message for crypto addresses, displays previous memos,
    and initiates blockchain clarification or memo prompting.
    If no addresses are found, informs the user.
    """
    db = SessionLocal()
    try:
        db_message = save_message(db, message)
        if db_message is None:
            logging.error("Failed to save message to database.")
            await message.reply(
                "An error occurred while processing your message (DB save failed)."
            )
            return

        text_to_scan = (message.text or message.caption or "").strip()
        if not text_to_scan:
            logging.debug(
                "Message ID %s has no text content to scan for addresses.",
                db_message.id,
            )
            return

        detected_raw_addresses_map = crypto_finder.find_addresses(text_to_scan)
        logging.debug(f"Detected map from crypto_finder: {detected_raw_addresses_map}")

        if detected_raw_addresses_map:
            try:
                audit_addresses_parts = [
                    "<b>🔍 Detected Crypto Addresses in User Message:</b>"
                ]
                all_detected_pairs = []  # To collect all (blockchain, address) pairs

                for blockchain, addresses_list in detected_raw_addresses_map.items():
                    if addresses_list:  # Ensure there are addresses for this blockchain
                        formatted_addresses_list = []
                        for addr in addresses_list:
                            formatted_addresses_list.append(
                                f"  • <code>{html.quote(addr)}</code>"
                            )
                            all_detected_pairs.append(
                                (blockchain, addr)
                            )  # Populate for button logic

                        formatted_addresses_text = "\n".join(formatted_addresses_list)
                        audit_addresses_parts.append(
                            f"<b>{html.quote(blockchain.capitalize())}:</b>\n{formatted_addresses_text}"
                        )

                audit_addresses_text = "\n\n".join(audit_addresses_parts)

                reply_markup_for_audit = None
                audit_buttons_list = []  # To hold rows of buttons

                # Create a button for each detected address that has a configured explorer
                for blockchain_key, addr_str in all_detected_pairs:
                    if blockchain_key in Config.EXPLORER_CONFIG: # MODIFIED
                        config = Config.EXPLORER_CONFIG[blockchain_key] # MODIFIED
                        explorer_name = config["name"]
                        url = config["url_template"].format(address=addr_str)

                        button_text_addr = addr_str
                        if len(addr_str) > 20:  # Shorten address for button text
                            button_text_addr = f"{addr_str[:6]}...{addr_str[-4:]}"

                        audit_button = InlineKeyboardButton(
                            text=f"View {button_text_addr} on {explorer_name}", url=url
                        )
                        audit_buttons_list.append(
                            [audit_button]
                        )  # Add button as a new row

                if audit_buttons_list:
                    reply_markup_for_audit = InlineKeyboardMarkup(
                        inline_keyboard=audit_buttons_list
                    )

                # Send if there are actual detected addresses listed (more than just the header)
                if len(audit_addresses_parts) > 1:
                    await message.bot.send_message(
                        chat_id=TARGET_AUDIT_CHANNEL_ID,
                        text=audit_addresses_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup_for_audit,  # Add the button if created
                    )
                    logging.info(
                        f"Detected addresses forwarded to audit channel {TARGET_AUDIT_CHANNEL_ID}"
                    )
            except Exception as e:
                logging.error(
                    f"Failed to forward detected addresses to audit channel {TARGET_AUDIT_CHANNEL_ID}. Error: {e}"
                )

        if not detected_raw_addresses_map:
            logging.debug("No crypto addresses found in message ID %s.", db_message.id)
            await message.reply(
                "No crypto addresses found in your message. Please send a message containing a crypto address."
            )
            return

        await state.update_data(current_scan_db_message_id=db_message.id)

        pending_blockchain_clarification = []
        addresses_for_memo_prompt_details = []
        addresses_for_explorer_buttons = []

        detected_address_info_blocks = []

        aggregated_detections = {}
        for bc, addr_list in detected_raw_addresses_map.items():
            for addr in addr_list:
                if addr not in aggregated_detections:
                    aggregated_detections[addr] = {"chains": set()}
                aggregated_detections[addr]["chains"].add(bc)

        for addr_str, data in aggregated_detections.items():
            detected_chains_set = data["chains"]
            current_address_block_parts = []

            potential_chains_display = ", ".join(
                sorted(list(chain.capitalize() for chain in detected_chains_set))
            )
            current_address_block_parts.append(
                f"🔍 Found: <code>{html.quote(addr_str)}</code>\n"
                f"   (Potential chains: {potential_chains_display})"
            )

            existing_memos = (
                db.query(CryptoAddress)
                .filter(
                    func.lower(CryptoAddress.address) == addr_str.lower(),
                    CryptoAddress.notes.isnot(None),
                    CryptoAddress.notes != "",
                )
                .order_by(CryptoAddress.blockchain, CryptoAddress.id)
                .all()
            )

            if existing_memos:
                memo_lines = ["📜 <b>Previous Memos:</b>"]
                for memo_item in existing_memos:
                    status_display = (
                        memo_item.status.value
                        if isinstance(memo_item.status, CryptoAddressStatus)
                        else str(memo_item.status or "N/A")
                    )
                    memo_lines.append(
                        f"  • <b>{memo_item.blockchain.capitalize()}</b> (<i>{status_display}</i>): {html.quote(memo_item.notes)}"
                    )
                current_address_block_parts.append("\n".join(memo_lines))
            else:
                current_address_block_parts.append(
                    "  (No previous memos found for this address.)"
                )

            detected_address_info_blocks.append("\n".join(current_address_block_parts))

            specific_chains = {
                chain for chain in detected_chains_set if chain != "address"
            }

            if len(specific_chains) == 1:
                chosen_blockchain = list(specific_chains)[0]
                addresses_for_memo_prompt_details.append(
                    {
                        "address": addr_str,
                        "blockchain": chosen_blockchain,
                    }
                )
                if chosen_blockchain in Config.EXPLORER_CONFIG: # MODIFIED
                    addresses_for_explorer_buttons.append(
                        {"address": addr_str, "blockchain": chosen_blockchain}
                    )
            else:
                options = sorted(list(specific_chains)) if specific_chains else []
                pending_blockchain_clarification.append(
                    {
                        "address": addr_str,
                        "detected_on_options": options,
                    }
                )

        if detected_address_info_blocks:
            # MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, using a buffer # This line is removed
            initial_header_text = "<b>Address Detections & History:</b>\n\n"
            
            final_messages_to_send = []
            
            # Initialize the first message with the header
            active_message_parts = [initial_header_text]
            current_length = len(initial_header_text)

            for block_text in detected_address_info_blocks:
                needs_separator = False
                # A separator is needed if active_message_parts is not empty AND
                # it's not just the initial_header_text waiting for its first block.
                if active_message_parts:
                    if not (len(active_message_parts) == 1 and active_message_parts[0] == initial_header_text):
                        needs_separator = True
                
                separator_len = 2 if needs_separator else 0 # for "\n\n"
                block_len = len(block_text)

                if current_length + separator_len + block_len > Config.MAX_TELEGRAM_MESSAGE_LENGTH: # MODIFIED
                    # Current message is full, or adding this block makes it too full.
                    # Finalize and store the current message.
                    if "".join(active_message_parts).strip(): # Ensure it's not empty
                        final_messages_to_send.append("".join(active_message_parts))
                    
                    # Start a new message. This new message does NOT get the primary header.
                    # It starts directly with the current block_text.
                    active_message_parts = [block_text]
                    current_length = block_len

                    # Handle if this single block_text itself is too long for a new message
                    if current_length > Config.MAX_TELEGRAM_MESSAGE_LENGTH: # MODIFIED
                        logging.warning(
                            f"A single address info block is too long ({current_length} chars) and will be truncated."
                        )
                        # Truncate the block to fit, leaving space for ellipsis and " (truncated)"
                        truncation_suffix = "... (truncated)"
                        allowed_block_len = Config.MAX_TELEGRAM_MESSAGE_LENGTH - len(truncation_suffix) # MODIFIED
                        truncated_block = block_text[:allowed_block_len] + truncation_suffix
                        active_message_parts = [truncated_block]
                        current_length = len(truncated_block)
                        # If somehow still too long (e.g., MAX_TELEGRAM_MESSAGE_LENGTH is extremely small)
                        if current_length > Config.MAX_TELEGRAM_MESSAGE_LENGTH: # MODIFIED
                             active_message_parts = ["Error: Content block too large to display."]
                             current_length = len(active_message_parts[0])
                else:
                    # It fits. Add separator if needed.
                    if needs_separator:
                        active_message_parts.append("\n\n")
                        current_length += 2
                    
                    active_message_parts.append(block_text)
                    current_length += block_len
            
            # Add the last composed message to the list, if it contains content.
            if active_message_parts and "".join(active_message_parts).strip():
                # Avoid adding an empty header if no blocks were actually processed with it.
                # This check ensures we don't send a message that's only the initial_header_text
                # if no blocks were appended to that initial header instance.
                if not (len(active_message_parts) == 1 and active_message_parts[0] == initial_header_text):
                    final_messages_to_send.append("".join(active_message_parts))
                # If it is just the initial_header_text, it means no blocks were added to THIS header instance.
                # This can happen if the first block was too long, causing the header to be sent alone,
                # and then active_message_parts was reset.

            # Send all prepared messages.
            for text_to_send in final_messages_to_send:
                if text_to_send.strip(): # Final check to not send empty strings
                    await message.answer(text_to_send, parse_mode="HTML")

        if addresses_for_explorer_buttons:
            explorer_url_buttons_list = []
            for item in addresses_for_explorer_buttons:
                addr = item["address"]
                blockchain_key = item["blockchain"]

                if blockchain_key in Config.EXPLORER_CONFIG: # MODIFIED
                    config = Config.EXPLORER_CONFIG[blockchain_key] # MODIFIED
                    explorer_name = config["name"]
                    url = config["url_template"].format(address=addr)

                    button_text_addr = addr
                    if len(addr) > 20:
                        button_text_addr = f"{addr[:6]}...{addr[-4:]}"

                    explorer_url_buttons_list.append(
                        [
                            InlineKeyboardButton(
                                text=f"View {button_text_addr} on {explorer_name}",
                                url=url,
                            )
                        ]
                    )

            if explorer_url_buttons_list:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=explorer_url_buttons_list
                )
                await message.answer(
                    "Direct links to blockchain explorers:",
                    reply_markup=keyboard,
                )

        await state.update_data(
            pending_blockchain_clarification=pending_blockchain_clarification,
            addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
        )
        db.close()
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
    """
    Orchestrates the next step in processing:
    1. Ask for blockchain clarification if pending.
    2. Save addresses with known blockchains and prepare for memo prompt.
    3. Prompt for the next memo.
    4. Clear state if all done.
    """
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
                addr_str = detail["address"]
                blockchain = detail["blockchain"]

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
                        f"Failed to save address {addr_str} on {blockchain} during orchestration for memo prompt."
                    )

            await state.update_data(addresses_for_memo_prompt_details=[])

            if ready_for_memo_prompt_with_ids:
                await _prompt_for_next_memo(
                    message_to_reply_to, state, ready_for_memo_prompt_with_ids
                )
            else:
                logging.info("No addresses successfully saved to prompt for memo.")
                remaining_clarifications = await state.get_data()
                if not remaining_clarifications.get("pending_blockchain_clarification"):
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
    """
    Asks the user to specify the blockchain for a given address using inline buttons.
    """
    address = item_to_clarify["address"]
    detected_options = item_to_clarify["detected_on_options"]

    keyboard_buttons = []
    if detected_options:
        for option in detected_options:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=option.capitalize(),
                        callback_data=f"clarify_bc:chosen:{option.lower()}",
                    )
                ]
            )

    keyboard_buttons.append(
        [
            InlineKeyboardButton(
                text="Other (Type manually)", callback_data="clarify_bc:other"
            )
        ]
    )
    keyboard_buttons.append(
        [
            InlineKeyboardButton(
                text="Skip this address", callback_data="clarify_bc:skip"
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    prompt_text = (
        f"For address: <code>{html.quote(address)}</code>\n"
        f"Which blockchain network does this address belong to?\n"
        "Please select from the options below."
    )
    if not detected_options:
        prompt_text += "\n(No specific chains were auto-detected, please choose 'Other' or 'Skip'.)"

    await message_to_reply_to.answer(
        prompt_text, reply_markup=keyboard, parse_mode="HTML"
    )
    await state.set_state(AddressProcessingStates.awaiting_blockchain)


async def handle_blockchain_clarification_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """
    Handles callback queries for blockchain clarification.
    """
    await callback_query.answer()

    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )

    if not item_being_clarified:
        await callback_query.message.answer(
            "Error: Could not determine which address this choice is for. Please try scanning again."
        )
        await state.clear()
        return

    action, *params = callback_query.data.split(":")
    if params[0] == "chosen":
        chosen_blockchain = params[1]
        addresses_for_memo_prompt_details.append(
            {
                "address": item_being_clarified["address"],
                "blockchain": chosen_blockchain,
            }
        )
        await state.update_data(
            addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
            current_item_for_blockchain_clarification=None,
        )
        await callback_query.message.edit_text(
            f"Noted: Address <code>{html.quote(item_being_clarified['address'])}</code> will be associated with <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await _orchestrate_next_processing_step(callback_query.message, state)

    elif params[0] == "other":
        await callback_query.message.edit_text(
            f"For address: <code>{html.quote(item_being_clarified['address'])}</code>\n"
            "Please type the name of the blockchain network.",
            parse_mode="HTML",
            reply_markup=None,
        )

    elif params[0] == "skip":
        await state.update_data(current_item_for_blockchain_clarification=None)
        await callback_query.message.edit_text(
            f"Skipped blockchain clarification for address: <code>{html.quote(item_being_clarified['address'])}</code>.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await _orchestrate_next_processing_step(callback_query.message, state)

    else:
        logging.warning(
            f"Unknown callback data received for blockchain clarification: {callback_query.data}"
        )
        await callback_query.message.answer(
            "An unexpected error occurred with your selection."
        )


async def _handle_blockchain_reply(message: Message, state: FSMContext):
    """
    Handles the user's text reply when specifying a blockchain.
    """
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")
    addresses_for_memo_prompt_details = data.get(
        "addresses_for_memo_prompt_details", []
    )

    if not item_being_clarified:
        await message.reply(
            "Error: Could not determine which address this blockchain choice is for. Please try scanning again."
        )
        await state.clear()
        return

    chosen_blockchain = (message.text or "").strip().lower()
    if not chosen_blockchain:
        await message.reply(
            "Blockchain name cannot be empty. Please try again, or use /skip_address_processing to cancel this address."
        )
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
    """
    Helper function to prompt for a memo for the next address in the list.
    """
    if not pending_list:
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
        f"Next, provide a memo for: <code>{next_address_info['address']}</code> ({next_address_info['blockchain'].capitalize()}).\n"
        "Please reply with your memo, or send /skip.",
        parse_mode="HTML",
    )
    await state.set_state(AddressProcessingStates.awaiting_memo)


async def _process_memo_action(message: Message, state: FSMContext):
    """
    Processes the user's reply as a memo for the current address.
    Sends a consolidated audit message upon successful memo save.
    """
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

            # Send consolidated audit message
            if message.from_user:
                user = message.from_user
                user_info_parts_audit = ["<b>👤 User Details:</b>"]
                user_info_parts_audit.append(f"ID: <code>{user.id}</code>")

                name_parts_audit = []
                if user.first_name:
                    name_parts_audit.append(html.quote(user.first_name))
                if user.last_name:
                    name_parts_audit.append(html.quote(user.last_name))
                if name_parts_audit:
                    user_info_parts_audit.append(f"Name: {' '.join(name_parts_audit)}")

                if user.username:
                    user_info_parts_audit.append(
                        f"Username: @{html.quote(user.username)}"
                    )

                user_details_audit_text = "\n".join(user_info_parts_audit)

                audit_message_text = (
                    f"<b>📝 New Memo Added to Audit Log</b>\n\n"
                    f"{user_details_audit_text}\n\n"
                    f"<b>Address Details:</b>\n"
                    f"Address: <code>{html.quote(address_text_for_display)}</code>\n"
                    f"Blockchain: {html.quote(blockchain_for_display.capitalize())}\n\n"
                    f"<b>Memo Text:</b>\n{html.quote(memo_text)}"
                )
                try:
                    await message.bot.send_message(
                        chat_id=TARGET_AUDIT_CHANNEL_ID,
                        text=audit_message_text,
                        parse_mode="HTML",
                    )
                    logging.info(
                        f"New memo audit log sent to channel {TARGET_AUDIT_CHANNEL_ID} for address {address_text_for_display}"
                    )
                except Exception as e_audit:
                    logging.error(
                        f"Failed to send new memo audit log to channel {TARGET_AUDIT_CHANNEL_ID}. Error: {e_audit}"
                    )
            else:
                logging.warning(
                    "Could not send new memo audit log: no from_user info in message."
                )

        else:
            logging.error(
                "Could not find CryptoAddress with id %s to save memo.",
                address_id_to_update,
            )
            await message.answer(
                "Error: Could not find the address in the database to save the memo."
            )
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
        db.close()


async def _skip_memo_action(message: Message, state: FSMContext):
    """
    Handles the /skip command when awaiting a memo.
    """
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


async def handle_story(message: Message) -> None:
    """
    Handler will forward receive a message back to the sender
    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    logging.info(f"handle_story received a story from chat_id: {message.chat.id}")
    try:
        msg_copy = await message.send_copy(chat_id=message.chat.id)
        msg_copy_json = message.model_dump_json(exclude_none=True)
        msg_copy_dict = json.loads(msg_copy_json)
        if "story" in msg_copy_dict:
            logging.info(
                "%s sent story object in chat %s (%s) message forwarded from %s",
                message.from_user.id if message.from_user else "unknown_user",
                (
                    getattr(message.chat, "title", None)
                    if getattr(message.chat, "title", None)
                    else message.chat.username or message.chat.id
                ),
                message.chat.id,
                (
                    getattr(message.forward_from_chat, "title", None)
                    if getattr(message.forward_from_chat, "title", None)
                    else getattr(message.forward_from_chat, "username", None)
                    or getattr(message.forward_from_chat, "id", None)
                ),
            )
        logging.info("Message object:")
        logging.info(msg_copy.model_dump_json(indent=4, exclude_none=True))
    except TypeError:
        await message.answer("Nice try!")


async def member_status_update_handler(update: ChatMemberUpdated) -> None:
    """
    Handle member status updates.
    """
    logging.info(
        f"member_status_update_handler received update for chat_id: {update.chat.id}, user_id: {update.new_chat_member.user.id}"
    )
    update_by_user_id = update.from_user.id
    update_member_id = update.old_chat_member.user.id
    update_member_old_status = update.old_chat_member.status
    update_member_new_status = update.new_chat_member.status
    logging.info(
        "%s changed from %s to %s by %s",
        update_member_id,
        update_member_old_status,
        update_member_new_status,
        update_by_user_id,
    )


async def unhandled_updates_handler(message: types.Message) -> None:
    """
    Log all unhandled updates (specifically edited messages as currently registered).
    """
    logging.info(
        f"unhandled_updates_handler received an edited_message. Chat ID: {message.chat.id}, Message ID: {message.message_id}"
    )
    event_data = message.model_dump_json(indent=4, exclude_none=True)
    logging.info("Edited Message Content: %s", event_data)


async def checkmemo_handler(message: types.Message):
    """
    Handles the /checkmemo command to retrieve memos for a given crypto address.
    Fetches records for the specified address across all its associated blockchains
    where a memo (notes) is present.
    Adds a "View on Explorer" button if the address is valid for a configured blockchain.
    """
    logging.info(
        f"checkmemo_handler received command from user. Text: '{message.text}'"
    )
    if not message.text:
        await message.reply(
            "Usage: /checkmemo <code>crypto_address</code>", parse_mode="HTML"
        )
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "Usage: /checkmemo <code>crypto_address</code>", parse_mode="HTML"
        )
        return

    address_arg = parts[1].strip()
    if not address_arg:
        await message.reply(
            "Usage: /checkmemo <code>crypto_address</code>", parse_mode="HTML"
        )
        return

    db = SessionLocal()
    reply_markup = None

    try:
        # Iterate through EXPLORER_CONFIG to find a suitable explorer for the address
        for blockchain_key, config in Config.EXPLORER_CONFIG.items(): # MODIFIED
            if crypto_finder.validate_checksum(blockchain_key, address_arg):
                explorer_name = config["name"]
                url = config["url_template"].format(address=address_arg)

                button_text_addr = address_arg
                if len(address_arg) > 20:  # Shorten address for button text
                    button_text_addr = f"{address_arg[:6]}...{address_arg[-4:]}"

                explorer_button = InlineKeyboardButton(
                    text=f"View {button_text_addr} on {explorer_name}",
                    url=url,
                )
                reply_markup = InlineKeyboardMarkup(inline_keyboard=[[explorer_button]])
                break  # Found a valid explorer, no need to check further

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
                f"No memos found for address: <code>{html.quote(address_arg)}</code>",
                parse_mode="HTML",
                reply_markup=reply_markup,  # Send button even if no memos
            )
            return

        memos_text_parts = []
        for row in results:
            status_display = "N/A"
            if isinstance(row.status, CryptoAddressStatus):
                status_display = row.status.value
            elif row.status is not None:
                status_display = str(row.status)

            memos_text_parts.append(
                f"<b>Blockchain:</b> {html.quote(row.blockchain)}\n"
                f"<b>Status:</b> {html.quote(status_display)}\n"
                f"<b>Memo:</b> {html.quote(row.notes)}"
            )

        response_header = (
            f"<b>Memos for Address:</b> <code>{html.quote(address_arg)}</code>\n\n"
        )
        response_body = "\n\n".join(memos_text_parts)
        full_response_text = response_header + response_body

        if len(full_response_text) > 4096:
            await message.reply(
                response_header, parse_mode="HTML", reply_markup=reply_markup
            )
            await message.reply(
                "The list of memos is too long to display in a single message. Please check logs or refine your search if possible.",
                parse_mode="HTML",
            )
            logging.info(
                f"Full memo list for {address_arg} was too long for Telegram. Full text: {full_response_text}"
            )
        else:
            await message.reply(
                full_response_text, parse_mode="HTML", reply_markup=reply_markup
            )

    except Exception as e:
        logging.exception(
            f"Error in checkmemo_handler for address {html.quote(address_arg)}: {e}"
        )
        await message.reply(
            "An error occurred while retrieving memos. Please check the bot logs."
        )
    finally:
        if db.is_active:
            db.close()
