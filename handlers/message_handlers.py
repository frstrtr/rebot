""""message_handlers.py
Contains handlers for processing messages that may contain crypto addresses,
stories, or other relevant content.
"""


import logging
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

from .states import AddressProcessingStates
from .helpers import _forward_to_audit_channel
from .address_processing import (
    _skip_memo_action,
    _process_memo_action,
    _handle_blockchain_reply,
    _scan_message_for_addresses_action,
)


async def handle_message_with_potential_crypto_address(
    message: Message, state: FSMContext
):
    """ "Handles incoming messages that may contain crypto addresses or require processing based on the current FSM state.
    This function checks the current FSM state and processes the message accordingly:
    - If the state is awaiting a memo, it processes the memo or skips it.
    - If the state is awaiting a blockchain choice, it handles the blockchain reply.
    - If no specific state is set, it scans the message for crypto addresses.
    If the message does not match the expected state (e.g., a non-memo reply when awaiting a memo), it forwards the message to an audit channel.
    """

    current_fsm_state = await state.get_state()
    if (
        current_fsm_state != AddressProcessingStates.awaiting_memo
    ):  # Audit non-memo replies
        await _forward_to_audit_channel(message)

    logging.info(
        "Handling message. Text: '%s', State: %s", message.text, current_fsm_state
    )

    if current_fsm_state == AddressProcessingStates.awaiting_memo:
        if message.text and message.text.lower() == "/skip":
            await _skip_memo_action(message, state)
        elif message.text:
            await _process_memo_action(message, state)
        else:
            await message.reply("Please provide a text memo or send /skip.")
    elif current_fsm_state == AddressProcessingStates.awaiting_blockchain:
        await _handle_blockchain_reply(
            message, state
        )  # This might be unused if only buttons are for blockchain choice
    else:  # No specific state, scan for addresses
        await _scan_message_for_addresses_action(message, state)


async def handle_story(message: Message) -> None:
    """Handles incoming stories. This function is triggered when a user sends a story.
    It logs the story content and can perform further actions, such as forwarding the story
    or acknowledging receipt.
    """

    logging.info("handle_story received a story from chat_id: %s", message.chat.id)
    try:
        # Example: Forward the story back or log its content
        # await message.forward(chat_id=message.chat.id) # Forwards the story
        story_data = (
            message.story.model_dump_json(indent=2)
            if message.story
            else "No story object"
        )
        logging.info("Story data: %s", story_data)
        # You can perform further actions with the story data here
        # For example, you might want to save it to a database or process it further
        # If you just want to acknowledge:
        # await message.answer("Story received!")
    except (TelegramAPIError, AttributeError, TypeError, ValueError) as e:
        logging.error("Error handling story: %s", e)
        await message.answer("Couldn't process the story.")
