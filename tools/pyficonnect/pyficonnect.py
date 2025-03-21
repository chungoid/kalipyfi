import asyncio
import subprocess
import logging
import threading
import time
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any
from pyroute2 import IW, IPRoute

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

    async def monitor_netlink_events(self):
        """
        Monitors netlink events using pyroute2's IPRoute and triggers a scan when events occur.
        """
        ipr = IPRoute()
        try:
            ipr.bind()
            self.logger.info("Netlink socket bound; starting event monitoring loop.")
            while self.scanner_running:
                self.logger.debug("Awaiting netlink events...")
                events = await asyncio.to_thread(ipr.get)
                if events:
                    for event in events:
                        self.logger.debug(f"Netlink event: {event}")
                else:
                    self.logger.debug("No netlink events received in this iteration.")

                networks = await asyncio.to_thread(self.scan_networks_pyroute2, self.selected_interface)
                self.logger.debug(f"Scan returned networks: {networks}")
                from tools.helpers.tool_utils import normalize_mac
                for net in networks:
                    cli_bssid = net.get("bssid")
                    norm_cli_bssid = normalize_mac(cli_bssid)
                    self.logger.debug(f"Normalized BSSID: {norm_cli_bssid}")
                    if norm_cli_bssid in self.db_networks:
                        current_time = time.time()
                        alert_data = {
                            "action": "NETWORK_FOUND",
                            "tool": self.name,
                            "ssid": self.db_networks[norm_cli_bssid]["ssid"],
                            "bssid": norm_cli_bssid,
                            "key": self.db_networks[norm_cli_bssid].get("key"),
                            "timestamp": current_time,
                        }
                        self.logger.info(f"Alert generated: {alert_data}")
                        self.send_network_found_alert(alert_data)
                await asyncio.sleep(0.1)
        finally:
            ipr.close()
            self.logger.info("Netlink event monitoring loop terminated.")

    def scan_networks_pyroute2(self, interface):
        """
        Uses pyroute2's IW module to scan for networks on the specified interface.
        Returns a list of dictionaries like:
          [{"ssid": "MyHomeWiFi", "bssid": "AA:BB:CC:DD:EE:FF"}, ...]
        """
        iw = IW()
        try:
            results = iw.scan(interface)
            self.logger.debug(f"Raw scan results: {results}")
            networks = []
            for ap in results:
                networks.append({
                    "ssid": ap.get("ssid", "Unknown"),
                    "bssid": ap.get("bssid")
                })
            self.logger.debug(f"pyroute2 scan found networks: {networks}")
            return networks
        except Exception as e:
            self.logger.error("Error scanning using pyroute2: %s", e)
            return []
        finally:
            try:
                iw.close()
            except Exception:
                pass

    @staticmethod
    def ensure_event_loop():
        try:
            loop = asyncio.get_running_loop()
            return loop
        except RuntimeError:
            new_loop = asyncio.new_event_loop()
            threading.Thread(target=new_loop.run_forever, daemon=True).start()
            asyncio.set_event_loop(new_loop)
            return new_loop

    def start_background_scan_async(self):
        self.logger.info(f"Starting background scan on interface: {self.selected_interface}")
        self.logger.info(f"Loaded DB networks: {list(self.db_networks.keys())}")
        self.scanner_running = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            threading.Thread(target=loop.run_forever, daemon=True).start()
        loop.create_task(self.monitor_netlink_events())
        self.logger.info("Background netlink event monitoring started.")

    def stop_background_scan_async(self):
        """
        Stops the background scanning by setting the scanner_running flag to False.
        """
        self.scanner_running = False
        self.logger.info("Background netlink event monitoring stopped.")

    def send_network_found_alert(self, alert_data):
        self.logger.debug(f"Sending alert via IPC: {alert_data}")
        self.send_alert_payload("NETWORK_FOUND", alert_data)
        response = self.client.send(alert_data)
        self.logger.debug(f"IPC response for alert: {response}")


