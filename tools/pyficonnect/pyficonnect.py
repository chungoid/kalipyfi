import asyncio
import subprocess
import logging
import threading
import time
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any

from scapy.layers.dot11 import Dot11
from scapy.sendrecv import sniff

# locals
from config.constants import BASE_DIR
from database.db_manager import get_db_connection
from tools.pyficonnect.db import init_pyfyconnect_schema, safe_sync_pyfyconnect_from_hcxtool
from tools.pyficonnect.submenu import PyfyConnectSubmenu
from tools.tools import Tool
from utils.tool_registry import register_tool


@register_tool("pyficonnect")
class PyfiConnectTool(Tool, ABC):
    def __init__(self,
                 base_dir: Path,  # pyficonnect module base, not project base
                 config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None,
                 presets: Optional[Dict[str, Any]] = None,
                 ui_instance: Optional[Any] = None) -> None:
        super().__init__(
            name="pyficonnect",
            description="Tool for connecting to a network using wpa_supplicant",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=presets,
            ui_instance=ui_instance
        )
        self.logger = logging.getLogger(self.name.upper())
        self.submenu_instance = PyfyConnectSubmenu(self)
        # submenu user selections
        self.selected_interface = None  # "wlan0, wlan1, etc. from config.yaml"
        self.selected_network = None  # SSID of the network
        self.network_password = None  # Password (if needed)

        # pyficonnect-specific database schema (tools/pyficonnect/db.py)
        conn = get_db_connection(BASE_DIR)
        init_pyfyconnect_schema(conn)
        safe_sync_pyfyconnect_from_hcxtool(conn)
        conn.close()

        # auto-scanning for db match
        self.db_networks = None
        self.scanner_running = False
        self.alerted_networks = {}

    def submenu(self, stdscr) -> None:
        """
        Launches the nmap submenu (interactive UI) using curses.
        """
        self.submenu_instance(stdscr)

    def run(self, profile=None) -> None:
        """
        Connect to the network using nmcli by creating or updating a connection profile.
        The connection profile is named using the SSID and interface (e.g., 'HomeBase-5G_wlan1').
        This method:
          1. Checks if a profile with the desired name already exists.
             - If it exists, it can be updated or removed.
          2. Creates the profile with the SSID, password, and other settings, including:
             - wifi-sec.key-mgmt set to wpa-psk
             - wifi-sec.psk set to the provided password
             - 802-11-wireless-security.psk-flags set to 0 (to store the password permanently)
             - autoconnect disabled
          3. Activates the connection.
        """
        if not self.selected_interface or not self.selected_network:
            self.logger.error("Interface or network not specified!")
            return

        # e.g. ssid_wlan1
        con_name = f"{self.selected_network}_{self.selected_interface}"

        # if it exists delete it
        if self.profile_exists(con_name):
            try:
                del_cmd = ["nmcli", "connection", "delete", con_name]
                self.logger.debug("Profile exists. Deleting existing profile: " + " ".join(del_cmd))
                subprocess.check_call(del_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.logger.info(f"Existing profile '{con_name}' deleted.")
            except Exception as e:
                self.logger.error(f"Error deleting existing profile '{con_name}': {e}")
                return

        try:
            # create connection profile
            add_cmd = [
                "nmcli", "connection", "add",
                "type", "wifi",
                "ifname", self.selected_interface,
                "con-name", con_name,
                "ssid", self.selected_network,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", self.network_password,
                "802-11-wireless-security.psk-flags", "0",
                "autoconnect", "no"
            ]
            self.logger.debug("Running nmcli add command: " + " ".join(add_cmd))
            subprocess.check_call(add_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"Connection '{con_name}' successfully added.")
        except Exception as e:
            self.logger.error(f"Error adding connection profile: {e}")
            return

        try:
            # activate connection
            up_cmd = ["nmcli", "connection", "up", con_name]
            self.logger.debug("Running nmcli connection up command: " + " ".join(up_cmd))
            subprocess.check_call(up_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(
                f"Connected to {self.selected_network} on {self.selected_interface} using profile '{con_name}'.")
        except Exception as e:
            self.logger.error(f"Error activating connection: {e}")
            return

    def profile_exists(self, con_name: str) -> bool:
        """
        Check if a NetworkManager connection profile with the given name already exists.
        """
        try:
            output = subprocess.check_output(
                ["nmcli", "-g", "NAME", "connection", "show"],
                text=True
            )
            # split where a line is a profile name
            existing_profiles = [line.strip() for line in output.splitlines() if line.strip()]
            return con_name in existing_profiles
        except Exception as e:
            self.logger.error(f"Error checking if profile exists: {e}")
            return False

    def disconnect(self) -> None:
        """
        Disconnects from the network using nmcli.

        Uses nmcli to disconnect the selected interface from any network.
        """
        if not self.selected_interface:
            self.logger.error("No interface selected for disconnecting!")
            return

        try:
            disconnect_cmd = ["nmcli", "device", "disconnect", self.selected_interface]
            self.logger.debug("Running nmcli disconnect command: " + " ".join(disconnect_cmd))
            subprocess.check_call(disconnect_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"Disconnected {self.selected_interface} using nmcli")
        except Exception as e:
            self.logger.error(f"Error disconnecting using nmcli: {e}")

    ##################################################
    ##### AUTO-SCAN IN BACKGROUND FOR DB MATCHES #####
    ##################################################

    def load_db_networks(self):
        """
        Loads all rows from the pyficonnect table into a dictionary keyed by normalized BSSID.
        """
        from tools.pyficonnect._parser import get_pyficonnect_networks_from_db, format_pyficonnect_networks
        rows = get_pyficonnect_networks_from_db(BASE_DIR)
        self.db_networks = format_pyficonnect_networks(rows)
        self.logger.debug(f"Loaded DB networks: {list(self.db_networks.keys())}")

    def scapy_packet_handler(self, pkt):
        # Only process 802.11 beacon frames
        from tools.helpers.tool_utils import normalize_mac
        if pkt.haslayer(Dot11) and pkt.type == 0 and pkt.subtype == 8:
            try:
                ssid = pkt.info.decode('utf-8', errors='ignore')
            except Exception:
                ssid = "<unknown>"
            if not ssid:
                ssid = "<hidden>"
            bssid = normalize_mac(pkt.addr2)
            self.logger.info(f"Scapy scan detected - SSID: {ssid} - BSSID: {bssid}")
            # Optionally check if the BSSID is in your database (self.db_networks)
            if self.db_networks and bssid in self.db_networks:
                # Avoid sending duplicate alerts for the same BSSID.
                if bssid not in self.alerted_networks:
                    alert_data = {
                        "action": "NETWORK_FOUND",
                        "tool": self.name,
                        "ssid": ssid,
                        "bssid": bssid,
                        "timestamp": time.time()
                    }
                    self.alerted_networks[bssid] = True
                    self.send_network_found_alert(alert_data)

    def scan_networks_scapy(self, interface: str, dwell_time: int = 1) -> None:
        """
        Rotates through all channels (2.4 GHz and 5 GHz) and uses Scapy to sniff for beacon frames.
        dwell_time: number of seconds to stay on each channel.
        """
        from config.constants import ALL_CHANNELS
        for channel in ALL_CHANNELS:
            try:
                # Switch the interface to the target channel.
                subprocess.check_call(["iw", "dev", interface, "set", "channel", str(channel)],
                                    stderr=subprocess.DEVNULL)
                print(f"Switched {interface} to channel {channel}")
            except subprocess.CalledProcessError as e:
                print(f"Error switching {interface} to channel {channel}: {e}")
                continue

            # Sniff for beacon frames on this channel.
            sniff(iface=interface, prn=self.scapy_packet_handler, timeout=dwell_time, store=0)

    def start_background_scan_rotating(self):
        """
        Starts a background thread that continuously rotates through channels,
        scanning with Scapy on each channel for a short period.
        Before starting, it checks if the selected interface is in monitor mode,
        switching it if necessary.
        """
        from tools.helpers.tool_utils import switch_interface_to_monitor, get_interface_mode
        # Check if interface is already in monitor mode (using your helper)
        current_mode = get_interface_mode(self.selected_interface, self.logger)
        if current_mode != "monitor":
            self.logger.info("Interface %s is in %s mode; switching to monitor mode.", self.selected_interface,
                             current_mode)
            if not switch_interface_to_monitor(self.selected_interface, self.logger):
                self.logger.error("Failed to switch interface %s to monitor mode. Aborting background scan.",
                                  self.selected_interface)
                return

        self.scanner_running = True

        def background_scan():
            while self.scanner_running:
                self.scan_networks_scapy(self.selected_interface, dwell_time=1)
                # Optionally, add a delay between full rotations
                time.sleep(1)

        threading.Thread(target=background_scan, daemon=True).start()
        self.logger.info("Scapy-based rotating background scanning started.")

    def stop_background_scan_scapy(self):
        """
        Stops the Scapy-based background scanning.
        """
        self.scanner_running = False
        self.logger.info("Scapy-based background scanning stopped.")

    def send_network_found_alert(self, alert_data):
        """
        Sends a network found alert via IPC.
        """
        self.logger.debug("Sending network found alert via IPC: %s", alert_data)
        self.send_alert_payload("NETWORK_FOUND", alert_data)
        response = self.client.send(alert_data)
        self.logger.debug("IPC response for network alert: %s", response)

