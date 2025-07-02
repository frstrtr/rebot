"""helpers.py - Contains utility functions for handling messages
and forwarding them to an audit channel."""

import logging, re
from aiogram import html, Bot 
from aiogram.types import Message, User 
from aiogram.exceptions import TelegramAPIError
import asyncio # Added for asyncio operations
import logging # Added for logging within the helper
import markdown as markdown2 # Added for Markdown to HTML conversion
from bs4 import BeautifulSoup # Added for HTML sanitization
from .common import TARGET_AUDIT_CHANNEL_ID, AMBIGUOUS_CHAIN_GROUPS, crypto_finder # crypto_finder is needed
from config.credentials import Credentials # Import Credentials to get bot token

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
    user_details_text = format_user_info_for_audit(user)

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
                disable_web_page_preview=True,
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
    """Formats user information for audit logs with deeplinked user ID."""
    user_id_deeplink = f"<a href=\"https://t.me/oLolsBot?start={user.id}\">{user.id}</a>"
    user_info_parts = ["👤 User Details:"]
    user_info_parts.append(f"ID: {user_id_deeplink}")
    
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
            await bot.send_message(TARGET_AUDIT_CHANNEL_ID, text, parse_mode=parse_mode, disable_web_page_preview=True)
            logging.info(f"Sent audit text to channel {TARGET_AUDIT_CHANNEL_ID}") # pylint: disable=logging-fstring-interpolation
        except TelegramAPIError as e:
            logging.error(f"Failed to send text to audit channel {TARGET_AUDIT_CHANNEL_ID}: {e}") # pylint: disable=logging-fstring-interpolation
    else:
        logging.warning("TARGET_AUDIT_CHANNEL_ID not set. Audit message not sent.")

async def log_to_audit_channel_async(text: str):
    """
    Creates a temporary Bot instance to send a message to the audit channel.
    Useful for logging from outside the main bot's context (e.g., an API).
    """
    credentials = Credentials()
    bot_token = credentials.get_bot_token()

    if not bot_token:
        logging.error("Cannot log to audit channel: BOT_TOKEN is not configured.")
        return
    if not TARGET_AUDIT_CHANNEL_ID:
        logging.error("Cannot log to audit channel: TARGET_AUDIT_CHANNEL_ID is not configured.")
        return

    bot = Bot(token=bot_token)
    try:
        await send_text_to_audit_channel(bot, text, parse_mode="HTML")
    finally:
        await bot.session.close()


def _create_bot_deeplink_html(address: str, bot_username: str) -> str:
    """Creates a t.me deeplink for a given address, formatted as an HTML link."""
    deeplink_url = f"https://t.me/{bot_username}?start={html.quote(address)}" # Address in start param should also be quoted if it can have special chars
    return f'<a href="{deeplink_url}">{html.quote(address)}</a>'

def markdown_to_html(markdown_text: str) -> str:
    """
    Converts a Markdown string to HTML using the markdown2 library,
    then sanitizes it to keep only Telegram-supported HTML tags.
    Allows raw HTML pass-through for our embedded deeplinks during markdown conversion.
    """
    if not markdown_text:
        return ""
    try:
        # Step 1: Convert Markdown to HTML
        # 'markdown2' allows HTML pass-through by default.
        html_output_from_markdown = markdown2.markdown(
            markdown_text,
            extras=["fenced-code-blocks", "tables", "smarty-pants", "break-on-newline", "code-friendly"]
        )

        if not html_output_from_markdown:
            return ""

        # Step 2: Sanitize HTML for Telegram
        # Define Telegram-supported tags
        supported_tags = {
            'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
            'a', 'code', 'pre', 'tg-spoiler'
        }
        supported_attrs = {
            'a': ['href'],
            'code': ['class'] 
        }

        soup = BeautifulSoup(html_output_from_markdown, 'lxml')

        for tag in soup.find_all(True): 
            if tag.name not in supported_tags:
                tag.unwrap()
            else:
                attrs = dict(tag.attrs)
                for attr_name in attrs:
                    if tag.name in supported_attrs and attr_name in supported_attrs[tag.name]:
                        if tag.name == 'a' and attr_name == 'href':
                            href_val = tag.get('href', '')
                            if not (href_val.startswith('http://') or \
                                    href_val.startswith('https://') or \
                                    href_val.startswith('tg://')):
                                # Remove potentially unsafe hrefs if they weren't created by our deeplinker
                                # This case should ideally be handled by what AI generates or what our deeplinker creates
                                # For now, we assume our deeplinker creates valid tg:// or https:// links
                                pass 
                        continue 
                    del tag[attr_name] 

        sanitized_html = str(soup)
        return sanitized_html.strip()

    except (TypeError, ValueError, AttributeError, LookupError, RecursionError) as e:
        logging.error(f"Error converting Markdown to HTML or sanitizing: {e}", exc_info=True)
        return html.quote(markdown_text)


