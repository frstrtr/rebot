"""helpers.py - Contains utility functions for handling messages
and forwarding them to an audit channel."""

import logging
from aiogram import html, Bot # Added Bot
from aiogram.types import Message, User # Added User
from aiogram.exceptions import TelegramAPIError
from .common import TARGET_AUDIT_CHANNEL_ID, AMBIGUOUS_CHAIN_GROUPS

def get_ambiguity_group_members(chain_name: str) -> set | None:
    """
    If the given chain_name is part of a defined ambiguous group,
    returns all members of that group. Otherwise, returns None.
    Uses AMBIGUOUS_CHAIN_GROUPS from common.
    """
    for _group_name, chains_in_group in AMBIGUOUS_CHAIN_GROUPS.items():
        if chain_name.lower() in chains_in_group:
            return chains_in_group
    return None

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
        # Assuming /skip is a command/text the user might send
        if message.text and message.text.lower() == "/skip":
            logging.info("Message from %s was a /skip command, not forwarded.", user.id)
        else:
            await message.forward(chat_id=TARGET_AUDIT_CHANNEL_ID)
            await message.bot.send_message(
                chat_id=TARGET_AUDIT_CHANNEL_ID,
                text=user_details_text,
                parse_mode="HTML",
            )
            logging.info(
                "Message from %s forwarded to audit channel %s",
                user.id,
                TARGET_AUDIT_CHANNEL_ID,
            )
    except TelegramAPIError as e:
        logging.error(
            "Failed to forward message or send user info to audit channel %s for user %s. Error: %s",
            TARGET_AUDIT_CHANNEL_ID,
            user.id,
            e
        )

def format_user_info_for_audit(user: User) -> str:
    """Formats user information for audit logs."""
    user_info_parts = ["<b>👤 User Details:</b>"]
    user_info_parts.append(f"ID: <code>{user.id}</code>")
    name_parts = [html.quote(n) for n in [user.first_name, user.last_name] if n]
    if name_parts:
        user_info_parts.append(f"Name: {' '.join(name_parts)}")
    if user.username:
        user_info_parts.append(f"Username: @{html.quote(user.username)}")
    return "\n".join(user_info_parts)

async def send_text_to_audit_channel(bot: Bot, text: str, parse_mode: str = "HTML"):
    """Sends a text message to the configured audit channel."""
    if TARGET_AUDIT_CHANNEL_ID:
        try:
            await bot.send_message(TARGET_AUDIT_CHANNEL_ID, text, parse_mode=parse_mode)
            logging.info(f"Sent audit text to channel {TARGET_AUDIT_CHANNEL_ID}") # pylint: disable=logging-fstring-interpolation
        except Exception as e:
            logging.error(f"Failed to send text to audit channel {TARGET_AUDIT_CHANNEL_ID}: {e}") # pylint: disable=logging-fstring-interpolation
    else:
        logging.warning("TARGET_AUDIT_CHANNEL_ID not set. Audit message not sent.")