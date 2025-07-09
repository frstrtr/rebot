"""
Rebot External API
This module provides an external API for checking crypto addresses, 
retrieving public memos, analyzing scam potential,
and generating blockchain explorer links.
"""

import logging
from fastapi import FastAPI, Depends, HTTPException, Security, Request
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
from handlers.helpers import get_ambiguity_group_members, log_to_audit_channel_async
# --- New Imports ---
import json
import asyncio
from utils.tronscan import TronScanAPI
from genai.vertex_ai_client import VertexAIClient

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Rebot External API",
    description="API to check crypto addresses, retrieve public memos, analyze scam potential, and get explorer links.",
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
    request_by_telegram_id: int = Field(..., gt=0, le=10000000000, description="Telegram ID of the user making the request.")
    provided_by_telegram_id: int = Field(..., gt=0, le=10000000000, description="Telegram ID of the user who provided the address.")
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
    risk_score: Optional[float] = Field(None, description="An AI-generated risk score for TRON addresses (0.0 to 1.0).")
    risk_score_updated_at: Optional[datetime] = Field(None, description="Timestamp when the risk score was last updated in UTC.")

class ScamReportRequest(BaseModel):
    crypto_address: str
    request_by_telegram_id: int = Field(..., gt=0, le=10000000000, description="Telegram ID of the user making the request.")
    blockchain_type: Optional[str] = Field(None, description="Optional: Specify the blockchain to resolve ambiguity (e.g., 'ethereum', 'bsc').")

