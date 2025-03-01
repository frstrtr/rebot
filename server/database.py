# database.py

"""
This module handles database operations for storing and retrieving spammer data.
"""

import sqlite3
from server_config import DATABASE_FILE, LOGGER


def initialize_database():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
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
            is_spammer BOOLEAN DEFAULT FALSE
        )
    """
    )
    conn.commit()
    conn.close()
    LOGGER.info("Database initialized")


def store_spammer_data(
    user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer=False
):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO spammers (user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer)
        VALUES (?, ?, ?, ?, ?)
    """,
        (user_id, lols_bot_data, cas_chat_data, p2p_data, is_spammer),
    )
    conn.commit()
    conn.close()
    LOGGER.info("\033[7m%s Stored spammer data\033[0m", user_id)


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
