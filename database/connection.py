"""
Database connection management for Rebot.
Supports SQLite by default with easy migration path to PostgreSQL.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# Database configuration
# Change DATABASE_TYPE to "postgresql" when ready to migrate
DATABASE_TYPE = os.environ.get("DATABASE_TYPE", "sqlite")

# SQLite configuration (default)
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "rebot.db")

# PostgreSQL configuration (for future use)
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB = os.environ.get("PG_DB", "rebot")

# Build connection string based on database type
if DATABASE_TYPE == "sqlite":
    DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH}"
    connect_args = {"check_same_thread": False}
elif DATABASE_TYPE == "postgresql":
    DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    connect_args = {}
else:
    raise ValueError(f"Unsupported database type: {DATABASE_TYPE}")

# Create SQLAlchemy engine and session
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()

def get_db():
    """Returns a database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()