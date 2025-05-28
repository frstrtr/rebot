import logging
import json
from aiogram import types
from aiogram.types import ChatMemberUpdated, Message # Message for edited_message

async def member_status_update_handler(update: ChatMemberUpdated) -> None:
    logging.info(f"member_status_update_handler for chat {update.chat.id}, user {update.new_chat_member.user.id}")
    logging.info(f"{update.old_chat_member.user.id} from {update.old_chat_member.status} to {update.new_chat_member.status} by {update.from_user.id}")

async def unhandled_updates_handler(message: Message) -> None: # Assuming this is for edited messages
    logging.info(f"unhandled_updates_handler (edited_message). Chat: {message.chat.id}, Msg ID: {message.message_id}")
    try:
        event_data = message.model_dump_json(indent=2, exclude_none=True)
        logging.info(f"Edited Message Content: {event_data}")
    except Exception as e:
        logging.error(f"Error dumping edited message: {e}")