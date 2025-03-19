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
        Connect to the network using wpa_supplicant.

        Steps:
         1. Generate a temporary wpa_supplicant configuration using wpa_passphrase.
         2. Write the configuration to a temporary file.
         3. Launch wpa_supplicant in the background on the selected interface.
         4. Wait until the interface is fully associated.
         5. Run a DHCP client (dhclient) to obtain an IP address.
         6. Clean up the temporary config file.
        """
        if not self.selected_interface or not self.selected_network:
            self.logger.error("Interface or network not specified!")
            return

        # generate wpa_supplicant configuration
        config_text = self.build_wpa_config()
        if config_text is None:
            self.logger.error("Failed to generate wpa_supplicant configuration.")
            return

        # write the config to a temporary file
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmpfile:
                tmpfile.write(config_text)
                tmpfile_path = tmpfile.name
            self.logger.debug(f"Temporary wpa_supplicant config written to {tmpfile_path}")
        except Exception as e:
            self.logger.error(f"Error writing temporary config file: {e}")
            return

        # launch wpa_supplicant in the background
        ws_cmd = ["wpa_supplicant", "-B", "-i", self.selected_interface, "-c", tmpfile_path]
        try:
            subprocess.check_call(ws_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"wpa_supplicant launched on {self.selected_interface}")
        except Exception as e:
            self.logger.error(f"Error launching wpa_supplicant: {e}")
            os.unlink(tmpfile_path)
            return

        # wait until the interface is associated
        if not self.wait_for_association(self.selected_interface, timeout=30):
            self.logger.error("Association did not complete in time; aborting dhclient run.")
            os.unlink(tmpfile_path)
            return

        # obtain an IP address using dhclient
        try:
            subprocess.check_call(["dhclient", self.selected_interface],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info("dhclient ran successfully; IP address obtained.")
        except Exception as e:
            self.logger.error(f"Error running dhclient: {e}")
            os.unlink(tmpfile_path)
            return

        # clean up temporary config file
        try:
            os.unlink(tmpfile_path)
            self.logger.debug("Temporary wpa_supplicant config file removed.")
        except Exception as e:
            self.logger.error(f"Error removing temporary config file: {e}")

        self.logger.info("Connected to network using wpa_supplicant.")

    def disconnect(self) -> None:
        """
        Disconnects the network on the selected interface by:
          1. Releasing the DHCP lease.
          2. Killing any wpa_supplicant process running on that interface.
        """
        if not self.selected_interface:
            self.logger.error("No interface selected for disconnecting!")
            return

        iface = self.selected_interface

        # release dhcp lease
        try:
            subprocess.check_call(
                ["dhclient", "-r", iface],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.logger.info(f"Released DHCP lease on {iface}.")
        except Exception as e:
            self.logger.error(f"Error releasing DHCP lease on {iface}: {e}")

        # kill wpa_supplicant for interface
        try:
            pkill_cmd = f"pkill -f 'wpa_supplicant.*-i {iface}'"
            subprocess.check_call(pkill_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"Killed wpa_supplicant on {iface}.")
        except Exception as e:
            self.logger.error(f"Error killing wpa_supplicant on {iface}: {e}")

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

    ##########################
    ##### HELPER METHODS #####
    ##########################
    def wait_for_association(self, interface: str, timeout: int = 30) -> bool:
        """
        Polls the wireless interface until it is fully associated with an access point.
        Returns True if association is confirmed within the timeout, else False.
        """
        start_time = time.time()
        self.logger.debug(f"Waiting for association on interface {interface} (timeout {timeout}s)...")
        while time.time() - start_time < timeout:
            try:
                output = subprocess.check_output(["iw", "dev", interface, "link"], text=True)
                self.logger.debug(f"Association check output: {output.strip()}")
                if "Connected to" in output:
                    self.logger.debug(f"Interface {interface} is now associated.")
                    return True
            except Exception as e:
                self.logger.debug(f"Error checking association on {interface}: {e}")
            time.sleep(1)
        self.logger.debug(f"Timeout reached: Interface {interface} is not associated after {timeout} seconds.")
        return False