class ScamReportResponse(BaseModel):
    """Response model for the scam report API."""
    status: str = Field(..., description="OK, ERROR, or CLARIFICATION_NEEDED")
    message: Optional[str] = Field(None, description="Error message or status description.")
    request_datetime: datetime = Field(..., description="Timestamp of the request in UTC.")
    address_analyzed: bool = Field(..., description="Whether scam analysis has been performed for this address.")
    scam_report: Optional[str] = Field(None, description="The scam analysis report if available.")
    analysis_date: Optional[datetime] = Field(None, description="When the scam analysis was performed.")
    risk_score: Optional[float] = Field(None, description="Risk score if available (0.0 to 1.0).")
    blockchain_explorer_link: Optional[str] = Field(None, description="Link to a block explorer for the address.")
    bot_deeplink: Optional[str] = Field(None, description="A raw t.me URL to check the address with the bot.")
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
async def check_address(request: AddressCheckRequest, api_request: Request, db: Session = Depends(get_db)):
    """
    Validates a crypto address, retrieves public memos, and provides relevant links.
    """
    # --- Audit Logging for Request ---
    try:
        client_ip = api_request.client.host
        request_log = (
            f"🔹 **API Request: /check-address**\n\n"
            f"**Client IP:** `{client_ip}`\n"
            f"**Address:** `{request.crypto_address}`\n"
            f"**Blockchain Hint:** `{request.blockchain_type or 'None'}`\n"
            f"**Requested By:** `tgid://user?id={request.request_by_telegram_id}`\n"
            f"**Provided By:** `tgid://user?id={request.provided_by_telegram_id}`"
        )
        await log_to_audit_channel_async(request_log)
    except Exception as e:
        logging.error(f"Failed to log API request to audit channel: {e}", exc_info=True)

    # --- Response Logging Helper ---
    async def log_and_return(response: AddressCheckResponse) -> AddressCheckResponse:
        try:
            response_log = (
                f"🔸 **API Response: /check-address**\n\n"
                f"**Address:** `{request.crypto_address}`\n"
                f"**Status:** `{response.status}`\n"
                f"**Message:** `{response.message}`\n"
                f"**Risk Score:** `{response.risk_score if response.risk_score is not None else 'N/A'}`"
            )
            await log_to_audit_channel_async(response_log)
        except Exception as e:
            logging.error(f"Failed to log API response to audit channel: {e}", exc_info=True)
        return response

    request_time = datetime.now(timezone.utc)
    crypto_finder = CryptoAddressFinder()
    
    detected_map = crypto_finder.find_addresses(request.crypto_address)
    
    if not detected_map:
        return await log_and_return(AddressCheckResponse(
            status="ERROR",
            message=f"'{request.crypto_address}' is not a valid or recognized crypto address format.",
            request_datetime=request_time
        ))

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
                return await log_and_return(AddressCheckResponse(
                    status="ERROR",
                    message=f"Provided blockchain_type '{request.blockchain_type}' is not a valid option for this address. Possible options: {sorted(list(ambiguity_options))}",
                    request_datetime=request_time
                ))
        else:
            return await log_and_return(AddressCheckResponse(
                status="CLARIFICATION_NEEDED",
                message="Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
                request_datetime=request_time,
                possible_blockchains=sorted(list(ambiguity_options))
            ))
    
    if not blockchain:
        # This case should not be hit if logic is correct, but it's a safeguard.
        # Add logging to be sure
        logging.error(f"API_LOGIC_ERROR: Could not resolve a single blockchain for address '{request.crypto_address}' from detected chains: {detected_chains}. Ambiguity options were: {ambiguity_options}")
        return await log_and_return(AddressCheckResponse(
            status="ERROR",
            message=f"Could not determine a single blockchain for '{request.crypto_address}'.",
            request_datetime=request_time
        ))

    risk_score: Optional[float] = None
    risk_score_updated_at: Optional[datetime] = None

    # --- Check for existing risk score in the database first ---
    try:
        # We query for any record of this address on the determined blockchain
        existing_record = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower()
        ).first()

        if existing_record and existing_record.risk_score is not None:
            logging.info(f"Found existing risk score {existing_record.risk_score} for {request.crypto_address} in DB.")
            risk_score = existing_record.risk_score
            risk_score_updated_at = existing_record.updated_at
    except SQLAlchemyError as e:
        logging.error(f"API DB Error checking for existing risk score for {request.crypto_address}: {e}", exc_info=True)
        # Do not fail the request; proceed to AI check as a fallback.

    # --- New logic for TRON address risk analysis (only if not found in DB) ---
    if risk_score is None and blockchain == 'tron':
        try:
            # Initialize clients for Tron and AI
            tron_client = TronScanAPI()
            vertex_client = VertexAIClient()

            # Fetch basic Tron data (optimized for cost/speed)
            loop = asyncio.get_running_loop()
            tron_data = await loop.run_in_executor(
                None, tron_client.get_basic_account_info, request.crypto_address
            )

            if tron_data:
                # Create a focused prompt for risk scoring
                balance_trx = tron_data.get('balance', 0) / 1_000_000  # Convert SUN to TRX
                tx_count = tron_data.get('totalTransactionCount', 0)
                create_time = tron_data.get('createTime')
                
                prompt = (
                    f"Analyze this TRON address for risk assessment. "
                    f"Address: {request.crypto_address}, "
                    f"Balance: {balance_trx:.6f} TRX, "
                    f"Total transactions: {tx_count}, "
                    f"Creation time: {create_time}. "
                    f"Consider account age, transaction volume, balance patterns. "
                    f"Provide only a risk score from 0.0 (very low risk) to 1.0 (very high risk). "
                    f"Response must be only the numerical score (e.g., 0.75)."
                )

                # Get AI analysis
                ai_response = await vertex_client.generate_text(prompt)

                if ai_response:
                    try:
                        # Attempt to parse the score from the AI's response
                        parsed_score = float(ai_response.strip())
                        logging.info(f"Successfully generated risk score {parsed_score} for TRON address {request.crypto_address}")
                        
                        # --- Write the new score to the database ---
                        if existing_record:
                            logging.info(f"Updating existing DB record (ID: {existing_record.id}) with new risk score.")
                            existing_record.risk_score = parsed_score
                            existing_record.updated_at = datetime.now(timezone.utc)
                            db.add(existing_record)
                        else:
                            # If no record exists, create a new one since message_id is now optional.
                            logging.info(f"Creating new DB record for {request.crypto_address} with new risk score.")
                            new_record = CryptoAddress(
                                address=request.crypto_address,
                                blockchain=blockchain,
                                risk_score=parsed_score,
                                status="to_check", # Default status
                                detected_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc)
                                # message_id is intentionally left null
                            )
                            db.add(new_record)
                            existing_record = new_record # Use the new record for the refresh
                        
                        db.commit()
                        db.refresh(existing_record)
                        
                        # Set the variables for the final response
                        risk_score = existing_record.risk_score
                        risk_score_updated_at = existing_record.updated_at

                    except (ValueError, TypeError):
                        logging.error(f"Could not parse risk score from AI response: '{ai_response}' for address {request.crypto_address}")
                    except SQLAlchemyError as db_err:
                        logging.error(f"API DB Error saving new risk score for {request.crypto_address}: {db_err}", exc_info=True)
                        db.rollback() # Rollback on error
            else:
                logging.info(f"No account info found on TronScan for address {request.crypto_address}, skipping risk analysis.")

        except Exception as e:
            # Log any errors from the Tron/AI clients but don't fail the whole request
            logging.error(f"Error during TRON risk analysis for {request.crypto_address}: {e}", exc_info=True)
    
    try:
        # --- Extensive Logging for DB Query ---
        # logging.info("-------------------- API DB QUERY DEBUG START --------------------")
        # logging.info(f"[API_DB_DEBUG] File: api/external_api.py -> check_address()")
        # logging.info(f"[API_DB_DEBUG] Preparing to query for public memos.")
        # logging.info(f"[API_DB_DEBUG] PARAMETER address: '{request.crypto_address}'")
        # logging.info(f"[API_DB_DEBUG] PARAMETER blockchain: '{blockchain}'")

        # 1. Create the base query EXACTLY matching the working logic in memo_management.py
        logging.info("[API_DB_DEBUG] Using func.lower() for case-insensitive comparison to mirror the bot's working implementation.")
        query = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower(),
            CryptoAddress.notes.isnot(None),
            CryptoAddress.notes != ""
        )
        # logging.info(f"[API_DB_DEBUG] Step 1: Base query constructed.")
        # logging.info(f"[API_DB_DEBUG] SQL for base query (approximate): {str(query.statement.compile(compile_kwargs={'literal_binds': True}))}")

        # 2. Apply the public scope filter to the existing query object.
        query = query.filter(
            or_(
                CryptoAddress.memo_type == MemoType.PUBLIC.value,
                CryptoAddress.memo_type.is_(None)
            )
        )
        # logging.info(f"[API_DB_DEBUG] Step 2: Public memo filter applied (memo_type is 'public' or NULL).")
        # logging.info(f"[API_DB_DEBUG] SQL for final query (approximate): {str(query.statement.compile(compile_kwargs={'literal_binds': True}))}")
        
        # 3. Execute the final query with ordering.
        # logging.info("[API_DB_DEBUG] Step 3: Executing query against the database...")
        memo_results = query.order_by(CryptoAddress.id.desc()).all()
        # logging.info(f"[API_DB_DEBUG] Step 4: Query executed. Found {len(memo_results)} raw results.")

        # 4. Log the raw results for inspection.
        if not memo_results:
            logging.warning(f"[API_DB_DEBUG] No matching records found in 'crypto_addresses' table for the given criteria.")
        else:
            for i, memo in enumerate(memo_results):
                logging.info(f"[API_DB_DEBUG]   - Result [{i}]: ID={memo.id}, Addr='{memo.address}', Chain='{memo.blockchain}', Type='{memo.memo_type}', Notes='{memo.notes[:70]}...'")

        # 5. Extract the notes.
        public_memos = [memo.notes for memo in memo_results if memo.notes]
        # logging.info(f"[API_DB_DEBUG] Step 5: Extracted {len(public_memos)} notes from raw results.")
        # logging.info("-------------------- API DB QUERY DEBUG END ----------------------")

    except SQLAlchemyError as e:
        logging.error(f"API DB Error fetching memos for {request.crypto_address}: {e}", exc_info=True)
        return await log_and_return(AddressCheckResponse(status="ERROR", message="A database error occurred while fetching memos.", request_datetime=request_time))

    explorer_link = Config.EXPLORER_CONFIG.get(blockchain, {}).get("url_template", "").format(address=request.crypto_address) or None

    bot_deeplink = f"https://t.me/{Config.BOT_USERNAME}?start={request.crypto_address}" if Config.BOT_USERNAME else None
    if not bot_deeplink:
        logging.warning("BOT_USERNAME not set in Config, cannot generate deeplink.")

    return await log_and_return(AddressCheckResponse(
        status="OK",
        message="Address details retrieved successfully.",
        request_datetime=request_time,
        bot_deeplink=bot_deeplink,
        blockchain_explorer_link=explorer_link,
        public_memos=public_memos if public_memos else [],
        risk_score=risk_score,
        risk_score_updated_at=risk_score_updated_at
    ))

