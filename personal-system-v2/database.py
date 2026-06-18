import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yd_os.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema. Tables will be added in v0.2+."""
    conn = get_connection()
    conn.execute("SELECT 1")
    conn.close()