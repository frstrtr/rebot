import logging
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import func

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

class AddressCheckResponse(BaseModel):
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

    is_ambiguous = False
    ambiguity_options = set()
    if len(detected_chains) == 1:
        single_chain = detected_chains.copy().pop()
        group = get_ambiguity_group_members(single_chain)
        if group:
            is_ambiguous = True
            ambiguity_options = group
    elif len(detected_chains) > 1:
        is_ambiguous = True
        ambiguity_options = detected_chains

    if is_ambiguous:
        return AddressCheckResponse(
            status="CLARIFICATION_NEEDED",
            message="Address format is ambiguous and could belong to multiple blockchains. Please clarify.",
            request_datetime=request_time,
            possible_blockchains=sorted(list(ambiguity_options))
        )

    blockchain = detected_chains.pop()
    
    from sqlalchemy.exc import SQLAlchemyError
    try:
        memos_query = db.query(CryptoAddress.notes).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower(),
            CryptoAddress.memo_type == MemoType.PUBLIC.value,
            CryptoAddress.notes.isnot(None),
            CryptoAddress.notes != ""
        ).all()
        public_memos = [memo[0] for memo in memos_query]
    except SQLAlchemyError as e:
        logging.error(f"API DB Error fetching memos for {request.crypto_address}: {e}")
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