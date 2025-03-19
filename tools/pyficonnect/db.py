import logging
import sqlite3

logger = logging.getLogger(__name__)

def init_pyfyconnect_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the pyficonnect schema with only bssid, ssid, and key.
    A created_at timestamp is added by default.
    """
    query = """
    CREATE TABLE IF NOT EXISTS pyficonnect (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bssid TEXT NOT NULL,
        ssid TEXT,
        key TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(bssid, ssid)
    );
    """
    conn.execute(query)
    conn.commit()


def safe_sync_pyfyconnect_from_hcxtool(conn: sqlite3.Connection) -> None:
    """
    Safely synchronizes entries from the hcxtool table into the pyficonnect table.
    If the hcxtool table doesn't exist or no valid data is available, this function logs
    the situation and exits gracefully.
    """
    try:
        cursor = conn.cursor()
        # check if the hcxtool table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hcxtool'")
        if not cursor.fetchone():
            logger.info("hcxtool table does not exist. Skipping sync.")
            return

        # perform upsert sync
        upsert_query = """
        INSERT INTO pyficonnect (bssid, ssid, key)
        SELECT bssid, ssid, key FROM hcxtool
        WHERE bssid IS NOT NULL AND key IS NOT NULL
          AND bssid <> '' AND key <> ''
        ON CONFLICT(bssid, ssid) DO UPDATE SET
            key = excluded.key;
        """
        conn.execute(upsert_query)
        conn.commit()
        logger.info("Successfully synchronized pyficonnect table from hcxtool table.")
    except sqlite3.Error as e:
        logger.error(f"Error during sync from hcxtool: {e}")