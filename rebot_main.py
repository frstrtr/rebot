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
from handlers import (
    command_start_handler,
    handle_crypto_address,
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

    def setup_handlers(self):
        """Function to setup all the handlers for the bot"""

        self.rebot_dp.message.register(command_start_handler, CommandStart())

        self.rebot_dp.message.register(
            handle_crypto_address,
            StateFilter("*"),
        )
        self.rebot_dp.message.register(handle_story)
        self.rebot_dp.chat_member.register(member_status_update_handler)
        self.rebot_dp.edited_message.register(unhandled_updates_handler)


async def main():
    """Main function"""
    rebot = Rebot()
    # Add any additional setup or start logic here
    print("Bot created successfully", rebot)

    # And the run events dispatching
    await rebot.rebot_dp.start_polling(rebot.bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
