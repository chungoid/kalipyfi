# tools/hcxtool/db.py
import sqlite3
from database.db_manager import execute_query, fetch_all

def init_hcxtool_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the database schema for hcxtool.
    This table is based on the results.csv format with columns:
    Date, Time, BSSID, SSID, Encryption, Latitude, Longitude, Key.
    """
    query = """
    CREATE TABLE IF NOT EXISTS hcxtool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bssid TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    ssid TEXT,
    encryption TEXT,
    latitude REAL,
    longitude REAL,
    key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bssid, ssid)
);
    """
    execute_query(conn, query)

def insert_hcxtool_results(conn: sqlite3.Connection,
                          date: str,
                          time: str,
                          bssid: str,
                          ssid: str,
                          encryption: str,
                          latitude: float,
                          longitude: float,
                          key_value: str) -> None:
    """
    Inserts a new result record into the hcxtool table.
    If a record with the same bssid and ssid exists, it will be replaced.
    """
    query = """
    INSERT OR REPLACE INTO hcxtool (date, time, bssid, ssid, encryption, latitude, longitude, key)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    execute_query(conn, query, (date, time, bssid, ssid, encryption, latitude, longitude, key_value))


def fetch_all_hcxtool_results(conn: sqlite3.Connection):
    """
    Fetches all records from the hcxtool table.
    """
    query = "SELECT * FROM hcxtool"
    return fetch_all(conn, query)


def get_founds(conn: sqlite3.Connection) -> list:
    """
    Retrieves all records from the hcxtool table that have a non-empty key value.

    Parameters:
        conn (sqlite3.Connection): The connection to the hcxtool database.

    Returns:
        list: A list of tuples representing the found records. Each tuple includes:
              (id, bssid, date, time, ssid, encryption, latitude, longitude, key)
    """
    query = """
    SELECT id, bssid, date, time, ssid, encryption, latitude, longitude, key 
    FROM hcxtool 
    WHERE key IS NOT NULL AND key != ''
    """
    return fetch_all(conn, query)
