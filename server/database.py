# database.py

"""
This module handles database operations for storing and retrieving spammer data.
"""

import os
import sys
import sqlite3
import time

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from server.server_config import DATABASE_FILE, LOGGER


def initialize_database():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            ALTER TABLE spammers ADD COLUMN timestamp INTEGER DEFAULT 0
            """
        )
        conn.commit()
        LOGGER.info("Added timestamp column to spammers table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            LOGGER.info("timestamp column already exists in spammers table")
    try:
        cursor.execute(
            """
            ALTER TABLE spammers ADD COLUMN is_spammer BOOLEAN DEFAULT FALSE
            """
        )
        conn.commit()
        LOGGER.info("Added is_spammer column to spammers table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            LOGGER.info("is_spammer column already exists in spammers table")
        else:
            LOGGER.error("Error adding is_spammer column: %s", e)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS spammers (
            user_id TEXT PRIMARY KEY,
            lols_bot_data TEXT,
            cas_chat_data TEXT,
            p2p_data TEXT,
            is_spammer BOOLEAN DEFAULT FALSE,
            timestamp INTEGER DEFAULT 0
        )
    """
    )
    conn.commit()
    conn.close()
    LOGGER.info("Database initialized")


def store_spammer_data(
    user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer=False
):
    timestamp = int(time.time())  # Get current timestamp
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO spammers (user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer, timestamp),
    )
    conn.commit()
    conn.close()
    LOGGER.info("%s stored spammer data", user_id)


def delete_spammer_data(user_id):
    """Remove spammer data from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM spammers WHERE user_id = ?
        """,
        (user_id,),
    )
    conn.commit()
    conn.close()
    LOGGER.info("%s removed from spammer data", user_id)
    LOGGER.info("Removed spammer data for user_id: %s", user_id)


def retrieve_spammer_data_from_db(user_id):
    """Retrieve spammer data from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT lols_bot_data, cas_chat_data, p2p_data, is_spammer FROM spammers WHERE user_id = ?
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        lols_bot_data, cas_chat_data, p2p_data, is_spammer = row
        return {
            "lols_bot_data": lols_bot_data,
            "cas_chat_data": cas_chat_data,
            "p2p_data": p2p_data,
            "is_spammer": is_spammer,
        }
    return None


def get_all_spammer_ids():
    """Retrieve all spammer IDs from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM spammers")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]
