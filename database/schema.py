"""
Database schema initialization for Rebot.
"""
import json
import logging
from database.connection import Base, engine
from database.models import (
    User, Chat, Message, CryptoAddress, Event, ReservedField,
    CryptoAddressStatus, EventType, MemoType # Added MemoType
)

def serialize_enum(obj):
    """Helper to serialize enum values for JSON storage"""
    if isinstance(obj, (CryptoAddressStatus, EventType, MemoType)): # Added MemoType
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def create_tables():
    """Create all tables in the database"""
    logging.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logging.info("Database tables created successfully")

def drop_tables():
    """Drop all tables in the database"""
    logging.warning("Dropping all database tables!")
    Base.metadata.drop_all(bind=engine)
    logging.info("Database tables dropped")

def json_dumps(data):
    """Helper function to dump data to JSON string with enum handling"""
    if data is None:
        return None
    return json.dumps(data, default=serialize_enum)

def json_loads(data_str):
    """Helper function to load JSON string to Python object"""
    if not data_str:
        return None
    try:
        return json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        logging.error(f"Failed to decode JSON: {data_str}")
        return {}