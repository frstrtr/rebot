"""
orchestration.py
Contains the logic to orchestrate the different steps of address processing.
"""
import logging
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import AiogramError
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal, save_crypto_address

# Import functions from other refactored modules
# To avoid circular imports at module load time, these might need to be
# imported within the function or type-hinted as strings if issues arise.
from .blockchain_clarification import _ask_for_blockchain_clarification
from .memo_management import _prompt_for_next_memo


async def _orchestrate_next_processing_step(
    message_to_reply_to: Message, state: FSMContext
):
    data = await state.get_data()
    pending_blockchain_clarification = data.get("pending_blockchain_clarification", [])
    # This is populated AFTER clarification or for unambiguous single detections
    addresses_for_action_prompt_details = data.get("addresses_for_memo_prompt_details", []) # Renamed for clarity
    current_scan_db_message_id = data.get("current_scan_db_message_id")

    if not current_scan_db_message_id:
        logging.error("Cannot orchestrate: current_scan_db_message_id not found in FSM state.")
        await message_to_reply_to.answer(
            "Internal error (missing message context). Try scanning again."
        )
        await state.clear()
        return

    db = SessionLocal()
    try:
        if pending_blockchain_clarification:
            item_to_clarify = pending_blockchain_clarification.pop(0) # Get the first item
            await state.update_data(
                current_item_for_blockchain_clarification=item_to_clarify,
                pending_blockchain_clarification=pending_blockchain_clarification, # Update the list
            )
            # Now call the function to ask for clarification
            await _ask_for_blockchain_clarification(message_to_reply_to, item_to_clarify, state)
        
        elif addresses_for_action_prompt_details: # This means clarification is done, or was not needed.
            # This list contains items like {"address": "0x123", "blockchain": "ethereum"}
            # These addresses need to be saved to the DB if not already, and then prompted for memo.
            
            ready_for_memo_prompt_with_ids = []
            for detail in addresses_for_action_prompt_details:
                addr_str, blockchain = detail["address"], detail["blockchain"]
                # Save the address now that its blockchain is confirmed
                db_crypto_address = save_crypto_address(db, current_scan_db_message_id, addr_str, blockchain)
                if db_crypto_address and db_crypto_address.id is not None:
                    ready_for_memo_prompt_with_ids.append({
                        "id": db_crypto_address.id, # DB ID of the CryptoAddress record
                        "address": addr_str,
                        "blockchain": blockchain,
                    })
                else:
                    logging.error(f"Failed to save address {addr_str} on {blockchain} or get its ID during orchestration.") # pylint: disable=logging-fstring-interpolation
            
            # Clear the list from FSM as we are processing it now
            await state.update_data(addresses_for_memo_prompt_details=[]) 

            if ready_for_memo_prompt_with_ids:
                # Now call _prompt_for_next_memo with the list of successfully saved addresses
                # _prompt_for_next_memo will handle iterating through this list.
                await _prompt_for_next_memo(message_to_reply_to, state, ready_for_memo_prompt_with_ids)
            elif not pending_blockchain_clarification: # No more clarifications and nothing to prompt for memo
                logging.info("No addresses successfully saved to prompt for memo, and no pending clarifications.")
                await message_to_reply_to.answer("Finished processing addresses.")
                await state.clear()
        
        else: # No pending clarifications and no addresses ready for memo prompt
            await state.clear()
            
    except (SQLAlchemyError, AiogramError, ValueError, TypeError, KeyError, AttributeError) as e:
        logging.exception(f"Error in _orchestrate_next_processing_step: {e}") # pylint: disable=logging-fstring-interpolation 
        await message_to_reply_to.answer("An error occurred during processing orchestration.") 
        await state.clear() # Clear state on error
    finally:
        # await state.clear() # Clear state on error or successful completion (if not cleared elsewhere)
        if db.is_active:
            db.close()