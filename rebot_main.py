# rebot_main.py

"""
AIogram bot main module
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, StateFilter

from config.credentials import Credentials
from config.config import Config
from database import create_tables  # Import database functionality
from handlers import (
    command_start_handler,
    handle_message_with_potential_crypto_address,  # MODIFIED: Import the new handler name
    handle_story,
    member_status_update_handler,
    unhandled_updates_handler,
)


class Rebot:
    """Main bot class"""

    def __init__(self):
        self.credentials = Credentials()
        self.parse_mode = Config.PARSE_MODE
        self.rebot_dp = Dispatcher()
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
            logging.error(f"Failed to initialize database: {e}")  # MODIFIED: Use f-string for error logging
            raise

    def setup_handlers(self):
        """Function to setup all the handlers for the bot"""

        self.rebot_dp.message.register(command_start_handler, CommandStart())

        # MODIFIED: Register the new handler name for crypto addresses and FSM
        self.rebot_dp.message.register(
            handle_message_with_potential_crypto_address,
            StateFilter("*"),  # This allows the handler to manage states
        )

        # Ensure other handlers are registered appropriately
        # If handle_story is a general text handler, it might need to be
        # registered after the FSM handler or with more specific filters
        # to avoid interfering with the memo input process.
        self.rebot_dp.message.register(handle_story)
        self.rebot_dp.chat_member.register(member_status_update_handler)
        self.rebot_dp.edited_message.register(unhandled_updates_handler)


async def main():
    """Main function"""
    rebot = Rebot()
    logging.info("Bot created successfully: %s", rebot)  # MODIFIED: Use logging instead of print

    # And the run events dispatching
    await rebot.rebot_dp.start_polling(rebot.bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
