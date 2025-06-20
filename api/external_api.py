import logging
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError

# Adjust path to import from the parent project directory
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config
from database import SessionLocal
from database.models import CryptoAddress, MemoType
from synapsifier.crypto_address import CryptoAddressFinder
from handlers.helpers import get_ambiguity_group_members

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Rebot External API",
    description="API to check crypto addresses, retrieve public memos, and get explorer links.",
    version="1.0.0"
)

# --- API Key Security ---
API_KEY_NAME = "X-API-KEY"
api_key_header = Security(APIKeyHeader(name=API_KEY_NAME, auto_error=False))

async def get_api_key(api_key: str = api_key_header):
    """ Validates the API key provided in the request header.
    Raises HTTPException if the key is invalid or not set.
    """
    if not Config.EXTERNAL_API_SECRET:
        logging.critical("EXTERNAL_API_SECRET is not set in the configuration. API is insecure.")
        raise HTTPException(status_code=500, detail="API secret is not configured on the server.")
    if api_key == Config.EXTERNAL_API_SECRET:
        return api_key
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

# --- Pydantic Models for Request and Response ---
class AddressCheckRequest(BaseModel):
    crypto_address: str
    request_by_telegram_id: int = Field(..., gt=0, le=100000000, description="Telegram ID of the user making the request.")
    provided_by_telegram_id: int = Field(..., gt=0, le=100000000, description="Telegram ID of the user who provided the address.")
    blockchain_type: Optional[str] = Field(None, description="Optional: Specify the blockchain to resolve ambiguity (e.g., 'ethereum', 'bsc').")

class AddressCheckResponse(BaseModel):
    """Response model for the address check API."""
    status: str = Field(..., description="OK, ERROR, or CLARIFICATION_NEEDED")
    message: Optional[str] = Field(None, description="Error message or status description.")
    request_datetime: datetime = Field(..., description="Timestamp of the request in UTC.")
    bot_deeplink: Optional[str] = Field(None, description="A raw t.me URL to check the address with the bot.")
    blockchain_explorer_link: Optional[str] = Field(None, description="Link to a block explorer for the address.")
    public_memos: Optional[List[str]] = Field(None, description="A list of public memos associated with the address.")
    possible_blockchains: Optional[List[str]] = Field(None, description="List of possible blockchains if clarification is needed.")