def process_ai_markdown_to_html_with_deeplinks(markdown_text: str, bot_username: str) -> str:
    """
    Processes AI-generated Markdown text to HTML, converting detected crypto addresses
    into clickable deeplinks.
    1. Finds addresses in the original Markdown.
    2. Replaces these addresses with unique placeholders in the Markdown.
    3. Converts the Markdown (with placeholders) to HTML using markdown_to_html (which also sanitizes).
    4. Replaces the placeholders in the resulting HTML with the actual HTML <a> deeplink tags.
    """
    if not markdown_text:
        return ""
    if not bot_username:
        logging.warning("Bot username not provided for deeplink creation. Addresses will not be linked.")
        return markdown_to_html(markdown_text) # Convert Markdown to HTML without deeplinks

    placeholder_map = {}
    temp_text_for_markdown_processing = markdown_text

    # Find addresses to create placeholders
    detected_addresses_map = crypto_finder.find_addresses(markdown_text)
    unique_addresses = set()
    for blockchain_addresses in detected_addresses_map.values():
        for addr_val in blockchain_addresses:
            unique_addresses.add(addr_val)
    
    if not unique_addresses:
        # No addresses found, just convert Markdown to HTML
        return markdown_to_html(markdown_text)

    # Sort by length to avoid partial replacements of shorter addresses within longer ones
    sorted_addresses = sorted(list(unique_addresses), key=len, reverse=True)

    for i, addr_str in enumerate(sorted_addresses):
        placeholder = f"ZZCryptoAddressPH{i}ZZ" # MODIFIED placeholder format
        # _create_bot_deeplink_html is available in this file (helpers.py)
        placeholder_map[placeholder] = _create_bot_deeplink_html(addr_str, bot_username)
        
        try:
            # Replace in the text that will be parsed by Markdown
            # Use word boundaries to ensure full address replacement
            addr_pattern = rf"\b{re.escape(addr_str)}\b"
            temp_text_for_markdown_processing = re.sub(addr_pattern, placeholder, temp_text_for_markdown_processing)
        except re.error as e:
            logging.error(f"Regex error while creating placeholder for address {addr_str}: {e}")
            # If regex fails for a placeholder, that address might not get a deeplink,
            # but the process should continue.

    # Convert Markdown (with placeholders) to HTML. 
    # markdown_to_html includes sanitization based on Telegram-supported tags.
    html_with_placeholders = markdown_to_html(temp_text_for_markdown_processing)

    # Replace placeholders in the generated HTML with their <a> tag counterparts
    final_html_with_deeplinks = html_with_placeholders
    for placeholder, deeplink_html_content in placeholder_map.items():
        # Direct string replacement is used here. Placeholders are unique.
        final_html_with_deeplinks = final_html_with_deeplinks.replace(placeholder, deeplink_html_content)
            
    return final_html_with_deeplinks

# Helper function for manual MarkdownV2 escaping
def manual_escape_markdown_v2(text: str) -> str:
    """Manually escapes characters for Telegram MarkdownV2."""
    # Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r"[_*\[\]()~`>#+\-=|{}.!]" # Raw string for regex
    return re.sub(escape_chars, r"\\\g<0>", text)

async def send_typing_periodically(bot: Bot, chat_id: int, stop_event: asyncio.Event, interval: int = 4):
    """
    Sends 'typing' chat action periodically until the stop_event is set.

    :param bot: The Bot instance.
    :param chat_id: The ID of the chat to send the action to.
    :param stop_event: An asyncio.Event that signals when to stop sending the action.
    :param interval: The interval in seconds between sending the action.
    """
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except TelegramAPIError as e:
            logging.warning(f"Could not send periodic typing action to chat {chat_id}: {e}")
        except Exception as e_gen:
            # Log unexpected errors and break to prevent continuous failure
            logging.error(f"Unexpected error in send_typing_periodically for chat {chat_id}: {e_gen}", exc_info=True)
            break 
        
        try:
            # Wait for the interval or until the event is set, whichever comes first
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            # Timeout means the event was not set, so continue the loop
            continue
        except Exception as e_wait:
            logging.error(f"Unexpected error during wait in send_typing_periodically for chat {chat_id}: {e_wait}", exc_info=True)
            break # Exit loop on other wait errors
