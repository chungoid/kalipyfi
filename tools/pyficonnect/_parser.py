import logging
import sqlite3
import time

# locals
from database.db_manager import get_db_connection, fetch_all
from tools.helpers.tool_utils import normalize_mac

logger = logging.getLogger(__name__)
############################
##### ALERT FORMATTING #####
############################

def _alert_nearby_from_db(alert_data: dict):
    ssid = alert_data.get("ssid")
    timestamp = alert_data.get("timestamp")
    time_passed = time.time() - timestamp
    formatted_message = f"Network Found: {ssid} ({time_passed:.2f}s)"
    return formatted_message

def get_pyficonnect_networks_from_db(basedir) -> list:
    """
    Retrieves all networks from the pyficonnect table.

    Parameters:
        basedir: Base directory to use when obtaining the database connection.

    Returns:
        A list of tuples (bssid, ssid, key) where bssid is not null or empty.
    """
    conn = get_db_connection(basedir)
    query = """
        SELECT bssid, ssid, key
        FROM pyficonnect
        WHERE bssid IS NOT NULL AND bssid <> ''
    """
    try:
        rows = fetch_all(conn, query)
        logger.debug(f"Retrieved {len(rows)} records from pyficonnect table.")
    except sqlite3.Error as e:
        logger.error(f"Error querying pyficonnect table: {e}")
        rows = []
    finally:
        conn.close()
    return rows

def format_pyficonnect_networks(rows: list) -> dict:
    """
    Formats a list of pyficonnect table rows into a dictionary keyed by normalized BSSID.

    Each entry in the resulting dictionary is structured as:
        {
            "NORMALIZED_BSSID": {"ssid": <SSID>, "key": <KEY>}
        }

    Parameters:
        rows: List of tuples (bssid, ssid, key) as returned from the database.

    Returns:
        A dictionary with normalized BSSID as keys.
    """
    networks = {}
    for row in rows:
        try:
            bssid, ssid, key = row
            norm_bssid = normalize_mac(bssid)
            logger.debug(f"Formatting network: raw BSSID {bssid} normalized to {norm_bssid}, SSID: {ssid}, Key: {key}")
            networks[norm_bssid] = {"ssid": ssid, "key": key}
        except Exception as e:
            logger.error(f"Error formatting row {row}: {e}")
    logger.debug(f"Formatted networks dict keys: {list(networks.keys())}")
    return networks