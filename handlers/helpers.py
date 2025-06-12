"""helpers.py - Contains utility functions for handling messages
and forwarding them to an audit channel."""

import logging, re
from aiogram import html, Bot 
from aiogram.types import Message, User 
from aiogram.exceptions import TelegramAPIError
import asyncio # Added for asyncio operations
import logging # Added for logging within the helper
import markdown as  markdown2 # Added for Markdown to HTML conversion
from bs4 import BeautifulSoup # Added for HTML sanitization
from .common import TARGET_AUDIT_CHANNEL_ID, AMBIGUOUS_CHAIN_GROUPS, crypto_finder 

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
            await bot.send_message(TARGET_AUDIT_CHANNEL_ID, text, parse_mode=parse_mode, disable_web_page_preview=True)
            logging.info(f"Sent audit text to channel {TARGET_AUDIT_CHANNEL_ID}") # pylint: disable=logging-fstring-interpolation
        except TelegramAPIError as e:
            logging.error(f"Failed to send text to audit channel {TARGET_AUDIT_CHANNEL_ID}: {e}") # pylint: disable=logging-fstring-interpolation
    else:
        logging.warning("TARGET_AUDIT_CHANNEL_ID not set. Audit message not sent.")

def _create_bot_deeplink_html(address: str, bot_username: str) -> str:
    """
    Creates an HTML deeplink for a given address that starts a chat with the bot
    and passes the address via the start parameter.
    """
    deeplink_url = f"https://t.me/{bot_username}?start={address}"
    return f'<a href="{deeplink_url}">{html.quote(address)}</a>' # Address in link text is HTML quoted

def replace_addresses_with_deeplinks(report_text: str, bot_username: str) -> str:
    """
    Finds all cryptocurrency addresses in the report_text and replaces them
    with HTML deeplinks that point back to the bot.
    This function expects plain text or Markdown text as input, and will output
    text with HTML <a> tags embedded.

    Args:
        report_text: The AI-generated report text (plain or Markdown).
        bot_username: The username of the bot (without '@').

    Returns:
        The report text with address occurrences replaced by HTML deeplink tags.
    """
    if not report_text:
        return ""
    if not bot_username:
        logging.warning("Bot username not provided for deeplink creation. Addresses will not be linked.")
        return report_text # Return original text if no bot_username

    detected_addresses_map = crypto_finder.find_addresses(report_text)
    
    unique_addresses = set()
    for blockchain_addresses in detected_addresses_map.values():
        for addr in blockchain_addresses:
            unique_addresses.add(addr)
    
    if not unique_addresses:
        return report_text # No addresses found, return original text

    # Sort addresses by length in descending order to avoid issues with
    # shorter addresses being substrings of longer ones during replacement.
    sorted_addresses = sorted(list(unique_addresses), key=len, reverse=True)
    
    modified_report_text = report_text # Start with the original report text

    for address in sorted_addresses:
        deeplink_html = _create_bot_deeplink_html(address, bot_username)
        # Regex to find the plain address as a whole word.
        # This will replace the plain address string with its HTML link version.
        # Ensure 'address' itself doesn't contain regex special characters or escape them.
        # For crypto addresses, direct string replacement or a simple \b might be okay.
        try:
            # Using re.escape on the address to handle any special characters it might contain,
            # though typical crypto addresses don't have many.
            pattern = rf"\b{re.escape(address)}\b" 
            modified_report_text = re.sub(pattern, deeplink_html, modified_report_text)
        except re.error as e:
            logging.error(f"Regex error while replacing address {address}: {e}")
            # Continue without replacing this specific address if regex fails
            
    return modified_report_text

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
        # Note: <tg-spoiler> is a special Telegram tag.
        # <pre><code class="language-python"> is also supported.
        supported_tags = {
            'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
            'a', 'code', 'pre', 'tg-spoiler'
        }
        # Attributes supported for <a> tag
        supported_attrs = {
            'a': ['href'],
            'code': ['class'] # For <code class="language-..."> inside <pre>
        }

        soup = BeautifulSoup(html_output_from_markdown, 'lxml')

        for tag in soup.find_all(True): # Find all tags
            if tag.name not in supported_tags:
                # If tag is not supported, unwrap it (remove tag, keep content)
                tag.unwrap()
            else:
                # If tag is supported, remove any unsupported attributes
                attrs = dict(tag.attrs)
                for attr_name in attrs:
                    if tag.name in supported_attrs and attr_name in supported_attrs[tag.name]:
                        # Special handling for tg://user?id= links if needed, but general href is fine
                        if tag.name == 'a' and attr_name == 'href':
                            if not (tag['href'].startswith('http://') or \
                                    tag['href'].startswith('https://') or \
                                    tag['href'].startswith('tg://')):
                                # Potentially unsafe href, remove attribute or tag
                                # For simplicity, let's assume replace_addresses_with_deeplinks creates safe links
                                pass 
                        continue # Attribute is supported
                    del tag[attr_name] # Remove unsupported attribute

        # Get the sanitized HTML string
        # Using .decode_contents() or str(soup) might be slightly different.
        # str(soup) usually gives the full HTML document structure.
        # We want the content of the body if soup added html/body tags,
        # or just the processed string if it didn't.
        # If markdown2 produces a fragment, str(soup) is fine.
        sanitized_html = str(soup)
        
        # Telegram expects newlines to be <br> or actual newlines.
        # markdown2 with "break-on-newline" might handle this, but ensure consistency.
        # Often, replacing \n with <br /> (if not already done by markdown2) is needed
        # AFTER sanitization if newlines are meant to be line breaks.
        # However, Telegram's HTML parser usually respects actual newline characters too.
        # Let's assume markdown2 handles newlines appropriately for now.

        return sanitized_html.strip()

    except (TypeError, ValueError, AttributeError, LookupError, RecursionError) as e:
        logging.error(f"Error converting Markdown to HTML or sanitizing: {e}", exc_info=True)
        # Fallback to HTML quoting the original Markdown text if conversion/sanitization fails
        return html.quote(markdown_text)

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