@app.post("/analyze-scam", response_model=ScamReportResponse, dependencies=[Depends(get_api_key)])
async def analyze_scam(request: ScamReportRequest, api_request: Request, db: Session = Depends(get_db)):
    """
    Performs new scam analysis on a crypto address and provides a report.
    This endpoint triggers AI analysis using external APIs and may take time to complete.
    """
    request_time = datetime.now(timezone.utc)

    # --- Audit Logging for Request ---
    try:
        client_ip = api_request.client.host
        request_log = (
            f"🔹 **API Request: /analyze-scam**\n\n"
            f"**Client IP:** `{client_ip}`\n"
            f"**Address:** `{request.crypto_address}`\n"
            f"**Blockchain Hint:** `{request.blockchain_type or 'None'}`\n"
            f"**Requested By:** `tgid://user?id={request.request_by_telegram_id}`"
        )
        await log_to_audit_channel_async(request_log)
    except Exception as e:
        logging.error(f"Failed to log API request to audit channel: {e}", exc_info=True)

    # --- Response Logging Helper ---
    async def log_and_return(response: ScamReportResponse) -> ScamReportResponse:
        try:
            response_log = (
                f"🔸 **API Response: /analyze-scam**\n\n"
                f"**Address:** `{request.crypto_address}`\n"
                f"**Status:** `{response.status}`\n"
                f"**Message:** `{response.message}`\n"
                f"**Risk Score:** `{response.risk_score if response.risk_score is not None else 'N/A'}`"
            )
            await log_to_audit_channel_async(response_log)
        except Exception as e:
            logging.error(f"Failed to log API response to audit channel: {e}", exc_info=True)
        return response

    crypto_finder = CryptoAddressFinder()
    
    detected_map = crypto_finder.find_addresses(request.crypto_address)
    
    if not detected_map:
        return await log_and_return(ScamReportResponse(
            status="ERROR",
            message=f"'{request.crypto_address}' is not a valid or recognized crypto address format.",
            request_datetime=request_time,
            address_analyzed=False
        ))

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
                return await log_and_return(ScamReportResponse(
                    status="ERROR",
                    message=f"Provided blockchain_type '{request.blockchain_type}' is not a valid option for this address. Possible options: {sorted(list(ambiguity_options))}",
                    request_datetime=request_time,
                    address_analyzed=False
                ))
        else:
            return await log_and_return(ScamReportResponse(
                status="CLARIFICATION_NEEDED",
                message="Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
                request_datetime=request_time,
                possible_blockchains=sorted(list(ambiguity_options)),
                address_analyzed=False
            ))
    
    if not blockchain:
        # This case should not be hit if logic is correct, but it's a safeguard.
        # Add logging to be sure
        logging.error(f"API_LOGIC_ERROR: Could not resolve a single blockchain for address '{request.crypto_address}' from detected chains: {detected_chains}. Ambiguity options were: {ambiguity_options}")
        return await log_and_return(ScamReportResponse(
            status="ERROR",
            message=f"Could not determine a single blockchain for '{request.crypto_address}'.",
            request_datetime=request_time,
            address_analyzed=False
        ))

    risk_score: Optional[float] = None
    risk_score_updated_at: Optional[datetime] = None
    scam_report: Optional[str] = None
    analysis_date: Optional[datetime] = None

    # --- Check for existing scam report in the database ---
    try:
        existing_record = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower()
        ).first()

        if existing_record:
            logging.info(f"Found existing record for {request.crypto_address} in DB.")
            address_analyzed = True

            if existing_record.risk_score is not None:
                risk_score = existing_record.risk_score
                risk_score_updated_at = existing_record.updated_at
            else:
                logging.info(f"No risk score found for existing record of {request.crypto_address}.")

            # For scam report, we might want to check a different field or logic
            scam_report = existing_record.notes  # Assuming notes might contain scam report info
            analysis_date = existing_record.updated_at if existing_record.updated_at else existing_record.detected_at

        else:
            logging.info(f"No existing record found for {request.crypto_address}, proceeding with analysis.")
            address_analyzed = False
    except SQLAlchemyError as e:
        logging.error(f"API DB Error checking for existing record for {request.crypto_address}: {e}", exc_info=True)
        address_analyzed = False

    # If we have an existing record and it was recently updated, we can return the existing risk score and skip the analysis
    if address_analyzed and risk_score_updated_at:
        # Ensure both datetimes are timezone-aware for comparison
        if risk_score_updated_at.tzinfo is None:
            risk_score_updated_at = risk_score_updated_at.replace(tzinfo=timezone.utc)
        
        time_since_update = (request_time - risk_score_updated_at).total_seconds()
        if time_since_update < 3600:  # Less than an hour ago
            logging.info(f"Returning existing risk score for {request.crypto_address} (updated {time_since_update} seconds ago).")
            return await log_and_return(ScamReportResponse(
                status="OK",
                message="Scam analysis report retrieved from database.",
                request_datetime=request_time,
                address_analyzed=True,
                scam_report=scam_report,
                analysis_date=analysis_date,
                risk_score=risk_score,
                blockchain_explorer_link=Config.EXPLORER_CONFIG.get(blockchain, {}).get("url_template", "").format(address=request.crypto_address) or None,
                bot_deeplink=f"https://t.me/{Config.BOT_USERNAME}?start={request.crypto_address}" if Config.BOT_USERNAME else None
            ))

    # --- Perform TRON address risk analysis ---
    if blockchain == 'tron':
        try:
            tron_client = TronScanAPI()
            vertex_client = VertexAIClient()

            # First, check if this is a smart contract or regular address
            loop = asyncio.get_running_loop()
            is_contract = await loop.run_in_executor(
                None, tron_client.is_smart_contract, request.crypto_address
            )

            prompt = None
            tron_data = None  # Initialize to avoid scope issues
            
            if is_contract:
                # Fetch contract-specific data
                contract_data = await loop.run_in_executor(
                    None, tron_client.get_contract_info, request.crypto_address
                )
                
                if contract_data:
                    # Create a focused prompt for smart contract analysis
                    balance_trx = contract_data.get('balance', 0) / 1_000_000  # Convert SUN to TRX
                    tx_count = contract_data.get('totalTransactionCount', 0)
                    create_time = contract_data.get('date_created')
                    contract_type = contract_data.get('contractType', 'Unknown')
                    creator = contract_data.get('creator', 'Unknown')
                    verified = contract_data.get('verified', False)
                    
                    # Token-specific info if available
                    token_info = contract_data.get('tokenInfo')
                    token_details = ""
                    if token_info:
                        symbol = token_info.get('symbol', 'Unknown')
                        name = token_info.get('name', 'Unknown')
                        total_supply = token_info.get('totalSupply', 'Unknown')
                        holder_count = token_info.get('holderCount', 'Unknown')
                        transfer_count = token_info.get('transferCount', 'Unknown')
                        vip = token_info.get('vip', False)
                        
                        token_details = (f", Token: {name} ({symbol}), "
                                       f"Total Supply: {total_supply}, "
                                       f"Holders: {holder_count}, "
                                       f"Transfers: {transfer_count}, "
                                       f"VIP Status: {vip}")
                    
                    prompt = (
                        f"Analyze this TRON SMART CONTRACT for scam potential. "
                        f"Contract Address: {request.crypto_address}, "
                        f"Contract Type: {contract_type}, "
                        f"Creator: {creator}, "
                        f"Verified: {verified}, "
                        f"Balance: {balance_trx:.6f} TRX, "
                        f"Total transactions: {tx_count}, "
                        f"Creation time: {create_time}{token_details}. "
                        f"Provide a risk score (0.0-1.0) and brief scam analysis. "
                        f"Focus on: contract verification status, creator reputation, "
                        f"token economics (if applicable), transaction patterns, "
                        f"unusual contract behavior. Consider: unverified contracts are higher risk, "
                        f"contracts with excessive permissions are suspicious, "
                        f"tokens with unfair distribution may be scams. "
                        f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                        f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                    )
                    logging.info(f"Generated smart contract prompt for {request.crypto_address}")
                else:
                    logging.error(f"Failed to fetch contract data for {request.crypto_address}, falling back to basic analysis")
                    # Fall back to basic account info for contracts that don't have contract data
                    tron_data = await loop.run_in_executor(
                        None, tron_client.get_basic_account_info, request.crypto_address
                    )
                    if tron_data:
                        balance_trx = tron_data.get('balance', 0) / 1_000_000
                        tx_count = tron_data.get('totalTransactionCount', 0)
                        create_time = tron_data.get('date_created')
                        
                        prompt = (
                            f"Analyze this TRON SMART CONTRACT for scam potential. "
                            f"Contract Address: {request.crypto_address}, "
                            f"Balance: {balance_trx:.6f} TRX, "
                            f"Total transactions: {tx_count}, "
                            f"Creation time: {create_time}. "
                            f"Note: Contract-specific data unavailable. "
                            f"Provide a risk score (0.0-1.0) and brief scam analysis. "
                            f"IMPORTANT: Start your analysis report with 'This is a SMART CONTRACT address.' "
                            f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a SMART CONTRACT address. [analysis here]\"}}"
                        )
                        logging.info(f"Generated fallback smart contract prompt for {request.crypto_address}")
            else:
                # Fetch wallet-specific data
                tron_data = await loop.run_in_executor(
                    None, tron_client.get_basic_account_info, request.crypto_address
                )
                
                if tron_data:
                    # Create a focused prompt for wallet address analysis
                    balance_trx = tron_data.get('balance', 0) / 1_000_000  # Convert SUN to TRX
                    tx_count = tron_data.get('totalTransactionCount', 0)
                    create_time = tron_data.get('date_created')
                    token_balances = tron_data.get('tokenBalances', [])
                    
                    # Format token balances for AI analysis
                    token_info = ""
                    if token_balances:
                        significant_tokens = []
                        for token in token_balances[:5]:  # Top 5 tokens for analysis
                            token_name = token.get('tokenName', 'Unknown')
                            token_symbol = token.get('tokenSymbol', '')
                            balance = token.get('balance', '0')
                            token_decimal = token.get('tokenDecimal', 0)
                            
                            # Convert balance to readable format
                            try:
                                if token_decimal > 0:
                                    readable_balance = float(balance) / (10 ** token_decimal)
                                else:
                                    readable_balance = float(balance)
                                
                                if readable_balance > 0:
                                    significant_tokens.append(f"{token_name} ({token_symbol}): {readable_balance:.6f}")
                            except (ValueError, ZeroDivisionError):
                                if balance != '0':
                                    significant_tokens.append(f"{token_name} ({token_symbol}): {balance}")
                        
                        if significant_tokens:
                            token_info = f", Token holdings: {'; '.join(significant_tokens)}"
                        else:
                            token_info = ", Token holdings: None"
                    else:
                        token_info = ", Token holdings: None"
                    
                    prompt = (
                        f"Analyze this TRON WALLET ADDRESS for scam potential. "
                        f"Address: {request.crypto_address}, "
                        f"Balance: {balance_trx:.6f} TRX, "
                        f"Total transactions: {tx_count}, "
                        f"Creation time: {create_time}{token_info}. "
                        f"Provide a risk score (0.0-1.0) and brief scam analysis. "
                        f"Focus on: account age, transaction volume, balance patterns, token holdings diversity. "
                        f"Consider: large token holdings may indicate accumulation schemes, "
                        f"diverse small holdings may suggest airdrop farming, "
                        f"stablecoin concentrations may indicate laundering. "
                        f"IMPORTANT: Start your analysis report with 'This is a WALLET address.' "
                        f"Respond in JSON format: {{\"risk_score\": 0.X, \"report\": \"This is a WALLET address. [analysis here]\"}}"
                    )
                    logging.info(f"Generated wallet prompt for {request.crypto_address}")

            if prompt:
                # Get AI analysis
                logging.info(f"[DEBUG] Sending prompt to AI for {request.crypto_address}")
                ai_response = await vertex_client.generate_text(prompt)
                logging.info(f"[DEBUG] AI response received: {ai_response[:200] if ai_response else 'None'}...")

                if ai_response:
                    try:
                        logging.info(f"[DEBUG] Processing AI response for {request.crypto_address}")
                        # Clean the AI response to handle markdown code blocks
                        cleaned_response = ai_response.strip()
                        if cleaned_response.startswith('```json'):
                            cleaned_response = cleaned_response[7:]  # Remove ```json
                        if cleaned_response.endswith('```'):
                            cleaned_response = cleaned_response[:-3]  # Remove ```
                        cleaned_response = cleaned_response.strip()
                        
                        logging.info(f"[DEBUG] Cleaned response: {cleaned_response}")
                        
                        # Parse the AI's response
                        ai_response_json = json.loads(cleaned_response)
                        logging.info(f"[DEBUG] Parsed JSON: {ai_response_json}")
                        
                        risk_score = ai_response_json.get("risk_score")
                        scam_report = ai_response_json.get("report")
                        
                        logging.info(f"[DEBUG] Extracted - Risk score: {risk_score}, Report length: {len(scam_report) if scam_report else 0}")

                        # Add "basic AI analysis" mark to the report
                        if scam_report:
                            scam_report = f"🤖 **Basic AI Analysis**\n\n{scam_report}"

                        if risk_score is not None:
                            risk_score = float(risk_score)
                            logging.info(f"Successfully generated risk score {risk_score} for TRON address {request.crypto_address}")
                        else:
                            logging.warning(f"Risk score not found in AI response for address {request.crypto_address}: {ai_response}")

                        # --- Write the new score and report to the database ---
                        if existing_record:
                            logging.info(f"Updating existing DB record (ID: {existing_record.id}) with new risk score and scam report.")
                            existing_record.risk_score = risk_score
                            existing_record.notes = scam_report
                            existing_record.memo_type = MemoType.PUBLIC.value  # Ensure it's public
                            existing_record.updated_at = request_time
                            db.add(existing_record)
                        else:
                            logging.info(f"Creating new DB record for {request.crypto_address} with risk score and scam report.")
                            new_record = CryptoAddress(
                                address=request.crypto_address,
                                blockchain=blockchain,
                                risk_score=risk_score,
                                notes=scam_report,
                                memo_type=MemoType.PUBLIC.value,  # Set as public memo
                                status="to_check",
                                detected_at=request_time,
                                updated_at=request_time
                            )
                            db.add(new_record)
                            existing_record = new_record
                        
                        db.commit()
                        db.refresh(existing_record)
                        
                        # Set the variables for the final response
                        risk_score = existing_record.risk_score
                        risk_score_updated_at = existing_record.updated_at
                        scam_report = existing_record.notes
                        analysis_date = existing_record.updated_at

                    except (ValueError, TypeError) as e:
                        logging.error(f"[DEBUG] Error parsing AI response for address {request.crypto_address}: {e}. Response: {ai_response}")
                    except SQLAlchemyError as db_err:
                        logging.error(f"[DEBUG] API DB Error saving scam report for {request.crypto_address}: {db_err}", exc_info=True)
                        db.rollback()
                else:
                    logging.warning(f"[DEBUG] No AI response received for {request.crypto_address}")
            else:
                logging.warning(f"[DEBUG] No prompt generated for {request.crypto_address}, skipping risk analysis.")

        except Exception as e:
            logging.error(f"Error during TRON scam analysis for {request.crypto_address}: {e}", exc_info=True)
    
    # Final response construction
    explorer_link = Config.EXPLORER_CONFIG.get(blockchain, {}).get("url_template", "").format(address=request.crypto_address) or None
    bot_deeplink = f"https://t.me/{Config.BOT_USERNAME}?start={request.crypto_address}" if Config.BOT_USERNAME else None

    return await log_and_return(ScamReportResponse(
        status="OK",
        message="Scam analysis completed.",
        request_datetime=request_time,
        address_analyzed=True,
        scam_report=scam_report,
        analysis_date=analysis_date,
        risk_score=risk_score,
        blockchain_explorer_link=explorer_link,
        bot_deeplink=bot_deeplink
    ))

