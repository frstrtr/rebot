# database.py

"""
This module handles database operations for storing and retrieving spammer data.
"""

import json
import sqlite3
from server_config import DATABASE_FILE, LOGGER

# Update the script name for the logger
LOGGER.extra["script_name"] = __name__


def initialize_database():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS spammers (
            user_id TEXT PRIMARY KEY,
            lols_bot_data TEXT,
            cas_chat_data TEXT,
            p2p_data TEXT
        )
    """
    )
    conn.commit()
    conn.close()
    LOGGER.info("Database initialized")


def store_spammer_data(user_id, lols_bot_data, cas_chat_data, p2p_data):
    """Store spammer data in the database."""
    # Convert dictionaries to JSON strings if necessary
    if isinstance(lols_bot_data, dict):
        lols_bot_data = json.dumps(lols_bot_data)
    if isinstance(cas_chat_data, dict):
        cas_chat_data = json.dumps(cas_chat_data)
    if isinstance(p2p_data, dict):
        p2p_data = json.dumps(p2p_data)

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO spammers (user_id, lols_bot_data, cas_chat_data, p2p_data)
        VALUES (?, ?, ?, ?)
    """,
        (user_id, lols_bot_data, cas_chat_data, p2p_data),
    )
    conn.commit()
    conn.close()
    LOGGER.info("\033[7mStored spammer data for user_id: %s\033[0m", user_id)


def retrieve_spammer_data_from_db(user_id):
    """Retrieve spammer data from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT lols_bot_data, cas_chat_data, p2p_data FROM spammers WHERE user_id = ?
    """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        lols_bot_data, cas_chat_data, p2p_data = row
        return {
            "lols_bot_data": lols_bot_data,
            "cas_chat_data": cas_chat_data,
            "p2p_data": p2p_data,
        }
    else:
        return None


def get_all_spammer_ids():
    """Retrieve all spammer IDs from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM spammers")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]
