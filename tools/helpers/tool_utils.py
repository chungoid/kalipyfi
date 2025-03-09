import logging
import subprocess
from datetime import datetime, timedelta
from typing import List, Tuple


def format_scan_display(scan: dict) -> str:
    """
    Format a ScanData dictionary for display.

    Parameters
    ----------
    scan : dict
        A dictionary representation of a ScanData object.
        See common/models.py for reference.

    Returns
    -------
    str
        A formatted string in the form:
        "tool | interface | preset_description | elapsed_time"

        For example, if the scan's internal name is
        "hcxtool_wlan1_passive_1741045426" and the scan has been running for 3 minutes and 15 seconds,
        the returned string would be:

        "hcxtool | wlan1 | passive | 0:03:15"
    """
    # Try to extract the tool, interface, and preset description from internal_name.
    internal_name = scan.get("internal_name", "")
    parts = internal_name.split("_")
    if len(parts) >= 3:
        tool_str = parts[0]
        interface_str = parts[1]
        preset_desc = parts[2]
    else:
        # Fall back to other keys if internal_name isn't in the expected format.
        tool_str = scan.get("tool", "unknown")
        interface_str = scan.get("interface", "unknown")
        # If scan_profile exists, assume it is formatted like "wlan1_passive" and take the second part.
        scan_profile = scan.get("scan_profile", "")
        if "_" in scan_profile:
            preset_desc = scan_profile.split("_")[-1]
        else:
            preset_desc = "N/A"

    # Compute elapsed time from the raw timestamp.
    raw_ts = scan.get("timestamp")
    if raw_ts:
        start_time = datetime.fromtimestamp(raw_ts)
        elapsed = datetime.now() - start_time
        # Format elapsed time as H:MM:SS.
        elapsed_str = str(timedelta(seconds=round(elapsed.total_seconds())))
    else:
        elapsed_str = "N/A"

    return f"{tool_str} | {interface_str} | {preset_desc} | {elapsed_str}"

def get_connected_interfaces(logger: logging.Logger) -> List[str]:
    """
    Uses nmcli to retrieve a list of devices that are currently in the 'connected' state.
    Returns a list of interface names.
    """
    cmd = ["nmcli", "-t", "-f", "DEVICE,STATE", "device"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        logger.error(f"Error retrieving connected interfaces: {e}")
        return []
    connected = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            device, state = parts[0].strip(), parts[1].strip()
            if state.lower() == "connected":
                connected.append(device)
    logger.debug(f"Connected interfaces: {connected}")
    return connected

def get_wifi_networks(interface: str, logger: logging.Logger) -> List[Tuple[str, str]]:
    """
    Uses nmcli to scan for available networks on the specified interface.
    Returns a list of tuples in the form (SSID, SECURITY).
    """
    cmd = ["sudo", "nmcli", "-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "ifname", interface]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        logger.error(f"nmcli scan failed: {e}")
        return []
    networks = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            ssid = parts[0].strip()
            security = parts[1].strip()
            networks.append((ssid, security))
    return networks

