import logging
import sqlite3
from pathlib import Path
from database.db_manager import get_db_connection, fetch_all
#from tools.hcxtool.db import get_founds


def get_founds_from_hcxtool(basedir: Path) -> list:
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
                from tools.hcxtool.db import init_hcxtool_schema
                init_hcxtool_schema(conn)
                founds = fetch_all(conn, query)
            else:
                raise
        # Log the DB path and found rows for debugging.
        from config.constants import BASE_DIR
        db_path = get_db_connection(basedir).execute("PRAGMA database_list").fetchall()
        logging.debug(f"Database info: {db_path}")
        logging.debug(f"Raw founds returned: {founds}")
        return founds
    finally:
        conn.close()

