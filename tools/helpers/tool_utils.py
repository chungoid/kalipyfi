
import yaml
import time
import psutil
import logging
import netifaces
import ipaddress
import subprocess
from pathlib import Path
from typing import List, Tuple
from datetime import datetime, timedelta


logger = logging.getLogger("tools/tool_utils")

################################
### PROCESS MANAGEMENT UTILS ###
################################
def wait_for_scan_process(scan_pid: int, timeout: int = 300, poll_interval: int = 2) -> bool:
    """
    Waits until the process with scan_pid terminates.

    Returns True if the process ends before the timeout; otherwise False.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not psutil.pid_exists(scan_pid):
            return True
        time.sleep(poll_interval)
    return False

################################
### FILE/UI FORMATTING UTILS ###
################################
def update_yaml_value(config_path: Path, key_path: list, new_value) -> None:
    """
    Updates the YAML configuration file at the specified config_path by setting the
    nested key defined by key_path to new_value.

    Parameters
    ----------
    config_path : Path
        The path to the YAML configuration file.
    key_path : list
        A list of keys representing the nested path to the desired value.
        For example, ["wpa-sec", "api_key"].
    new_value :
        The new value to set at the specified key path.

    Returns
    -------
    None

    Raises
    ------
    Exception
        If there is an error reading from or writing to the configuration file.
    """
    try:
        with config_path.open("r") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load configuration file {config_path}: {e}")
        raise

    sub_config = config
    for key in key_path[:-1]:
        if key not in sub_config or not isinstance(sub_config[key], dict):
            sub_config[key] = {}
        sub_config = sub_config[key]

    sub_config[key_path[-1]] = new_value

    try:
        with config_path.open("w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Updated {'.'.join(key_path)} to {new_value} in {config_path}")
    except Exception as e:
        logger.error(f"Failed to write updated configuration to {config_path}: {e}")
        raise

def format_scan_display(scan: dict) -> str:
    """
    Format a ScanData dictionary for display.

    The displayed information includes:
      - Tool name.
      - Scan interface.
      - Preset description (the description from the scan preset).
      - Elapsed time since the scan started.

    Parameters
    ----------
    scan : dict
        A dictionary representation of a ScanData object.

    Returns
    -------
    str
        A formatted string in the form:
        "tool | interface | preset_description | elapsed_time"
    """
    tool_str = scan.get("tool", "unknown")
    interface_str = scan.get("interface", "unknown")
    preset_desc = scan.get("preset_description", "N/A")
    raw_ts = scan.get("timestamp")
    if raw_ts:
        start_time = datetime.fromtimestamp(raw_ts)
        elapsed = datetime.now() - start_time
        elapsed_str = str(timedelta(seconds=round(elapsed.total_seconds())))
    else:
        elapsed_str = "N/A"

    return f"{tool_str} | {interface_str} | {preset_desc} | {elapsed_str}"

#######################################################
### OS/HARDWARE/NETWORK INFORMATION GATHERING UTILS ###
#######################################################
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

def get_network_from_interface(interface: str) -> str:
    """
    Given an interface name, retrieves its IPv4 address and netmask,
    then computes the network in CIDR notation.

    Returns:
        A string representation of the network (e.g., "192.168.1.0/24"),
        or an empty string if the network cannot be determined.
    """
    try:
        addresses = netifaces.ifaddresses(interface)
        inet_info = addresses.get(netifaces.AF_INET, [{}])[0]
        ip_addr = inet_info.get("addr")
        netmask = inet_info.get("netmask")
        if ip_addr and netmask:
            # Create an IPv4Interface object which provides the network
            iface = ipaddress.IPv4Interface(f"{ip_addr}/{netmask}")
            network = iface.network
            return str(network)
    except Exception as e:
        logging.error(f"Error retrieving network for interface {interface}: {e}")
    return ""

def get_gateways() -> dict:
    """
    Returns a dictionary mapping each network interface to its IPv4 gateway.
    Uses netifaces to extract default and non-default gateways.
    """
    gateways = {}
    gateways_info = netifaces.gateways()

    # Process default gateways for IPv4.
    default_gateways = gateways_info.get("default", {})
    if netifaces.AF_INET in default_gateways:
        gateway, interface = default_gateways[netifaces.AF_INET]
        gateways[interface] = gateway

    # Process non-default IPv4 gateways.
    if netifaces.AF_INET in gateways_info:
        for entry in gateways_info[netifaces.AF_INET]:
            gateway, interface, _ = entry
            if interface not in gateways:
                gateways[interface] = gateway

    return gateways



