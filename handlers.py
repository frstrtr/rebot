# handlers.py

import logging
import json
from aiogram import html
from aiogram.types import Message, Update

async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")

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
                message.from_user.id,
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

async def update_handler(update: Update) -> None:
    """
    Handle all updates
    """
    logging.info("Chat member status: %s", update.model_dump_json(exclude_none=True, indent=4))
