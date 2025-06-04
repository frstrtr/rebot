"""
addrss_processing.py
Contains functions for processing crypto addresses in messages,
including scanning messages for addresses, handling blockchain clarifications,
and prompting for memos.
"""

# import logging  # Ensure logging is imported

# from typing import Optional # Import Optional for type hinting
# from aiogram import html, types
# from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
# from aiogram.fsm.context import FSMContext
# from aiogram.exceptions import TelegramAPIError
# from sqlalchemy import func, or_  # Add this import for OR conditions in SQLAlchemy
# from sqlalchemy.orm import Session

# from database import (
#     SessionLocal,
#     save_message,
#     save_crypto_address,
#     get_or_create_user,  # Import get_or_create_user
#     CryptoAddress,
#     CryptoAddressStatus,
#     # MemoType, # Import MemoType # No longer imported directly from 'database'
# )
# from database.models import MemoType  # Assuming MemoType is in database.models
from .common import (
    crypto_finder,
    TARGET_AUDIT_CHANNEL_ID,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    EXPLORER_CONFIG,
)
from .states import AddressProcessingStates
from .helpers import get_ambiguity_group_members
from utils.colors import Colors  # Adjust relative import based on your structure

from .address_scanning import _scan_message_for_addresses_action
from .blockchain_clarification import (
    _ask_for_blockchain_clarification,
    _handle_blockchain_reply,
)  # If called directly by a handler
from .memo_management import (
    _display_memos_for_address_blockchain,
    _prompt_for_next_memo,
    _process_memo_action,
    _skip_memo_action,
)  # If called directly
from .orchestration import _orchestrate_next_processing_step
from .action_prompt import _send_action_prompt
