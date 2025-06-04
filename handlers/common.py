"""Handles incoming messages that may contain crypto addresses or require processing based on the current FSM state."""

from config.credentials import Credentials
from synapsifier.crypto_address import CryptoAddressFinder
from config.config import Config  # For MAX_TELEGRAM_MESSAGE_LENGTH if used commonly

credentials = Credentials()
TARGET_AUDIT_CHANNEL_ID = credentials.get_target_audit_channel_id()
crypto_finder = CryptoAddressFinder()
MAX_TELEGRAM_MESSAGE_LENGTH = Config.MAX_TELEGRAM_MESSAGE_LENGTH
EXPLORER_CONFIG = Config.EXPLORER_CONFIG
AMBIGUOUS_CHAIN_GROUPS = Config.AMBIGUOUS_CHAIN_GROUPS
ADMINS = Config.ADMINS
