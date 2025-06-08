"""
blockchain_clarification.py
Manages asking for and handling blockchain clarification from the user.
"""
import logging
from aiogram import html, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, CryptoAddress
from .common import EXPLORER_CONFIG
from .states import AddressProcessingStates

async def _ask_for_blockchain_clarification(
    message_to_reply_to: Message, item_to_clarify: dict, state: FSMContext
):
    address = item_to_clarify["address"]
    detected_options = item_to_clarify.get("detected_on_options", []) # Ensure detected_options is a list
    
    keyboard_buttons_rows = []
    db: Session = SessionLocal()
    try:
        if detected_options and detected_options != ["Unknown"]: # Don't show options if it's just "Unknown"
            current_row = []
            for i, option in enumerate(detected_options):
                if not isinstance(option, str): # Skip if option is not a string
                    logging.warning(f"Skipping non-string option in detected_options: {option}") # pylint: disable=logging-fstring-interpolation    
                    continue

                memo_count = (
                    db.query(func.count(CryptoAddress.id)) # pylint: disable=not-callable
                    .filter(
                        func.lower(CryptoAddress.address) == address.lower(),
                        func.lower(CryptoAddress.blockchain) == option.lower(),
                        CryptoAddress.notes.isnot(None),
                        CryptoAddress.notes != "",
                    )
                    .scalar() or 0
                )
                button_text_parts = [option.capitalize()]
                # Example: Add token standard if available in EXPLORER_CONFIG
                # if option.lower() in EXPLORER_CONFIG:
                #     chain_config = EXPLORER_CONFIG[option.lower()]
                #     token_standard = chain_config.get("token_standard_display")
                #     if token_standard:
                #         button_text_parts.append(f"({token_standard})")
                if memo_count > 0:
                    button_text_parts.append(f"[{memo_count} memo{'s' if memo_count > 1 else ''}]")
                
                final_button_text = " ".join(button_text_parts)
                current_row.append(
                    InlineKeyboardButton(
                        text=f"⛓️ {final_button_text}",
                        callback_data=f"clarify_bc:chosen:{option.lower()}",
                    )
                )
                if len(current_row) == 2 or i == len(detected_options) - 1:
                    keyboard_buttons_rows.append(current_row)
                    current_row = []
            if current_row: # Append any remaining buttons
                 keyboard_buttons_rows.append(current_row)
    finally:
        if db.is_active:
            db.close()

    keyboard_buttons_rows.append(
        [InlineKeyboardButton(text="⏭️ Skip this address", callback_data="clarify_bc:skip")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons_rows)

    prompt_text_base = f"For address: <code>{html.quote(address)}</code>\n"
    if detected_options and detected_options != ["Unknown"] and keyboard_buttons_rows[:-1]: # Check if actual options were added
        prompt_text = prompt_text_base + "Which blockchain network does this address belong to?\nPlease select from the options below."
    else:
        prompt_text = prompt_text_base + "I couldn't auto-detect specific blockchain networks. If you know it, you might need to resend the address with more context. For now, you can skip."

    await message_to_reply_to.answer(prompt_text, reply_markup=keyboard, parse_mode="HTML")
    # Store the item being clarified in the FSM state
    if item_to_clarify: # Add a check to ensure item_to_clarify is not None
        await state.update_data(current_item_for_blockchain_clarification=item_to_clarify.copy()) # Store a copy
        logging.info(f"Stored for clarification (user {message_to_reply_to.from_user.id if message_to_reply_to.from_user else 'UnknownUser'}): {item_to_clarify}")
    else:
        logging.warning(f"item_to_clarify is None or empty, not storing in FSM for user {message_to_reply_to.from_user.id if message_to_reply_to.from_user else 'UnknownUser'}.")
        # Handle cases where item_to_clarify might be None, perhaps by not proceeding or logging an error.
        # For now, just logging and not setting if None.
    await state.set_state(AddressProcessingStates.awaiting_blockchain)


async def _handle_blockchain_reply(message: Message, state: FSMContext):
    # Import _orchestrate_next_processing_step here, inside the function
    from .orchestration import _orchestrate_next_processing_step 

    # This function is noted as potentially unused if all clarification is via callbacks.
    # If used, it assumes user types the blockchain name.
    data = await state.get_data()
    item_being_clarified = data.get("current_item_for_blockchain_clarification")

    if not item_being_clarified:
        logging.info("Received blockchain reply but no item_being_clarified in state. Ignoring.")
        return

    addresses_for_memo_prompt_details = data.get("addresses_for_memo_prompt_details", [])
    chosen_blockchain = (message.text or "").strip().lower()

    if not chosen_blockchain:
        await message.reply(
            "Blockchain name cannot be empty. Please try again, or use the skip button."
        )
        return

    addresses_for_memo_prompt_details.append(
        {"address": item_being_clarified["address"], "blockchain": chosen_blockchain}
    )
    await state.update_data(
        addresses_for_memo_prompt_details=addresses_for_memo_prompt_details,
        current_item_for_blockchain_clarification=None, # Clear the item being clarified
        # pending_blockchain_clarification is handled by orchestrator
    )
    await message.reply(
        f"Noted: <code>{html.quote(item_being_clarified['address'])}</code> will be associated with <b>{html.quote(chosen_blockchain.capitalize())}</b>.",
        parse_mode="HTML",
    )
    await state.set_state(None) # Clear specific state, orchestrator will take over
    await _orchestrate_next_processing_step(message, state)