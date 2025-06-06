""" "State management for address processing in a Telegram bot using aiogram."""

from aiogram.fsm.state import State, StatesGroup


class AddressProcessingStates(StatesGroup):
    """State management for address processing in a Telegram bot using aiogram."""

    awaiting_blockchain = State()
    awaiting_ai_language_choice = State()  # New state for AI language selection
    awaiting_memo = State()
