import asyncio
import subprocess
import logging
import threading
import time
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any
from pyroute2 import IPRoute

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

    def scan_networks_pyroute2(self, interface):
        """
        Uses pyroute2's IW module to trigger a fresh scan on the specified interface.
        Returns a list of dictionaries like: [{"ssid": <ssid>, "bssid": <bssid>}, ...]
        """
        from pyroute2 import IPRoute, IW

        # Confirm the interface exists and retrieve ifindex
        ipr = IPRoute()
        try:
            indices = ipr.link_lookup(ifname=interface)
            if not indices:
                self.logger.error("No interface found with name %s", interface)
                return []
            ifindex = indices[0]
            self.logger.debug("Interface %s has ifindex: %s", interface, ifindex)
        except Exception as e:
            self.logger.error("Error looking up interface %s: %s", interface, e)
            return []
        finally:
            ipr.close()

        # Create IW instance and perform scan
        iw = IW()
        networks = []
        try:
            self.logger.info("Initiating scan on interface %s (ifindex %s).", interface, ifindex)
            results = iw.scan(ifindex, flush_cache=True)
            self.logger.debug("Raw scan results: %s", results)
            if not results:
                self.logger.error("No results returned from iw.scan() for interface %s", interface)
            for idx, ap in enumerate(results, start=1):
                # Parse attributes into a dictionary
                ap_attrs = {}
                for attr in ap.get("attrs", []):
                    key, value = attr[0], attr[1]
                    ap_attrs[key] = value
                    self.logger.debug("AP %d: Parsed attribute: %r = %r", idx, key, value)
                bssid = ap_attrs.get("NL80211_BSS_BSSID")
                ie = ap_attrs.get("NL80211_BSS_INFORMATION_ELEMENTS", {})
                raw_ssid = ie.get("SSID") if isinstance(ie, dict) else None

                if raw_ssid is None:
                    ssid = "Unknown"
                elif isinstance(raw_ssid, bytes):
                    try:
                        ssid = raw_ssid.decode("utf-8", errors="replace")
                    except Exception as e:
                        self.logger.error("AP %d: Error decoding SSID: %s", idx, e)
                        ssid = "Unknown"
                elif isinstance(raw_ssid, str):
                    ssid = raw_ssid
                else:
                    ssid = "Unknown"
                if not ssid:
                    ssid = "Hidden"

                network = {"ssid": ssid, "bssid": bssid}
                networks.append(network)
                self.logger.debug("AP %d: Scanned network: %s", idx, network)
                self.logger.info("AP %d: Found network - SSID: %s, BSSID: %s", idx, ssid, bssid)
            if not networks:
                self.logger.error("Fallback scan on interface %s returned no networks.", interface)
            else:
                self.logger.info("Fallback scan complete. Found %d networks on %s.", len(networks), interface)
            return networks
        except Exception as e:
            self.logger.error("Error during fallback scan on interface %s: %s", interface, e)
            return []
        finally:
            try:
                iw.close()
            except Exception as ex:
                self.logger.debug("Error closing IW instance: %s", ex)

    async def monitor_netlink_events(self):
        """
        Opens a netlink socket via IPRoute and waits for events.
        If no events are received within 1 second, logs a timeout.
        Triggers a fallback scan every 10 seconds.
        """
        self.logger.debug("Monitoring netlink events")
        from pyroute2 import IPRoute
        ipr = IPRoute()
        try:
            ipr.bind()
            self.logger.info("Netlink socket bound; starting event monitoring loop.")
            last_scan = time.time()
            while self.scanner_running:
                self.logger.debug("Starting new netlink monitoring iteration.")
                try:
                    self.logger.debug("Waiting for netlink events (1-second timeout)...")
                    events = await asyncio.wait_for(asyncio.to_thread(ipr.get), timeout=1)
                    self.logger.debug("Netlink events received: %s", events)
                except asyncio.TimeoutError:
                    self.logger.debug("Timeout: no netlink events received this iteration.")
                    events = None
                except Exception as e:
                    self.logger.error("Exception in netlink event retrieval: %s", e)
                    events = None

                if events:
                    self.logger.debug("Received %d netlink event(s).", len(events))
                    for idx, event in enumerate(events, start=1):
                        self.logger.debug("Event %d: %s", idx, event)
                else:
                    self.logger.debug("No netlink events received.")

                elapsed = time.time() - last_scan
                self.logger.debug("Elapsed time since last fallback scan: %.2f seconds", elapsed)
                if elapsed >= 10:
                    last_scan = time.time()
                    self.logger.info("Fallback periodic scan triggered.")
                    if not self.selected_interface:
                        self.logger.error("No interface selected for fallback scan.")
                    else:
                        self.logger.debug("Executing fallback scan on interface: %s", self.selected_interface)
                        fallback_networks = await asyncio.to_thread(self.scan_networks_pyroute2, self.selected_interface)
                        self.logger.info("Fallback scan detected %d networks.", len(fallback_networks))
                        # Here you can add additional processing (e.g., compare with DB networks)
                await asyncio.sleep(0.1)
        finally:
            ipr.close()
            self.logger.info("Netlink event monitoring loop terminated.")

    def start_background_scan_async(self):
        """
        Starts the asynchronous netlink monitoring loop in a separate thread.
        """
        self.scanner_running = True
        thread = threading.Thread(
            target=self.background_monitor,
            args=(self.monitor_netlink_events(),),
            daemon=True
        )
        thread.start()
        self.logger.info("Background netlink event monitoring started.")

    @staticmethod
    def background_monitor(coro):
        """
        Runs an asynchronous coroutine in a dedicated thread.
        """
        asyncio.run(coro)

    def stop_background_scan_async(self):
        """
        Stops the background netlink event monitoring loop.
        """
        self.scanner_running = False
        self.logger.info("Background netlink event monitoring stopped.")

    def send_network_found_alert(self, alert_data):
        """
        Sends a network found alert via IPC.
        """
        self.logger.debug("Sending network found alert via IPC: %s", alert_data)
        self.send_alert_payload("NETWORK_FOUND", alert_data)
        response = self.client.send(alert_data)
        self.logger.debug("IPC response for network alert: %s", response)

