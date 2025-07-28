"""Common database operations for Rebot.
Compatible with both SQLite and PostgreSQL.
"""

import json
from typing import Optional
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from aiogram.types import (
    Message as TelegramMessage,
    User as TelegramUser,
    Chat as TelegramChat,
)

from database.models import (
    User,
    Message,
    Chat,
    CryptoAddress,
    Event,
    CryptoAddressStatus,
    EventType,
    MemoType,  # Added MemoType
    UserWatchState,  # Added UserWatchState for user watch states
    # ReservedField,  # Uncomment if ReservedField is used in queries
)

from database.schema import json_dumps


def get_user_watch_states(db: Session, telegram_user_id: int) -> dict:
    """Retrieve the user's watch states for memos and blockchain events as a dict."""
    user = db.query(User).filter(User.telegram_id == telegram_user_id).first()
    states = {}
    if not user:
        return states
    # Query all UserWatchState rows for this user
    rows = db.query(UserWatchState).filter(UserWatchState.user_id == user.id).all()
    for row in rows:
        blockchain_lc = row.blockchain.lower()
        # For TRON, use original-case address as key; for others, lowercase
        key_address = row.address if blockchain_lc == "tron" else row.address.lower()
        key = f"{key_address}:{blockchain_lc}"
        # Parse last_state from JSON if present
        last_state = None
        if row.last_state:
            try:
                last_state = json.loads(row.last_state)
            except Exception:
                last_state = None
        states[key] = {
            "watch_memos": bool(row.watch_memos),
            "watch_events": bool(row.watch_events),
            "last_memo_id": row.last_memo_id,
            "last_state": last_state,
            "_row": row,  # Expose row for advanced usage
        }
    return states


# --- UserWatchState helpers for persistent polling state ---
def get_user_watch_state_row(db: Session, user_id: int, address: str, blockchain: str):
    blockchain_lc = blockchain.lower()
    db_address = address if blockchain_lc == "tron" else address.lower()
    return (
        db.query(UserWatchState)
        .filter(
            UserWatchState.user_id == user_id,
            UserWatchState.address == db_address,
            UserWatchState.blockchain == blockchain_lc,
        )
        .first()
    )


def update_user_watch_state_last_memo_id(
    db: Session, user_id: int, address: str, blockchain: str, last_memo_id: int
):
    row = get_user_watch_state_row(db, user_id, address, blockchain)
    if row:
        row.last_memo_id = last_memo_id
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return True
    return False


def update_user_watch_state_last_state(
    db: Session, user_id: int, address: str, blockchain: str, last_state: dict
):
    row = get_user_watch_state_row(db, user_id, address, blockchain)
    if row:
        try:
            row.last_state = json.dumps(last_state) if last_state is not None else None
        except Exception:
            row.last_state = None
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return True
    return False


def set_user_watch_state(
    db: Session,
    telegram_user_id: int,
    address: str,
    blockchain: str,
    watch_memos: bool = None,
    watch_events: bool = None,
):
    """Set the user's watch state for a specific address/blockchain."""
    user = db.query(User).filter(User.telegram_id == telegram_user_id).first()
    if not user:
        return False
    # Find or create UserWatchState row
    address_lc = address.lower()
    blockchain_lc = blockchain.lower()
    blockchain_lc = blockchain.lower()
    # For TRON, store address in original case; for others, lowercase
    db_address = address if blockchain_lc == "tron" else address.lower()
    watch_state = (
        db.query(UserWatchState)
        .filter(
            UserWatchState.user_id == user.id,
            UserWatchState.address == db_address,
            UserWatchState.blockchain == blockchain_lc,
        )
        .first()
    )
    if not watch_state:
        watch_state = UserWatchState(
            user_id=user.id,
            address=db_address,
            blockchain=blockchain_lc,
            watch_memos=watch_memos if watch_memos is not None else False,
            watch_events=watch_events if watch_events is not None else False,
        )
        db.add(watch_state)
    else:
        if watch_memos is not None:
            watch_state.watch_memos = watch_memos
        if watch_events is not None:
            watch_state.watch_events = watch_events
    db.commit()
    return True


"""
Common database operations for Rebot.
Compatible with both SQLite and PostgreSQL.
"""


