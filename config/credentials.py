"""credentials.py
Handles bot credentials and configuration for the Telegram bot.
"""

from os import getenv
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()


class Credentials:
    """Class to store the bot credentials"""

    def __init__(self):
        # Bot token can be obtained via https://t.me/BotFather
        self.bot_token = getenv("BOT_TOKEN")
        self.target_audit_channel_id_str = getenv("TARGET_AUDIT_CHANNEL_ID")

        if not self.bot_token or not self.target_audit_channel_id_str:
            raise RuntimeError(
                "Bot token or target audit channel ID not found. Please set them in the .env file."
            )

    def get_bot_token(self):
        """Function to get the bot token"""
        return self.bot_token

    def get_target_audit_channel_id(self):
        """Function to get the target audit channel ID"""
        return self.target_audit_channel_id_str
