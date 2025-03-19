import tempfile
import subprocess
import os
import logging
import threading
import time
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any

from config.constants import BASE_DIR
from database.db_manager import get_db_connection
from tools.pyficonnect.db import init_pyfyconnect_schema
from tools.pyficonnect.submenu import PyfyConnectSubmenu
from tools.tools import Tool
from utils.ipc_client import IPCClient
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
        # These are set via the submenu
        self.selected_interface = None  # "wlan0, wlan1, etc. from config.yaml"
        self.selected_network = None  # SSID of the network
        self.network_password = None  # Password (if needed)

        # pyficonnect-specific database schema (tools/pyficonnect/db.py)
        conn = get_db_connection(BASE_DIR)
        init_pyfyconnect_schema(conn)
        conn.close()

        # auto-scanning for db match
        self.db_networks = None
        self.scanner_running = False

    def submenu(self, stdscr) -> None:
        """
        Launches the nmap submenu (interactive UI) using curses.
        """
        self.submenu_instance(stdscr)

    def build_wpa_config(self) -> Optional[str]:
        """
        Uses wpa_passphrase to generate a wpa_supplicant configuration for the selected network.
        Returns the configuration as a string, or None if an error occurs.
        """
        if not self.selected_network or self.network_password is None:
            self.logger.error("Missing SSID or password for generating wpa_supplicant config.")
            return None
        cmd = ["wpa_passphrase", self.selected_network, self.network_password]
        try:
            # capture output
            config = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            self.logger.debug("Generated wpa_supplicant config using wpa_passphrase.")
            return config
        except Exception as e:
            self.logger.error(f"Error generating wpa_supplicant config: {e}")
            return None

    def run(self, profile=None) -> None:
        """
        Connect to the network using nmcli by creating a connection profile in one step.
        This method:
          1. Creates the profile with the SSID, password, and other settings, including:
             - wifi-sec.key-mgmt set to wpa-psk
             - wifi-sec.psk set to the provided password
             - 802-11-wireless-security.psk-flags set to 0 (to store the password permanently)
             - autoconnect disabled
          2. Activates the connection.
        """
        if not self.selected_interface or not self.selected_network:
            self.logger.error("Interface or network not specified!")
            return

        con_name = self.selected_network
        try:
            # create the connection profile in one command
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
            # activate the connection
            up_cmd = ["nmcli", "connection", "up", con_name]
            self.logger.debug("Running nmcli connection up command: " + " ".join(up_cmd))
            subprocess.check_call(up_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(
                f"Connected to {self.selected_network} on {self.selected_interface} using profile '{con_name}'.")
        except Exception as e:
            self.logger.error(f"Error activating connection: {e}")
            return

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
        Loads all rows from the hcxtool table into a dictionary.
        The resulting dictionary maps each SSID to its bssid and key.
        Example:
           {
             "MyHomeWiFi": {"bssid": "AA:BB:CC:DD:EE:FF", "key": "pass123"},
             "OfficeWiFi": {"bssid": "11:22:33:44:55:66", "key": "secret"}
           }
        """
        from tools.helpers.sql_utils import get_founds_bssid_ssid_and_key
        founds = get_founds_bssid_ssid_and_key(self.base_dir)
        self.db_networks = {}
        for bssid, ssid, key in founds:
            self.logger.debug(f"database networks: {bssid}, {ssid}, {key}")
            self.db_networks[ssid] = {"bssid": bssid, "key": key}

    def start_background_scan(self):
        self.scanner_running = True
        threading.Thread(target=self.background_scan_loop, daemon=True).start()

    def background_scan_loop(self):
        while self.scanner_running:
            available_networks = self.scan_networks_cli(self.selected_interface)
            # compare available to db
            for net in available_networks:
                ssid = net.get("ssid")
                if ssid in self.db_networks:
                    alert_data = {
                        "action": "NETWORK_FOUND",
                        "tool": self.name,
                        "ssid": ssid,
                        "bssid": net.get("bssid"),
                        "key": self.db_networks[ssid].get("key")
                    }
                    self.logger.debug(f"background scan alert_data: {alert_data}")
                    self.send_network_found_alert(alert_data)
            time.sleep(10)  # check every 10 seconds

    def scan_networks_cli(self, interface):
        """
        Scans for available networks using nmcli
        Returns a list of dictionaries like:
          [{"ssid": "MyHomeWiFi", "bssid": "AA:BB:CC:DD:EE:FF"}, ...]
        """
        try:
            output = subprocess.check_output(
                ["nmcli", "-f", "SSID,BSSID", "device", "wifi", "list", "ifname", interface],
                text=True
            )
            from tools.helpers.tool_utils import parse_nmcli_ssid_bssid
            self.logger.debug(f"background scan result: {output}")
            return parse_nmcli_ssid_bssid(output)
        except Exception as e:
            self.logger.error("Background scan error: %s", e)
            return []

    def send_network_found_alert(self, alert_data):
        """
        Uses the IPC client to send a 'NETWORK_FOUND' message.
        """
        client = IPCClient()  # uses published sock file.. instancing is fine
        response = client.send(alert_data)
        self.logger.debug("Network found alert sent: %s, response: %s", alert_data, response)
