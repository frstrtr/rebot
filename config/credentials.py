# credentials.py

from os import getenv

class Credentials:
    """Class to store the bot credentials"""

    def __init__(self):
        # Bot token can be obtained via https://t.me/BotFather
        self.bot_token = getenv("BOT_TOKEN")
        self.target_audit_channel_id = -1002624042904 # Added attribute

        if not self.bot_token:
            self.bot_token = self.read_token_from_file()

    def read_token_from_file(self):
        """Read the bot token from token.txt"""
        try:
            with open("./config/token.txt", "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Bot token not found. Please set the BOT_TOKEN environment variable or create a token.txt file."
            ) from exc

    def get_bot_token(self):
        """Function to get the bot token"""
        return self.bot_token

    def get_target_audit_channel_id(self):
        """Function to get the target audit channel ID"""
        return self.target_audit_channel_id
