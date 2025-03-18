
import re
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


logger = logging.getLogger(__name__)

################################
### PROCESS MANAGEMENT UTILS ###
################################
def wait_for_scan_process(scan_pid: int, timeout: int = 300, poll_interval: int = 2) -> bool:
    """
    Waits until the process with scan_pid terminates.

    :param scan_pid: Process ID
    :param timeout: Time to wait in seconds
    :param poll_interval: Time to wait in seconds between polling
    :return: True if process with scan_pid terminates, False otherwise
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

    :param config_path: Path to the YAML configuration file.
    :param key_path: Path to the nested key to update.
    :param new_value: New value to update the nested key with.
    :return: None
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

    :param scan: ScanData dictionary
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
def get_all_connected_interfaces(logger: logging.Logger) -> List[str]:
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

def get_connected_wireless_interfaces(logger: logging.Logger) -> List[str]:
    """
    Uses nmcli to retrieve a list of devices that are currently in the 'connected'
    state and are wireless (TYPE == wifi).
    Returns a list of wireless interface names.
    """
    cmd = ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        logger.error(f"Error retrieving connected interfaces: {e}")
        return []
    connected = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            device, dev_type, state = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if state.lower() == "connected" and dev_type.lower() == "wifi":
                connected.append(device)
    logger.debug(f"Connected wireless interfaces: {connected}")
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

    :param interface: Interface name
    :return A string representing the network in CIDR notation or an empty string gif the network cannot be determined.
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
    Get default and non-default gateways for all associated interfaces from netifaces.AF_INET.

    :return: a dictionary mapping each network interface to its IPv4 gateway.
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

    logging.debug(f"gateways: {gateways}")
    return gateways

def parse_nmcli_ssid_bssid(output: str) -> list:
    """
    Parses nmcli output from a command like:
      nmcli -f SSID,BSSID device wifi list ifname <interface>
    and returns a list of dictionaries:
      [{"ssid": "MyHomeWiFi", "bssid": "AA:BB:CC:DD:EE:FF"}, ...]

    It assumes the first line is a header and that columns are separated by at least two spaces.

    :param output: Raw output from nmcli.
    :return: List of dictionaries with 'ssid' and 'bssid' keys.
    """
    lines = output.strip().splitlines()
    if not lines:
        return []

    # remove the header line
    data_lines = lines[1:]
    results = []

    for line in data_lines:
        if not line.strip():
            continue  # skip empty lines
        # split the line on two or more whitespace characters.
        parts = re.split(r'\s{2,}', line.strip())
        if len(parts) >= 2:
            ssid, bssid = parts[0], parts[1]
            results.append({"ssid": ssid, "bssid": bssid})
    return results




