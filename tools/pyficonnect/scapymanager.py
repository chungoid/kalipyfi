import threading
import subprocess
import time
import logging
from scapy.layers.dot11 import Dot11, Dot11ProbeReq, Dot11Elt, RadioTap
from scapy.all import sniff
from scapy.sendrecv import sendp

# locals
from common.models import AlertData
from config.constants import ALL_CHANNELS, BASE_DIR

PRIORITY_CHANNELS = [1, 6, 11, 36, 40, 44, 48]
OTHER_CHANNELS = [ch for ch in ALL_CHANNELS if ch not in PRIORITY_CHANNELS]
CHANNEL_SEQUENCE = PRIORITY_CHANNELS + OTHER_CHANNELS

class ScapyManager:
    _instance = None

    @staticmethod
    def get_instance():
        if ScapyManager._instance is None:
            ScapyManager._instance = ScapyManager()
        return ScapyManager._instance

    def __init__(self):
        self.logger = logging.getLogger("ScapyManager")
        logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
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
                current_time = time.time()
                alert_delay = 120  # delay in seconds (2 minutes)
                last_alert_time = self.alerted_networks.get(bssid)
                if not last_alert_time or (current_time - last_alert_time) > alert_delay:
                    self.logger.info("Detected network - SSID: %s, BSSID: %s", ssid, bssid)
                    alert = AlertData(
                        tool="pyficonnect",
                        data={
                            "action": "NETWORK_FOUND",
                            "ssid": ssid,
                            "bssid": bssid,
                            "msg": f"Detected network {ssid} on {bssid}"
                        }
                    )
                    self.alerted_networks[bssid] = current_time
                    self.publish_alert(alert)

    def publish_alert(self, alert_data):
        """
        Calls all registered alert callbacks with the given alert data.
        """
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error("Error in alert callback: %s", e)

    def scan_networks_scapy(self, interface: str) -> None:
        """
        Rotates through the prioritized channel sequence. For channels that are in the priority
        list (1,6,11,36,40,44,48), it listens longer (0.5 seconds) to capture more beacons.
        For all other channels, it uses a shorter dwell time (0.2 seconds).
        """
        for channel in CHANNEL_SEQUENCE:
            try:
                subprocess.check_call(
                    ["iw", "dev", interface, "set", "channel", str(channel)],
                    stderr=subprocess.DEVNULL
                )
                #self.logger.debug("Switched %s to channel %s", interface, channel)
            except subprocess.CalledProcessError as e:
                self.logger.error("Error switching %s to channel %s: %s", interface, channel, e)
                continue

            # Set dwell time based on whether the channel is prioritized.
            dwell_time = 0.5 if channel in PRIORITY_CHANNELS else 0.2
            #self.logger.debug("Listening on channel %s for %s seconds", channel, dwell_time)
            try:
                sniff(iface=interface, prn=self.scapy_packet_handler, timeout=dwell_time, store=0)
                #self.logger.debug("Finished listening on channel %s", channel)
            except Exception as e:
                self.logger.error("Error during sniffing on channel %s: %s", channel, e)
                time.sleep(0.1)

    def start_scanning(self, interface: str):
        """
        Starts a background thread that rotates through the prioritized channel sequence on the specified interface.
        It first loads the DB networks so alerts can be generated, then continuously cycles through channels.
        """
        self.selected_interface = interface
        self.load_db_networks()
        self.scanner_running = True

        def background_scan():
            while self.scanner_running:
                #self.logger.debug("Starting a new channel rotation cycle")
                self.scan_networks_scapy(interface)
                #self.logger.debug("Completed channel rotation cycle; sleeping briefly")
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