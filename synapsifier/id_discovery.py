import asyncio
import logging
import sys
import os # Added for file path operations

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.utils.deep_linking import decode_payload
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)

# --- Helper function to read from file ---
def read_from_file(filename):
    """Reads a single line of text from a file in the script's directory."""
    script_dir = os.path.dirname(__file__) # Gets the directory where the script is located
    file_path = os.path.join(script_dir, filename)
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()
            if not content:
                logging.warning(f"File '{filename}' is empty.")
                return None
            return content
    except FileNotFoundError:
        logging.error(f"Error: File '{filename}' not found in {script_dir}.")
        return None
    except Exception as e:
        logging.error(f"Error reading from file '{filename}': {e}")
        return None

# --- Configuration ---
BOT_TOKEN = read_from_file("bot_token.txt")
WEBAPP_URL = read_from_file("webapp_url.txt") # Ensure this file contains the full URL including the .html part

# --- Bot and Dispatcher Initialization ---
dp = Dispatcher()

# --- Handlers ---
@dp.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer("Hello! I'm your ID Finder bot.")
        return
    payload = decode_payload(command.args)
    await message.answer(
        f"Hello! Started with payload: {payload}. I'm your ID Finder bot. "
        "Use /myid to see your info via a Web App."
    )


@dp.message(CommandStart(deep_link=False))
async def cmd_start_no_deep_link(message: types.Message):
    await message.answer(
        "Hello! I'm the ID Finder bot.\n"
        "Use the /myid command to open a Web App and see your Telegram info.\n"
        "You can also forward a message or share a contact to get ID info directly."
    )

@dp.message(Command("myid"))
async def cmd_myid_webapp(message: types.Message):
    if not WEBAPP_URL: # Check if WEBAPP_URL was successfully read
        await message.answer("Web App URL is not configured. Please contact the bot admin.")
        return
    # The check for "YOUR_NGROK_HTTPS_URL" is less relevant if reading from file,
    # but can be kept if you want a placeholder in the file.
    if "YOUR_NGROK_HTTPS_URL" in WEBAPP_URL: # Example placeholder check
         await message.answer("Web App URL placeholder detected. Please contact the bot admin.")
         return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Show My Info",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ]
    )
    await message.answer(
        "Click the button below to open the Web App and see your Telegram ID and other details:",
        reply_markup=keyboard
    )


@dp.message(F.forward_from | F.contact)
async def handle_direct_id_request(message: types.Message):
    response_parts = []
    user_id = None
    username = None
    first_name = None
    last_name = None
    source_info = ""

    if message.forward_from:
        user_id = message.forward_from.id
        username = message.forward_from.username
        first_name = message.forward_from.first_name
        last_name = message.forward_from.last_name
        source_info = "from forwarded message"
    elif message.contact:
        user_id = message.contact.user_id
        phone_number = message.contact.phone_number
        first_name = message.contact.first_name
        last_name = message.contact.last_name
        source_info = "from shared contact"
        if phone_number:
            response_parts.append(f"Phone Number: `{phone_number}`")

    if user_id is not None:
        response_parts.insert(0, f"User ID: `{user_id}` ({source_info})")
        if username:
            response_parts.append(f"Username: @{username}")
        if first_name:
            response_parts.append(f"First Name: {first_name}")
        if last_name:
            response_parts.append(f"Last Name: {last_name}")
        await message.answer("\n".join(response_parts), parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            "I can only extract IDs from forwarded messages or shared contacts."
        )


@dp.message() # Fallback
async def handle_other_messages(message: types.Message):
    await message.answer(
        "I'm the ID Finder bot. Use /myid to see your info, or forward a message/share a contact."
    )


async def main() -> None:
    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN is not set. Please create 'bot_token.txt' with your bot token.")
        return
    if not WEBAPP_URL:
        logging.warning("WEBAPP_URL is not set. The /myid command might not work as expected. Please create 'webapp_url.txt'.")
        # Depending on your needs, you might want to exit if WEBAPP_URL is critical
        # return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
