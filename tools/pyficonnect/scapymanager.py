import threading
import subprocess
import time
import logging
from scapy.layers.dot11 import Dot11
from scapy.all import sniff
from config.constants import ALL_CHANNELS, BASE_DIR


class ScapyManager:
    _instance = None

    @staticmethod
    def get_instance():
        if ScapyManager._instance is None:
            ScapyManager._instance = ScapyManager()
        return ScapyManager._instance

    def __init__(self):
        self.logger = logging.getLogger("ScapyManager")
        self.scanner_running = False
        self.selected_interface = None
        self.db_networks = {}         # Dictionary of networks loaded from the database
        self.alerted_networks = {}      # Keeps track of alerts already sent
        self.alert_callbacks = []       # Other tools can register callback functions

    def load_db_networks(self):
        """
        Loads network data from your database.
        Replace the placeholder code below with your actual DB loading logic.
        """
        from tools.pyficonnect._parser import get_pyficonnect_networks_from_db, format_pyficonnect_networks
        rows = get_pyficonnect_networks_from_db(BASE_DIR)
        self.db_networks = format_pyficonnect_networks(rows)
        self.logger.debug(f"Loaded DB networks: {list(self.db_networks.keys())}")

    def scapy_packet_handler(self, pkt):
        """
        Processes each packet captured by Scapy.
        If the packet is a beacon frame, it checks if the BSSID exists in the loaded DB networks.
        If so, and if this BSSID hasn't already generated an alert, it publishes an alert.
        """
        from tools.helpers.tool_utils import normalize_mac
        if pkt.haslayer(Dot11) and pkt.type == 0 and pkt.subtype == 8:
            try:
                ssid = pkt.info.decode('utf-8', errors='ignore')
            except Exception:
                ssid = "<unknown>"
            if not ssid:
                ssid = "<hidden>"
            bssid = normalize_mac(pkt.addr2)
            if self.db_networks and bssid in self.db_networks:
                if bssid not in self.alerted_networks:
                    self.logger.info("Detected network - SSID: %s, BSSID: %s", ssid, bssid)
                    alert_data = {
                        "action": "NETWORK_FOUND",
                        "tool": "pyficonnect",
                        "ssid": ssid,
                        "bssid": bssid,
                        "timestamp": time.time()
                    }
                    self.alerted_networks[bssid] = True
                    self.publish_alert(alert_data)

    def publish_alert(self, alert_data):
        """
        Calls all registered alert callbacks with the given alert data.
        """
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error("Error in alert callback: %s", e)

    def scan_networks_scapy(self, interface: str, dwell_time: float = 0.2) -> None:
        """
        Iterates through all channels (2.4 GHz and 5 GHz) and uses Scapy to sniff for beacon frames.
        dwell_time: The number of seconds to sniff on each channel.
        """
        for channel in ALL_CHANNELS:
            try:
                subprocess.check_call(
                    ["iw", "dev", interface, "set", "channel", str(channel)],
                    stderr=subprocess.DEVNULL
                )
                self.logger.info("Switched %s to channel %s", interface, channel)
            except subprocess.CalledProcessError as e:
                self.logger.error("Error switching %s to channel %s: %s", interface, channel, e)
                continue

            try:
                sniff(iface=interface, prn=self.scapy_packet_handler, timeout=dwell_time, store=0)
            except Exception as e:
                self.logger.error("Error during sniffing on channel %s: %s", channel, e)
                time.sleep(0.1)

    def start_scanning(self, interface: str, dwell_time: float = 0.2):
        """
        Starts a background thread that rotates through all channels on the specified interface.
        It first loads the DB networks so alerts can be generated, then starts scanning.
        """
        self.selected_interface = interface
        self.load_db_networks()
        self.scanner_running = True

        def background_scan():
            while self.scanner_running:
                self.scan_networks_scapy(interface, dwell_time=dwell_time)
                time.sleep(0.2)

        threading.Thread(target=background_scan, daemon=True).start()
        self.logger.info("Global Scapy-based background scanning started on %s", interface)

    def stop_scanning(self):
        """
        Stops the background scanning process.
        """
        self.scanner_running = False
        self.logger.info("Global Scapy-based background scanning stopped.")

    def register_alert_callback(self, callback):
        """
        Registers a callback function that will be called when a network alert is generated.
        """
        if callback not in self.alert_callbacks:
            self.alert_callbacks.append(callback)
            self.logger.info("Alert callback registered.")

    def unregister_alert_callback(self, callback):
        """
        Unregisters a previously registered alert callback.
        """
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
            self.logger.info("Alert callback unregistered.")