@app.post("/get-scam-analysis", response_model=ScamReportResponse, dependencies=[Depends(get_api_key)])
async def get_scam_analysis(request: ScamReportRequest, api_request: Request, db: Session = Depends(get_db)):
    """
    Retrieves existing scam analysis for a crypto address if it has been performed.
    This endpoint only queries the database and does not trigger new analysis.
    Returns whether analysis exists and the report content.
    """
    # --- Audit Logging for Request ---
    try:
        client_ip = api_request.client.host
        request_log = (
            f"🔹 **API Request: /get-scam-analysis**\n\n"
            f"**Client IP:** `{client_ip}`\n"
            f"**Address:** `{request.crypto_address}`\n"
            f"**Blockchain Hint:** `{request.blockchain_type or 'None'}`\n"
            f"**Requested By:** `tgid://user?id={request.request_by_telegram_id}`"
        )
        await log_to_audit_channel_async(request_log)
    except Exception as e:
        logging.error(f"Failed to log get-scam-analysis API request to audit channel: {e}", exc_info=True)

    # --- Response Logging Helper ---
    async def log_and_return(response: ScamReportResponse) -> ScamReportResponse:
        try:
            response_log = (
                f"🔸 **API Response: /get-scam-analysis**\n\n"
                f"**Address:** `{request.crypto_address}`\n"
                f"**Status:** `{response.status}`\n"
                f"**Analysis Available:** `{response.address_analyzed}`\n"
                f"**Risk Score:** `{response.risk_score if response.risk_score is not None else 'N/A'}`"
            )
            await log_to_audit_channel_async(response_log)
        except Exception as e:
            logging.error(f"Failed to log get-scam-analysis API response to audit channel: {e}", exc_info=True)
        return response

    request_time = datetime.now(timezone.utc)
    crypto_finder = CryptoAddressFinder()
    
    # Validate and resolve blockchain
    detected_map = crypto_finder.find_addresses(request.crypto_address)
    
    if not detected_map:
        return await log_and_return(ScamReportResponse(
            status="ERROR",
            message=f"'{request.crypto_address}' is not a valid or recognized crypto address format.",
            request_datetime=request_time,
            address_analyzed=False
        ))

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
                return await log_and_return(ScamReportResponse(
                    status="ERROR",
                    message=f"Provided blockchain_type '{request.blockchain_type}' is not a valid option for this address. Possible options: {sorted(list(ambiguity_options))}",
                    request_datetime=request_time,
                    address_analyzed=False
                ))
        else:
            return await log_and_return(ScamReportResponse(
                status="CLARIFICATION_NEEDED",
                message="Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
                request_datetime=request_time,
                possible_blockchains=sorted(list(ambiguity_options)),
                address_analyzed=False
            ))
    
    if not blockchain:
        logging.error(f"SCAM_REPORT_LOGIC_ERROR: Could not resolve a single blockchain for address '{request.crypto_address}' from detected chains: {detected_chains}")
        return await log_and_return(ScamReportResponse(
            status="ERROR",
            message=f"Could not determine a single blockchain for '{request.crypto_address}'.",
            request_datetime=request_time,
            address_analyzed=False
        ))

    # --- Query for scam analysis data ---
    try:
        # Look for existing records with analysis data
        existing_record = db.query(CryptoAddress).filter(
            func.lower(CryptoAddress.address) == request.crypto_address.lower(),
            func.lower(CryptoAddress.blockchain) == blockchain.lower()
        ).first()

        address_analyzed = False
        scam_report = None
        analysis_date = None
        risk_score = None

        if existing_record:
            # Check if we have a public memo (scam analysis)
            if existing_record.notes and existing_record.notes.strip():
                # Check if this is a public memo or no memo type specified (default public)
                if existing_record.memo_type == MemoType.PUBLIC.value or existing_record.memo_type is None:
                    address_analyzed = True
                    scam_report = existing_record.notes
                    analysis_date = existing_record.updated_at or existing_record.detected_at
            
            # Get risk score if available
            if existing_record.risk_score is not None:
                risk_score = existing_record.risk_score

        # Generate explorer link and bot deeplink
        explorer_link = Config.EXPLORER_CONFIG.get(blockchain, {}).get("url_template", "").format(address=request.crypto_address) or None
        bot_deeplink = f"https://t.me/{Config.BOT_USERNAME}?start={request.crypto_address}" if Config.BOT_USERNAME else None

        # Prepare response message
        if address_analyzed:
            message = "Scam analysis found for this address."
        else:
            message = "No scam analysis has been performed for this address yet."

        return await log_and_return(ScamReportResponse(
            status="OK",
            message=message,
            request_datetime=request_time,
            address_analyzed=address_analyzed,
            scam_report=scam_report,
            analysis_date=analysis_date,
            risk_score=risk_score,
            blockchain_explorer_link=explorer_link,
            bot_deeplink=bot_deeplink
        ))

    except SQLAlchemyError as e:
        logging.error(f"API DB Error fetching scam report for {request.crypto_address}: {e}", exc_info=True)
        return await log_and_return(ScamReportResponse(
            status="ERROR",
            message="A database error occurred while fetching scam report.",
            request_datetime=request_time,
            address_analyzed=False
        ))
