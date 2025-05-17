"""
Database module for Rebot.
Provides SQLite storage with migration path to PostgreSQL.
"""
from database.connection import engine, Base, get_db, SessionLocal
from database.models import (
    User, Message, Chat, CryptoAddress, Event, 
    CryptoAddressStatus, EventType, ReservedField
)
from database.queries import (
    get_or_create_user, get_or_create_chat, save_message,
    save_crypto_address, update_crypto_address_status, create_event,
    get_recent_messages, get_user_messages, get_addresses_by_status,
    get_address_history
)
from database.schema import create_tables, drop_tables, json_dumps, json_loads

__all__ = [
    # Connection
    'engine', 'Base', 'get_db', 'SessionLocal',
    
    # Models
    'User', 'Message', 'Chat', 'CryptoAddress', 'Event',
    'CryptoAddressStatus', 'EventType', 'ReservedField',
    
    # Queries
    'get_or_create_user', 'get_or_create_chat', 'save_message',
    'save_crypto_address', 'update_crypto_address_status', 'create_event',
    'get_recent_messages', 'get_user_messages', 'get_addresses_by_status',
    'get_address_history',
    
    # Schema & Helpers
    'create_tables', 'drop_tables', 'json_dumps', 'json_loads',
]