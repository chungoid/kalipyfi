import sqlite3


def init_pyfyconnect_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the pyfyconnect schema with only bssid, ssid, and key.
    A created_at timestamp is added by default.
    """
    query = """
    CREATE TABLE IF NOT EXISTS pyfyconnect (
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


def sync_pyfyconnect_from_hcxtool(conn: sqlite3.Connection, hcxtool_db: str) -> None:
    """
    Synchronizes entries from the hcxtool database into the pyfyconnect table.
    Only rows where both bssid and key are available are considered.
    For each such row, only the bssid, ssid, and key columns are imported.
    On conflict (same bssid and ssid), the key is updated.

    :param conn: sqlite3.Connection to the pyfyconnect database.
    :param hcxtool_db: Path to the hcxtool database file.
    """
    # get bssid, ssid, key from hcxtool table
    hcxtool_conn = sqlite3.connect(hcxtool_db)
    hcxtool_conn.row_factory = sqlite3.Row
    cur = hcxtool_conn.cursor()
    query = """
    SELECT bssid, ssid, key
    FROM hcxtool
    WHERE bssid IS NOT NULL AND key IS NOT NULL
      AND bssid <> '' AND key <> ''
    """
    cur.execute(query)
    rows = cur.fetchall()
    hcxtool_conn.close()

    # update otherwise insert (upsert)
    upsert_query = """
    INSERT INTO pyfyconnect (bssid, ssid, key)
    VALUES (?, ?, ?)
    ON CONFLICT(bssid, ssid) DO UPDATE SET
        key = excluded.key;
    """
    cur = conn.cursor()
    for row in rows:
        cur.execute(upsert_query, (row["bssid"], row["ssid"], row["key"]))
    conn.commit()