import logging
import sqlite3
from pathlib import Path
from database.db_manager import get_db_connection, fetch_all

logger = logging.getLogger(__name__)

##################################
##### GET FROM HCXTOOL TABLE #####
##################################
def get_founds_ssid_and_key(basedir: Path) -> list:
    """
    Opens a database connection using the given basedir and returns a list of tuples (ssid, key)
    from the hcxtool table where key is non-empty.
    """
    conn = get_db_connection(basedir)
    try:
        query = """
            SELECT ssid, key 
            FROM hcxtool 
            WHERE key IS NOT NULL AND key != ''
        """
        try:
            results = fetch_all(conn, query)
        except sqlite3.OperationalError as e:
            if "no such table: hcxtool" in str(e):
                from tools.hcxtool.db import init_hcxtool_schema
                init_hcxtool_schema(conn)
                results = fetch_all(conn, query)
            else:
                raise
        return results
    finally:
        conn.close()

def get_founds_bssid_ssid_and_key(basedir: Path) -> list:
    """
    Opens a database connection using the given basedir and returns a list of tuples
    (bssid, ssid, key) from the hcxtool table where key is non-empty.

    If the hcxtool table does not exist, it will be initialized.
    """
    conn = get_db_connection(basedir)
    try:
        query = """
            SELECT bssid, ssid, key
            FROM hcxtool
            WHERE key IS NOT NULL AND key != ''
        """
        try:
            results = fetch_all(conn, query)
        except sqlite3.OperationalError as e:
            if "no such table: hcxtool" in str(e):
                from tools.hcxtool.db import init_hcxtool_schema
                init_hcxtool_schema(conn)
                results = fetch_all(conn, query)
            else:
                raise
        return results
    finally:
        conn.close()


