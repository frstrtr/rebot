# rebot_main.py

"""
AIogram bot main module
"""

import asyncio
import logging
import sys
import contextvars  # ADDED

from aiogram import Bot, Dispatcher, BaseMiddleware  # MODIFIED: Added BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Update  # ADDED

from config.credentials import Credentials
from config.config import Config
from database import create_tables  # Import database functionality
from handlers import (
    command_start_handler,
    handle_message_with_potential_crypto_address,  # MODIFIED: Import the new handler name
    handle_story,
    member_status_update_handler,
    unhandled_updates_handler,
    checkmemo_handler,  # <-- Add this
)

# 1. Define Context Variable for user_id
user_id_context = contextvars.ContextVar("user_id_context", default="N/A")


# 2. Custom Logging Filter to add user_id to log records
class UserIdContextFilter(logging.Filter):
    def filter(self, record):
        record.user_id = (
            user_id_context.get()
        )  # Directly set from context, which has a default "N/A"
        return True


# 3. Aiogram Middleware to extract and set user_id in context
class UserIdLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        user_id_to_log = "N/A"

        if event.message and event.message.from_user:
            user_id_to_log = event.message.from_user.id
        elif event.edited_message and event.edited_message.from_user:
            user_id_to_log = event.edited_message.from_user.id
        elif event.channel_post and event.channel_post.from_user:
            user_id_to_log = (
                event.channel_post.from_user.id
                if event.channel_post.from_user
                else "Channel"
            )
        elif event.edited_channel_post and event.edited_channel_post.from_user:
            user_id_to_log = (
                event.edited_channel_post.from_user.id
                if event.edited_channel_post.from_user
                else "Channel"
            )
        elif event.inline_query and event.inline_query.from_user:
            user_id_to_log = event.inline_query.from_user.id
        elif event.chosen_inline_result and event.chosen_inline_result.from_user:
            user_id_to_log = event.chosen_inline_result.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            user_id_to_log = event.callback_query.from_user.id
        elif event.shipping_query and event.shipping_query.from_user:
            user_id_to_log = event.shipping_query.from_user.id
        elif event.pre_checkout_query and event.pre_checkout_query.from_user:
            user_id_to_log = event.pre_checkout_query.from_user.id
        elif event.poll_answer and event.poll_answer.user:
            user_id_to_log = event.poll_answer.user.id
        elif event.my_chat_member and event.my_chat_member.from_user:
            user_id_to_log = event.my_chat_member.from_user.id
        elif event.chat_member and event.chat_member.from_user:
            user_id_to_log = event.chat_member.from_user.id
        elif event.chat_join_request and event.chat_join_request.from_user:
            user_id_to_log = event.chat_join_request.from_user.id

        token = user_id_context.set(str(user_id_to_log))  # Ensure it's a string
        try:
            return await handler(event, data)
        finally:
            user_id_context.reset(token)


class Rebot:
    """Main bot class"""

    def __init__(self):
        self.credentials = Credentials()
        self.parse_mode = Config.PARSE_MODE
        self.rebot_dp = Dispatcher()
        # Register middleware for all updates
        self.rebot_dp.update.outer_middleware(
            UserIdLoggingMiddleware()
        )  # ADDED MIDDLEWARE REGISTRATION
        self.bot = self.create_bot()
        self.setup_handlers()
        self.init_database()  # Initialize the database

    def create_bot(self):
        """Function to create the bot"""
        token = self.credentials.get_bot_token()
        if token is None:
            raise ValueError("Bot token must not be None.")
        return Bot(
            token=token,
            default=DefaultBotProperties(
                parse_mode=self.parse_mode,
            ),
        )

    def init_database(self):
        """Initialize the database"""
        try:
            create_tables()
            logging.info("Database initialized successfully")
        except Exception as e:
            logging.error(
                f"Failed to initialize database: {e}"
            )  # MODIFIED: Use f-string for error logging
            raise

    def setup_handlers(self):
        """Function to setup all the handlers for the bot"""

        self.rebot_dp.message.register(command_start_handler, CommandStart())
        self.rebot_dp.message.register(
            checkmemo_handler,
            lambda m: m.text and m.text.startswith("/checkmemo"),
        )
        self.rebot_dp.message.register(
            handle_message_with_potential_crypto_address,
            StateFilter("*"),
        )
        self.rebot_dp.message.register(handle_story)
        self.rebot_dp.chat_member.register(member_status_update_handler)
        self.rebot_dp.edited_message.register(unhandled_updates_handler)


async def main():
    """Main function"""
    rebot = Rebot()
    logging.info(
        "Bot created successfully: %s", rebot
    )  # MODIFIED: Use logging instead of print

    # And the run events dispatching
    await rebot.rebot_dp.start_polling(rebot.bot)


if __name__ == "__main__":
    # 1. Create the filter and formatter
    custom_filter = UserIdContextFilter()
    log_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - UserID: %(user_id)s - %(message)s"
    )

    # 2. Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    # Clear existing handlers from root logger (important if basicConfig was called before or by libraries)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_handler = logging.StreamHandler(sys.stdout)
    root_handler.setFormatter(log_formatter)
    root_handler.addFilter(custom_filter)
    root_logger.addHandler(root_handler)

    # 3. Configure Aiogram loggers similarly to ensure they use the new handler/formatter/filter
    #    This is important if they have their own default handlers that might not include user_id
    aiogram_loggers_to_configure = [
        "aiogram.event",
        "aiogram.dispatcher",
        "aiogram.bot",
    ]
    for logger_name in aiogram_loggers_to_configure:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)  # Or whatever level you prefer for these
        if (
            logger.hasHandlers()
        ):  # Clear existing handlers to avoid duplicate messages or old formats
            logger.handlers.clear()
        logger.addHandler(root_handler)  # Add the same configured handler
        logger.propagate = False  # Prevent aiogram logs from being handled again by root if you only want one output

    asyncio.run(main())
