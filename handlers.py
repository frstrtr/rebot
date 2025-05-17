import logging
import json
from aiogram import html, F
from aiogram.types import Message, ChatMemberUpdated, Update
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command  # For /skip command

from synapsifier.crypto_address import CryptoAddressFinder
from database import SessionLocal, save_message, save_crypto_address, CryptoAddress, CryptoAddressStatus

crypto_finder = CryptoAddressFinder()

# Define FSM States for memo processing
class AddressProcessingStates(StatesGroup):
    awaiting_memo = State()


async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    user_full_name = message.from_user.full_name if message.from_user else "there"
    await message.answer(f"Hello, {html.bold(user_full_name)}!")


# Main handler for messages, routes based on FSM state
async def handle_message_with_potential_crypto_address(message: Message, state: FSMContext):
    """
    Handles incoming messages. If not in a specific state, scans for crypto addresses.
    If in 'awaiting_memo' state, processes the user's reply as a memo or a skip command.
    """
    current_fsm_state = await state.get_state()

    if current_fsm_state == AddressProcessingStates.awaiting_memo:
        if message.text and message.text.lower() == "/skip":
            await _skip_memo_action(message, state)
        elif message.text:  # Assuming memo is text
            await _process_memo_action(message, state)
        else:
            # Non-text message while awaiting memo
            await message.reply("Please provide a text memo or send /skip.")
            # Stay in the awaiting_memo state
    else:
        # Not in a memo state, so scan the message for addresses
        await _scan_message_for_addresses_action(message, state)


async def _scan_message_for_addresses_action(message: Message, state: FSMContext):
    """
    Scans the message for crypto addresses, saves them, and initiates memo prompting.
    """
    db = SessionLocal()
    try:
        # 1. Store original message and user data
        db_message = save_message(db, message)
        if db_message is None:  # Should not happen if save_message is robust
            logging.error("Failed to save message to database.")
            await message.reply("An error occurred while processing your message (DB save failed).")
            return

        text_to_scan = (message.text or message.caption or "").strip()
        if not text_to_scan:
            logging.debug("Message ID %s has no text content to scan for addresses.", db_message.id)
            return

        # 2. Detect crypto addresses
        detected_raw_addresses_map = crypto_finder.find_addresses(text_to_scan)

        if not detected_raw_addresses_map:
            logging.debug("No crypto addresses found in message ID %s.", db_message.id)
            return

        addresses_for_memo_prompt = []
        initial_reply_lines = []

        for blockchain, addr_list_for_chain in detected_raw_addresses_map.items():
            for addr_str in addr_list_for_chain:
                # 3. Store each crypto address
                db_crypto_address = save_crypto_address(db, db_message.id, addr_str, blockchain)
                if db_crypto_address:
                    addresses_for_memo_prompt.append({
                        "id": db_crypto_address.id,
                        "address": db_crypto_address.address,
                        "blockchain": db_crypto_address.blockchain
                    })
                    initial_reply_lines.append(f"✅ <b>{blockchain.capitalize()}</b>: <code>{db_crypto_address.address}</code>")
                else:
                    logging.error("Failed to save crypto address %s for message %s", addr_str, db_message.id)

        if initial_reply_lines:
            await message.answer(
                "Detected and saved addresses:\n" + "\n".join(initial_reply_lines),
                parse_mode="HTML"
            )

        # 4. Start prompting for memos if any addresses were processed
        if addresses_for_memo_prompt:
            await _prompt_for_next_memo(message, state, addresses_for_memo_prompt)

    except ValueError as ve:
        logging.error("ValueError in address scanning: %s", ve)
        await message.reply("An error occurred while processing your message.")
    except Exception as e:
        logging.exception("Unexpected error in _scan_message_for_addresses_action: %s", e)
        await message.reply("An unexpected error occurred.")
    finally:
        db.close()


async def _prompt_for_next_memo(message_to_reply_to: Message, state: FSMContext, pending_list: list):
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
        pending_addresses_for_memo=pending_list
    )
    await message_to_reply_to.answer(
        f"Next, provide a memo for: <code>{next_address_info['address']}</code> ({next_address_info['blockchain'].capitalize()}).\n"
        "Please reply with your memo, or send /skip.",
        parse_mode="HTML"
    )
    await state.set_state(AddressProcessingStates.awaiting_memo)


async def _process_memo_action(message: Message, state: FSMContext):
    """
    Processes the user's reply as a memo for the current address.
    """
    db = SessionLocal()
    try:
        data = await state.get_data()
        address_id_to_update = data.get("current_address_for_memo_id")
        address_text_for_display = data.get("current_address_for_memo_text", "the address")
        pending_addresses = data.get("pending_addresses_for_memo", [])

        if not address_id_to_update:
            logging.warning("Attempted to process memo without address_id in state.")
            await message.answer("Error: Could not determine which address to update. Please try scanning again.")
            await state.clear()
            return

        memo_text = message.text.strip()
        if not memo_text:
            await message.reply("Memo cannot be empty. Please provide a memo or send /skip.")
            return

        addr_record = db.query(CryptoAddress).filter(CryptoAddress.id == address_id_to_update).first()
        if addr_record:
            addr_record.notes = memo_text
            db.commit()
            await message.answer(f"📝 Memo saved for <code>{address_text_for_display}</code>.", parse_mode="HTML")
        else:
            logging.error("Could not find CryptoAddress with id %s to save memo.", address_id_to_update)
            await message.answer("Error: Could not find the address in the database to save the memo.")
            await state.clear()
            return

        if pending_addresses:
            await _prompt_for_next_memo(message, state, pending_addresses)
        else:
            await message.answer("All memos processed. You can send new messages with addresses.")
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
    address_text_for_display = data.get("current_address_for_memo_text", "the current address")
    pending_addresses = data.get("pending_addresses_for_memo", [])

    await message.answer(f"Skipped memo for <code>{address_text_for_display}</code>.", parse_mode="HTML")

    if pending_addresses:
        await _prompt_for_next_memo(message, state, pending_addresses)
    else:
        await message.answer("All memos processed. You can send new messages with addresses.")
        await state.clear()


async def handle_story(message: Message) -> None:
    """
    Handler will forward receive a message back to the sender
    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    try:
        # Send a copy of the received message
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
    Handle all updates
    """
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


async def unhandled_updates_handler(update: Update) -> None:
    """
    Log all unhandled updates
    """
    event = update.model_dump_json(indent=4, exclude_none=True)
    logging.info("Update: %s", event)
