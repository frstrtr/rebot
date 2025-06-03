import asyncio
import logging
import sys
# import uuid # No longer needed if removing inline query

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.utils.deep_linking import decode_payload
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
# from aiogram.exceptions import TelegramAPIError # Keep if other error handling needs it
from aiogram.types import (
    # InlineQuery, # Removing inline mode specifics
    # InlineQueryResultArticle,
    # InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    # CallbackQuery,
    WebAppInfo # New import for Web Apps
)

# --- Configuration ---
BOT_TOKEN = "7509730696:AAF62kdNXpuwNMtqCyJ81vpwvWm_Nvo_2PE" # Your bot token
# IMPORTANT: Replace with your ngrok HTTPS URL
WEBAPP_URL = "https://7581-34-35-78-201.ngrok-free.app/user_id_display.html"

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

@dp.message(Command("myid")) # New command to launch the Web App
async def cmd_myid_webapp(message: types.Message):
    if not WEBAPP_URL or "YOUR_NGROK_HTTPS_URL" in WEBAPP_URL:
        await message.answer("Web App URL is not configured correctly by the bot admin.")
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


# --- Inline Mode Handlers (Commented out or removed as requested) ---
# @dp.inline_query()
# async def handle_inline_query(inline_query: InlineQuery):
#     # ... previous inline logic ...
#     pass

# @dp.callback_query(F.data == "reveal_my_id")
# async def cq_reveal_my_id(callback_query: CallbackQuery):
#     # ... previous callback logic ...
#     pass


@dp.message() # Fallback
async def handle_other_messages(message: types.Message):
    await message.answer(
        "I'm the ID Finder bot. Use /myid to see your info, or forward a message/share a contact."
    )


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