# User operations
def get_or_create_user(db: Session, telegram_user: TelegramUser) -> User:
    """Get existing user or create a new one"""
    user = db.query(User).filter(User.telegram_id == telegram_user.id).first()

    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            is_bot=telegram_user.is_bot,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Log user creation event
        create_event(db, EventType.USER_JOIN.value, user_id=user.id)

    return user


# Chat operations
def get_or_create_chat(db: Session, telegram_chat: TelegramChat) -> Chat:
    """Get existing chat or create a new one"""
    chat = db.query(Chat).filter(Chat.telegram_id == telegram_chat.id).first()

    if chat is None:
        chat = Chat(
            telegram_id=telegram_chat.id,
            type=telegram_chat.type,
            title=getattr(telegram_chat, "title", None),
            username=getattr(telegram_chat, "username", None),
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

    return chat


# Message operations
def save_message(db: Session, telegram_message: TelegramMessage) -> Message:
    """Save a message to the database"""
    # Get or create user and chat
    if telegram_message.from_user is None:
        raise ValueError(
            "telegram_message.from_user is None, cannot save message without a user."
        )
    user = get_or_create_user(db, telegram_message.from_user)
    chat = get_or_create_chat(db, telegram_message.chat)

    # Convert message to dict and then to JSON
    try:
        raw_data = json_dumps(telegram_message.model_dump(exclude_none=True))
    except Exception as e:
        logging.error("Failed to serialize message: %s", e)
        raw_data = None

    # Create message
    message = Message(
        telegram_id=telegram_message.message_id,
        user_id=user.id,
        chat_id=chat.id,
        text=telegram_message.text or "",
        date=telegram_message.date,
        is_command=bool(
            telegram_message.text and telegram_message.text.startswith("/")
        ),
        raw_data=raw_data,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # Log message event
    event_type = (
        EventType.COMMAND_EXECUTED.value
        if message.is_command
        else EventType.MESSAGE_RECEIVED.value
    )
    create_event(db, event_type, user_id=user.id)

    return message


# Crypto address operations
def save_crypto_address(
    db: Session, message_id: int, address: str, blockchain: str
) -> CryptoAddress:
    """Save a crypto address to the database.
    An address is unique per message_id, address string, and blockchain."""
    # Check if this address for this specific blockchain already exists in this message
    existing = (
        db.query(CryptoAddress)
        .filter(
            CryptoAddress.message_id == message_id,
            CryptoAddress.address == address,
            CryptoAddress.blockchain == blockchain,  # ADDED THIS CONDITION
        )
        .first()
    )

    if existing:
        # Log or handle if you want to know it's a re-detection of the exact same entry
        logging.debug(
            f"CryptoAddress {address} on {blockchain} for message_id {message_id} already exists with id {existing.id}."
        )  # pylint: disable=logging-fstring-interpolation
        return existing

    # Default memo_type can be None or a specific default if desired
    crypto_address = CryptoAddress(
        address=address,
        blockchain=blockchain,
        status=CryptoAddressStatus.TO_CHECK.value,
        message_id=message_id,
        memo_type=None,  # Initialize memo_type
    )
    db.add(crypto_address)
    db.commit()
    db.refresh(crypto_address)

    # Log address detection event
    data = json_dumps({"address": address, "blockchain": blockchain})
    create_event(
        db,
        EventType.ADDRESS_DETECTED.value,
        crypto_address_id=crypto_address.id,
        data=data,
    )

    return crypto_address


def update_crypto_address_memo(
    db: Session,
    address_id: int,
    notes: Optional[str],
    memo_type: Optional[
        str
    ],  # Expects a string value from MemoType enum, e.g., "public"
    user_id: Optional[int] = None,  # Optional: ID of the user updating the memo
) -> Optional[CryptoAddress]:
    """Update the notes and memo_type of a crypto address."""
    crypto_address = (
        db.query(CryptoAddress).filter(CryptoAddress.id == address_id).first()
    )
    if crypto_address:
        crypto_address.notes = notes
        if memo_type:
            try:
                # Validate if memo_type is a valid member of MemoType enum
                valid_memo_type = MemoType(memo_type).value
                crypto_address.memo_type = valid_memo_type
            except ValueError:
                logging.error(
                    f"Invalid memo_type: {memo_type}. Not updating memo_type."
                )  # pylint: disable=logging-fstring-interpolation
                # Optionally, you could raise an error or handle it differently
        else:
            crypto_address.memo_type = None  # Clear memo_type if None is passed

        if user_id:
            crypto_address.memo_added_by_user_id = user_id

        crypto_address.memo_updated_at = datetime.now(timezone.utc)
        crypto_address.updated_at = datetime.now(
            timezone.utc
        )  # Also update the general updated_at

        db.commit()
        db.refresh(crypto_address)

        # Log memo update event (optional)
        # event_data = json_dumps({"address_id": address_id, "memo_type": crypto_address.memo_type, "updated_by": user_id})
        # create_event(db, "MEMO_UPDATED", data=event_data, crypto_address_id=address_id, user_id=user_id)

    return crypto_address


def update_crypto_address_status(
    db: Session, address_id: int, status: str
) -> Optional[CryptoAddress]:
    """Update the status of a crypto address"""
    crypto_address = (
        db.query(CryptoAddress).filter(CryptoAddress.id == address_id).first()
    )
    if crypto_address:
        old_status = crypto_address.status
        crypto_address.status = CryptoAddressStatus(status).value  # type: ignore
        crypto_address.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(crypto_address)

        # Log status change event
        data = json_dumps({"old_status": old_status, "new_status": status})
        create_event(
            db,
            EventType.ADDRESS_STATUS_CHANGE.value,
            crypto_address_id=crypto_address.id,
            data=data,
        )

    return crypto_address


# Event operations
def create_event(
    db: Session,
    event_type: str,
    user_id: Optional[int] = None,
    crypto_address_id: Optional[int] = None,
    data: Optional[str] = None,
) -> Event:
    """Create a new event"""
    event = Event(
        type=event_type,
        user_id=user_id,
        crypto_address_id=crypto_address_id,
        data=data,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return event


# Query operations
def get_recent_messages(db: Session, limit: int = 10):
    """Get recent messages"""
    return db.query(Message).order_by(desc(Message.created_at)).limit(limit).all()


def get_user_messages(db: Session, telegram_user_id: int, limit: int = 10):
    """Get messages from a specific user"""
    user = db.query(User).filter(User.telegram_id == telegram_user_id).first()
    if user:
        return (
            db.query(Message)
            .filter(Message.user_id == user.id)
            .order_by(desc(Message.created_at))
            .limit(limit)
            .all()
        )
    return []


def get_addresses_by_status(db: Session, status: str, limit: int = 10):
    """Get crypto addresses by status"""
    return (
        db.query(CryptoAddress)
        .filter(CryptoAddress.status == status)
        .order_by(desc(CryptoAddress.updated_at))
        .limit(limit)
        .all()
    )


def get_address_history(db: Session, address: str):
    """Get all occurrences of an address"""
    return (
        db.query(CryptoAddress)
        .filter(CryptoAddress.address == address)
        .order_by(desc(CryptoAddress.detected_at))
        .all()
    )


def get_all_watched_addresses(db: Session):
    """
    Return all UserWatchState rows where either watch_memos or watch_events is True, with user object attached.
    """
    watched = (
        db.query(UserWatchState)
        .filter(
            (UserWatchState.watch_memos == True) | (UserWatchState.watch_events == True)
        )
        .all()
    )
    # Attach user object for each watch
    for w in watched:
        w.user = db.query(User).filter(User.id == w.user_id).first()
    return watched


def get_address_public_memos(address: str):
    """
    Query memos for a given address from the CryptoAddress table, returning a list of dicts with id, notes, memo_type, and timestamp.
    """
    from database.connection import SessionLocal

    db = SessionLocal()
    results = (
        db.query(CryptoAddress)
        .filter(
            CryptoAddress.address == address,
            CryptoAddress.notes.isnot(None),
            CryptoAddress.notes != "",
            CryptoAddress.memo_type == "public",
        )
        .order_by(CryptoAddress.blockchain, CryptoAddress.id)
        .all()
    )
    memos = []
    for r in results:
        memos.append(
            {
                "id": r.id,
                "notes": r.notes,
                "memo_type": r.memo_type,
                "timestamp": r.memo_updated_at or r.detected_at,
            }
        )
    db.close()
    return memos