# --- Dependency for DB Session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoint ---
@app.post("/check-address", response_model=AddressCheckResponse, dependencies=[Depends(get_api_key)])
async def check_address(request: AddressCheckRequest, db: Session = Depends(get_db)):
    """
    Validates a crypto address, retrieves public memos, and provides relevant links.
    """
    request_time = datetime.now(timezone.utc)
    crypto_finder = CryptoAddressFinder()
    
    detected_map = crypto_finder.find_addresses(request.crypto_address)
    
    if not detected_map:
        return AddressCheckResponse(
            status="ERROR",
            message=f"'{request.crypto_address}' is not a valid or recognized crypto address format.",
            request_datetime=request_time
        )

    detected_chains: Set[str] = {chain for chain, addrs in detected_map.items() if request.crypto_address in addrs}
    
    blockchain: Optional[str] = None
    ambiguity_options: Set[str] = set()

    if len(detected_chains) == 1:
        single_chain = detected_chains.copy().pop()
        group = get_ambiguity_group_members(single_chain)
        if group:
            ambiguity_options = group
        else:
            blockchain = single_chain
    elif len(detected_chains) > 1:
        ambiguity_options = detected_chains

    if ambiguity_options:
        if request.blockchain_type:
            if request.blockchain_type.lower() in ambiguity_options:
                blockchain = request.blockchain_type.lower()
            else:
                return AddressCheckResponse(
                    status="ERROR",
                    message=f"Provided blockchain_type '{request.blockchain_type}' is not a valid option for this address. Possible options: {sorted(list(ambiguity_options))}",
                    request_datetime=request_time
                )
        else:
            return AddressCheckResponse(
                status="CLARIFICATION_NEEDED",
                message="Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
                request_datetime=request_time,
                possible_blockchains=sorted(list(ambiguity_options))
            )
    
    if not blockchain:
        # This case should not be hit if logic is correct, but it's a safeguard.
        # Add logging to be sure
        logging.error(f"API_LOGIC_ERROR: Could not resolve a single blockchain for address '{request.crypto_address}' from detected chains: {detected_chains}. Ambiguity options were: {ambiguity_options}")
        return AddressCheckResponse(
            status="ERROR",
            message=f"Could not determine a single blockchain for '{request.crypto_address}'.",
            request_datetime=request_time
        )
    
    try:
        # --- Extensive Logging for DB Query ---
        logging.info("-------------------- API DB QUERY DEBUG START --------------------")
        logging.info(f"[API_DB_DEBUG] File: api/external_api.py -> check_address()")
        logging.info(f"[API_DB_DEBUG] Preparing to query for public memos.")
        logging.info(f"[API_DB_DEBUG] PARAMETER address: '{request.crypto_address}'")
        logging.info(f"[API_DB_DEBUG] PARAMETER blockchain: '{blockchain}'")

        # 1. Create the base query EXACTLY matching the working logic in memo_management.py
        logging.info("[API_DB_DEBUG] Using func.lower() for case-insensitive comparison to mirror the bot's working implementation.")
        query = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower(),
            CryptoAddress.notes.isnot(None),
            CryptoAddress.notes != ""
        )
        logging.info(f"[API_DB_DEBUG] Step 1: Base query constructed.")
        logging.info(f"[API_DB_DEBUG] SQL for base query (approximate): {str(query.statement.compile(compile_kwargs={'literal_binds': True}))}")

        # 2. Apply the public scope filter to the existing query object.
        query = query.filter(
            or_(
                CryptoAddress.memo_type == MemoType.PUBLIC.value,
                CryptoAddress.memo_type.is_(None)
            )
        )
        logging.info(f"[API_DB_DEBUG] Step 2: Public memo filter applied (memo_type is 'public' or NULL).")
        logging.info(f"[API_DB_DEBUG] SQL for final query (approximate): {str(query.statement.compile(compile_kwargs={'literal_binds': True}))}")
        
        # 3. Execute the final query with ordering.
        logging.info("[API_DB_DEBUG] Step 3: Executing query against the database...")
        memo_results = query.order_by(CryptoAddress.id.desc()).all()
        logging.info(f"[API_DB_DEBUG] Step 4: Query executed. Found {len(memo_results)} raw results.")

        # 4. Log the raw results for inspection.
        if not memo_results:
            logging.warning(f"[API_DB_DEBUG] No matching records found in 'crypto_addresses' table for the given criteria.")
        else:
            for i, memo in enumerate(memo_results):
                logging.info(f"[API_DB_DEBUG]   - Result [{i}]: ID={memo.id}, Addr='{memo.address}', Chain='{memo.blockchain}', Type='{memo.memo_type}', Notes='{memo.notes[:70]}...'")

        # 5. Extract the notes.
        public_memos = [memo.notes for memo in memo_results if memo.notes]
        logging.info(f"[API_DB_DEBUG] Step 5: Extracted {len(public_memos)} notes from raw results.")
        logging.info("-------------------- API DB QUERY DEBUG END ----------------------")

    except SQLAlchemyError as e:
        logging.error(f"API DB Error fetching memos for {request.crypto_address}: {e}", exc_info=True)
        return AddressCheckResponse(status="ERROR", message="A database error occurred while fetching memos.", request_datetime=request_time)

    explorer_link = Config.EXPLORER_CONFIG.get(blockchain, {}).get("url_template", "").format(address=request.crypto_address) or None

    bot_deeplink = f"https://t.me/{Config.BOT_USERNAME}?start={request.crypto_address}" if Config.BOT_USERNAME else None
    if not bot_deeplink:
        logging.warning("BOT_USERNAME not set in Config, cannot generate deeplink.")

    return AddressCheckResponse(
        status="OK",
        message="Address details retrieved successfully.",
        request_datetime=request_time,
        bot_deeplink=bot_deeplink,
        blockchain_explorer_link=explorer_link,
        public_memos=public_memos if public_memos else []
    )