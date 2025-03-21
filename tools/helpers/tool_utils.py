
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
def wait_for_association(interface, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        output = subprocess.check_output(["iw", "dev", interface, "link"], text=True)
        if "Connected to" in output:
            return True
        time.sleep(1)
    return False

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

def get_available_wireless_interfaces(logger: logging.Logger) -> List[str]:
    """
    Uses nmcli to retrieve a list of devices that are wireless (TYPE == wifi)
    and are not 'unmanaged'. This returns both connected and disconnected wireless interfaces.
    """
    cmd = ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        logger.error(f"Error retrieving interfaces: {e}")
        return []
    available = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            device, dev_type, state = parts[0].strip(), parts[1].strip(), parts[2].strip()
            # accept any managed Wi-Fi iface
            if dev_type.lower() == "wifi" and state.lower() != "unmanaged":
                available.append(device)
    logger.debug(f"Available wireless interfaces: {available}")
    return available

def get_available_ethernet_interfaces(logger: logging.Logger) -> List[str]:
    """
    Uses nmcli to retrieve a list of devices that are ethernet and are not 'unmanaged'.
    Returns a list of ethernet interface names.
    """
    cmd = ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        logger.error(f"Error retrieving ethernet interfaces: {e}")
        return []
    available = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            device, dev_type, state = parts[0].strip(), parts[1].strip(), parts[2].strip()
            # Accept ethernet devices that are not marked as unmanaged.
            if dev_type.lower() == "ethernet" and state.lower() != "unmanaged":
                available.append(device)
    logger.debug(f"Available ethernet interfaces: {available}")
    return available

def get_wifi_networks(interface: str, logger: logging.Logger) -> List[Tuple[str, str]]:
    """
    Uses nmcli to scan for available networks on the specified interface.
    Returns a list of tuples in the form (SSID, SECURITY).
    """
    cmd = ["nmcli", "-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "ifname", interface]
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
            logger.debug(f"parsed ssid: {ssid} & parsed bssid:{bssid}")
    logger.debug(f"parsed results: {results}")
    return results

def get_interface_mode(interface: str, logger: logging.Logger) -> str:
    """
    Returns the current mode for the given interface by parsing the output of:
        iw dev <interface> info
    Typically, the mode is indicated as "managed", "monitor", etc.
    Returns an empty string if mode cannot be determined.
    """
    try:
        output = subprocess.check_output(
            ["iw", "dev", interface, "info"],
            stderr=subprocess.DEVNULL,
            text=True
        )
        # find mode
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("type"):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1].lower()
    except Exception as e:
        logger.error(f"Error getting mode for interface {interface}: {e}")
    return ""

def switch_interface_to_managed(interface: str, logger: logging.Logger) -> bool:
    """
    Attempts to switch the specified interface to managed mode.
    The typical sequence is:
      1. Bring the interface down.
      2. Change its mode to managed.
      3. Bring the interface up.
    Returns True if successful, False otherwise.
    """
    try:
        subprocess.check_call(["ip", "link", "set", interface, "down"],
                              stderr=subprocess.DEVNULL)
        subprocess.check_call(["iw", "dev", interface, "set", "type", "managed"],
                              stderr=subprocess.DEVNULL)
        subprocess.check_call(["ip", "link", "set", interface, "up"],
                              stderr=subprocess.DEVNULL)
        logger.info(f"Interface {interface} switched to managed mode.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error switching interface {interface} to managed mode: {e}")
    return False

def switch_interface_to_monitor(interface: str, logger: logging.Logger) -> bool:
    """
    Attempts to switch the specified interface to monitor mode.
    The typical sequence is:
      1. Bring the interface down.
      2. Change its mode to monitor.
      3. Bring the interface up.
    Returns True if successful, False otherwise.
    """
    try:
        subprocess.check_call(["ip", "link", "set", interface, "down"], stderr=subprocess.DEVNULL)
        subprocess.check_call(["iw", "dev", interface, "set", "type", "monitor"], stderr=subprocess.DEVNULL)
        subprocess.check_call(["ip", "link", "set", interface, "up"], stderr=subprocess.DEVNULL)
        logger.info(f"Interface {interface} switched to monitor mode.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error switching interface {interface} to monitor mode: {e}")
    return False


def normalize_mac(mac: str) -> str:
    """
    Normalizes a MAC address to the format aa:bb:cc:dd:ee:ff.
    Removes any non-alphanumeric characters, ensures lowercase, and then
    reinserts colons every two characters if the MAC has exactly 12 hex digits.
    """
    if not mac:
        return ""
    mac = "".join(c for c in mac if c.isalnum()).upper()
    if len(mac) == 12:
        return ":".join(mac[i:i+2] for i in range(0, 12, 2))
    return mac





