"""
SQLAlchemy models for Rebot database.
Compatible with both SQLite and PostgreSQL.
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, 
    ForeignKey, Boolean, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declared_attr

from database.connection import Base

# Use TEXT type for JSON in SQLite
try:
    from sqlalchemy.dialects.postgresql import JSONB
    JsonType = JSONB
except ImportError:
    JsonType = JSON

class MemoType(enum.Enum):
    """Type of memo for a crypto address"""
    PUBLIC = "public"        # Visible to all users who can see the address
    PRIVATE = "private"      # Visible only to the user who added it (requires user tracking for memos)
    ENCRYPTED = "encrypted"  # Content is encrypted, accessible with a key (key management not included here)
    ADMIN = "admin"          # Visible only to administrators
    OTHER = "other"          # A generic type if none of the above fit

class CryptoAddressStatus(enum.Enum):
    """Status of a crypto address"""
    UNKNOWN = "unknown"
    CLEAN = "clean"
    SCAM = "scam"
    TO_CHECK = "to_check"
    INVESTIGATION = "investigation"

class EventType(enum.Enum):
    """Types of events tracked in the system"""
    USER_JOIN = "user_join"
    USER_LEAVE = "user_leave"
    MESSAGE_RECEIVED = "message_received"
    COMMAND_EXECUTED = "command_executed"
    ADDRESS_DETECTED = "address_detected"
    ADDRESS_STATUS_CHANGE = "address_status_change"
    CUSTOM = "custom"

class User(Base):
    """User information"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), nullable=True)
    is_bot = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    messages = relationship("Message", back_populates="user")
    events = relationship("Event", back_populates="user")
    
    # Reserved fields for future use (compatible with SQLite and PostgreSQL)
    reserved_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite

class Chat(Base):
    """Chat information"""
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    type = Column(String(20), nullable=False)  # private, group, supergroup, channel
    title = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("Message", back_populates="chat")
    
    # Reserved fields for future use
    reserved_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite

class Message(Base):
    """Message information"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    text = Column(Text, nullable=True)
    date = Column(DateTime, nullable=False)
    is_command = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Store full message data as JSON
    raw_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite
    
    # Relationships
    user = relationship("User", back_populates="messages")
    chat = relationship("Chat", back_populates="messages")
    crypto_addresses = relationship("CryptoAddress", back_populates="message")
    
    # Reserved fields for future use
    reserved_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite

class CryptoAddress(Base):
    """Cryptocurrency address information"""
    __tablename__ = "crypto_addresses"

    id = Column(Integer, primary_key=True)
    address = Column(String(255), nullable=False, index=True)
    blockchain = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="to_check")  # Using string for enum compatibility
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True) # MODIFIED: Allow null for API-added addresses
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    message = relationship("Message", back_populates="crypto_addresses")
    events = relationship("Event", back_populates="crypto_address")
    
    # Memo fields
    notes = Column(Text, nullable=True) # Stores the actual memo content
    memo_type = Column(String(20), nullable=True) # Stores the type of the memo, maps to MemoType enum
    memo_added_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Optional: track who added/updated the memo
    memo_updated_at = Column(DateTime, nullable=True) # Optional: track when the memo was last updated

    # Reserved fields for future use
    risk_score = Column(Float, nullable=True)
    investigation_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite
    reserved_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite

    # Optional: Relationship for memo_added_by_user_id
    memo_added_by = relationship("User", foreign_keys=[memo_added_by_user_id])

class Event(Base):
    """Event information"""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    type = Column(String(30), nullable=False)  # Using string for enum compatibility
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    crypto_address_id = Column(Integer, ForeignKey("crypto_addresses.id"), nullable=True)
    data = Column(Text, nullable=True)  # Stores JSON as text in SQLite
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="events")
    crypto_address = relationship("CryptoAddress", back_populates="events")
    
    # Reserved fields for future use
    reserved_data = Column(Text, nullable=True)  # Stores JSON as text in SQLite

class UserWatchState(Base):
    """Stores per-user watch state for memos and blockchain events on addresses."""
    __tablename__ = "user_watch_states"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    address = Column(String(255), nullable=False, index=True)
    blockchain = Column(String(50), nullable=False, index=True)
    watch_memos = Column(Boolean, default=False, nullable=False)
    watch_events = Column(Boolean, default=False, nullable=False)
    last_memo_id = Column(Integer, nullable=True)  # New: last memo id seen for this address
    last_state = Column(Text, nullable=True)  # New: JSON-serialized last state for this address
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="watch_states")

# Additional tables for future use
class ReservedField(Base):
    """Reserved fields for future use"""
    __tablename__ = "reserved_fields"

    id = Column(Integer, primary_key=True)
    field_name = Column(String(100), nullable=False)
    field_type = Column(String(50), nullable=False)  # string, int, float, json, etc.
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    
    # When this field was created and last updated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)