# utils/db_manager.py
import sqlite3
from pathlib import Path

def get_hidden_db_path(basedir: Path, db_filename: str = "kalipyfi.sqlite3") -> Path:
    parent_dir = basedir.parent
    hidden_dir = parent_dir / f".{basedir.name}"
    hidden_dir.mkdir(exist_ok=True)
    return hidden_dir / db_filename

def get_db_connection(basedir: Path) -> sqlite3.Connection:
    db_path = get_hidden_db_path(basedir)
    conn = sqlite3.connect(db_path)
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool1_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool2_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        info TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shared_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tool_name TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

def insert_shared_data(conn: sqlite3.Connection, tool_name: str, key: str, value: str) -> None:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shared_data (tool_name, key, value) VALUES (?, ?, ?)",
                   (tool_name, key, value))
    conn.commit()

def query_shared_data(conn: sqlite3.Connection, key: str):
    cursor = conn.cursor()
    cursor.execute("SELECT tool_name, value, created_at FROM shared_data WHERE key = ?", (key,))
    return cursor.fetchall()

def execute_query(conn: sqlite3.Connection, query: str, params: tuple = ()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    return cursor

def fetch_all(conn: sqlite3.Connection, query: str, params: tuple = ()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()

