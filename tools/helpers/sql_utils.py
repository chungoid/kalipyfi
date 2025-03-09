import sqlite3
from pathlib import Path
from database.db_manager import get_db_connection, fetch_all
from tools.hcxtool.db import get_founds


def get_founds_from_hcxtool(basedir: Path) -> list:
    """
    Opens a database connection using basedir and returns found records from the hcxtool table.
    If the table does not exist, it initializes the schema.
    Assumes that the SSID is at index 4 and the key at index 8 in the record.
    """
    conn = get_db_connection(basedir)
    try:
        query = """
            SELECT id, bssid, date, time, ssid, encryption, latitude, longitude, key 
            FROM hcxtool 
            WHERE key IS NOT NULL AND key != ''
        """
        try:
            founds = fetch_all(conn, query)
        except sqlite3.OperationalError as e:
            if "no such table: hcxtool" in str(e):
                # initialize it
                from tools.hcxtool.db import init_hcxtool_schema
                init_hcxtool_schema(conn)
                founds = fetch_all(conn, query)
            else:
                raise
        return founds
    finally:
        conn.close()
