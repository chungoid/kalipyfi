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
from tools.pyficonnect.scapymanager import ScapyManager
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
        self.scapy_manager = ScapyManager.get_instance()
        self.scapy_manager.register_alert_callback(self.handle_alert)

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
