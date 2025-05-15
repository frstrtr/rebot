# handlers.py

import logging
import json
from aiogram import html
from aiogram.types import Message, ChatMemberUpdated, Update
from synapsifier.crypto_address import CryptoAddressFinder

crypto_finder = CryptoAddressFinder()


async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    user_full_name = message.from_user.full_name if message.from_user else "there"
    await message.answer(f"Hello, {html.bold(user_full_name)}!")


async def handle_crypto_address(message: Message) -> None:
    """
    Handler to check if the received message is a valid crypto address and validate its checksum if possible.
    """
    text = message.text.strip() if message.text else ""
    if not text:
        await message.answer("Please send a crypto address.")
        return

    results = crypto_finder.find_addresses(text)
    if not results:
        await message.answer("No valid crypto address found in your message.")
        return

    reply_lines = []
    for blockchain, addresses in results.items():
        for address in addresses:
            reply_lines.append(f"✅ <b>{blockchain.capitalize()}</b> address detected and checksum is valid:\n<code>{address}</code>")

    await message.answer("\n\n".join(reply_lines), parse_mode="HTML")
    

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
        # log message object as idented JSON
        logging.info("Message object:")
        logging.info(msg_copy.model_dump_json(indent=4, exclude_none=True))
    except TypeError:
        # But not all the types is supported to be copied so need to handle it
        await message.answer("Nice try!")


async def member_status_update_handler(update: ChatMemberUpdated) -> None:
    """
    Handle all updates
    """
    # Log update object as idented JSON
    # logging.info("Chat member status: %s", update.model_dump_json(exclude_none=True, indent=4))
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
