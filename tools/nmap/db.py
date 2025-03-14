# tools/nmap/db.py
import sqlite3
from database.db_manager import execute_query, fetch_all


def init_nmap_network_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the database schema for nmap network scans.
    This table stores overall CIDR scan results.

    Columns:
      - id: Auto-incremented primary key.
      - cidr: The scanned network (e.g., "192.168.1.0/24").
      - station_mac: The MAC address of the scanning interface.
      - router_ip: The router's IP address.
      - bssid: The router's MAC address (BSSID) if available.
      - scan_date: The date the scan was performed.
      - scan_time: The time the scan was performed.
      - created_at: Timestamp of record creation.

    The UNIQUE constraint (cidr, station_mac) helps avoid duplicate records.
    """
    query = """
    CREATE TABLE IF NOT EXISTS nmap_network (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bssid TEXT,
        station_mac TEXT,
        cidr TEXT NOT NULL,
        router_ip TEXT,
        router_hostname TEXT,
        hosts TEXT, -- JSON blob containing hosts (IP, hostname)
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bssid, cidr)
);
    """
    execute_query(conn, query)


def init_nmap_host_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the database schema for nmap host scans.
    This table stores detailed scan information for each host discovered
    in a network scan.

    Columns:
      - id: Auto-incremented primary key.
      - network_id: Foreign key referencing the nmap_network table.
      - host_ip: The host's IP address.
      - open_ports: Text (or JSON) representation of open ports.
      - services: Text (or JSON) representation of discovered services.
      - scan_date: Date when the host scan was performed.
      - scan_time: Time when the host scan was performed.
      - created_at: Timestamp of record creation.

    The UNIQUE constraint (network_id, host_ip) ensures that each host is only
    recorded once per network scan.
    """
    query = """
    CREATE TABLE IF NOT EXISTS nmap_host (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        network_id INTEGER NOT NULL,
        host_ip TEXT NOT NULL,
        open_ports TEXT,
        services TEXT,
        scan_date TEXT NOT NULL,
        scan_time TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(network_id, host_ip),
        FOREIGN KEY(network_id) REFERENCES nmap_network(id) ON DELETE CASCADE
    );
    """
    execute_query(conn, query)


def insert_nmap_network_result(conn: sqlite3.Connection,
                               bssid: str,
                               station_mac: str,
                               cidr: str,
                               router_ip: str,
                               router_hostname: str,
                               hosts: str) -> int:
    """
    Inserts a new record into the nmap_network table.

    Parameters:
      - bssid: The router's MAC address (BSSID), if available.
      - station_mac: The MAC address of the scanning interface.
      - cidr: The scanned network (e.g., "192.168.1.0/24").
      - router_ip: The IP address of the router.
      - router_hostname: The hostname of the router.
      - hosts: A JSON blob containing host information (list of dicts with host IPs and hostnames).

    Returns:
      The inserted record's id.
    """
    query = """
    INSERT OR REPLACE INTO nmap_network (bssid, station_mac, cidr, router_ip, router_hostname, hosts)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    cursor = execute_query(conn, query, (bssid, station_mac, cidr, router_ip, router_hostname, hosts))
    return cursor.lastrowid


def insert_nmap_host_result(conn: sqlite3.Connection,
                            network_id: int,
                            host_ip: str,
                            open_ports: str,
                            services: str,
                            scan_date: str,
                            scan_time: str) -> None:
    """
    Inserts a new record into the nmap_host table.

    Parameters:
      - network_id: The foreign key linking this host scan to an nmap_network record.
      - host_ip: The host's IP address.
      - open_ports: A text (or JSON) representation of the open ports.
      - services: A text (or JSON) representation of discovered services.
      - scan_date: The date when the host scan was performed.
      - scan_time: The time when the host scan was performed.
    """
    query = """
    INSERT OR REPLACE INTO nmap_host (network_id, host_ip, open_ports, services, scan_date, scan_time)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    execute_query(conn, query, (network_id, host_ip, open_ports, services, scan_date, scan_time))


def fetch_all_nmap_network_results(conn: sqlite3.Connection):
    """
    Fetches all records from the nmap_network table.

    Returns:
      A list of tuples containing network scan results.
    """
    query = "SELECT * FROM nmap_network"
    return fetch_all(conn, query)


def fetch_all_nmap_host_results(conn: sqlite3.Connection):
    """
    Fetches all records from the nmap_host table.

    Returns:
      A list of tuples containing host scan results.
    """
    query = "SELECT * FROM nmap_host"
    return fetch_all(conn, query)
