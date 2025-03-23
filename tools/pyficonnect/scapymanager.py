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

    def active_probe_request(self, interface):
        # Replace 'AA:BB:CC:DD:EE:FF' with your interface's MAC address (e.g., obtained via get_if_hwaddr)
        source_mac = "AA:BB:CC:DD:EE:FF"
        self.logger.debug("Sending probe request on interface %s with source MAC %s", interface, source_mac)
        # Create a probe request frame: destination is broadcast and source is your interface.
        dot11 = Dot11(type=0, subtype=4, addr1="ff:ff:ff:ff:ff:ff",
                      addr2=source_mac, addr3="ff:ff:ff:ff:ff:ff")
        # Dot11ProbeReq frame with an empty SSID (asking for all networks)
        probe_req = Dot11ProbeReq()
        ssid_elt = Dot11Elt(ID="SSID", info=b"")
        # Optionally, add supported rates (example rates)
        rates_elt = Dot11Elt(ID="Rates", info=b"\x82\x84\x8b\x96")
        pkt = RadioTap() / dot11 / probe_req / ssid_elt / rates_elt
        sendp(pkt, iface=interface, verbose=False)
        self.logger.debug("Probe request sent on %s", interface)

    def scapy_packet_handler(self, pkt):
        from tools.helpers.tool_utils import normalize_mac
        # Listen only for probe responses (subtype 5)
        if pkt.haslayer(Dot11) and pkt.type == 0 and pkt.subtype == 5:
            try:
                ssid = pkt.info.decode('utf-8', errors='ignore')
            except Exception:
                ssid = "<unknown>"
            if not ssid:
                ssid = "<hidden>"
            bssid = normalize_mac(pkt.addr2)
            self.logger.debug("Probe response received: SSID=%s, BSSID=%s", ssid, bssid)
            if self.db_networks and bssid in self.db_networks:
                current_time = time.time()
                alert_delay = 120  # 2 minutes delay
                last_alert_time = self.alerted_networks.get(bssid)
                if not last_alert_time or (current_time - last_alert_time) > alert_delay:
                    self.logger.info("Detected network via probe response - SSID: %s, BSSID: %s", ssid, bssid)
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
                else:
                    self.logger.debug("Skipping alert for %s; last alert was %ss ago", bssid,
                                      current_time - last_alert_time)

    def scan_networks_scapy(self, interface: str, dwell_time: float = 0.2) -> None:
        """
        Rotates through all channels, sends an active probe request on each,
        and listens for probe responses (subtype 5) only.
        """
        for channel in ALL_CHANNELS:
            self.logger.debug("Switching %s to channel %s", interface, channel)
            try:
                subprocess.check_call(
                    ["iw", "dev", interface, "set", "channel", str(channel)],
                    stderr=subprocess.DEVNULL
                )
                self.logger.debug("Successfully switched %s to channel %s", interface, channel)
            except subprocess.CalledProcessError as e:
                self.logger.error("Error switching %s to channel %s: %s", interface, channel, e)
                continue

            # Send a probe request on this channel
            self.logger.debug("Sending active probe request on channel %s", channel)
            self.active_probe_request(interface)

            # Listen for probe responses on this channel
            self.logger.debug("Sniffing on channel %s for %s seconds", channel, dwell_time)
            try:
                sniff(iface=interface, prn=self.scapy_packet_handler, timeout=dwell_time, store=0)
                self.logger.debug("Finished sniffing on channel %s", channel)
            except Exception as e:
                self.logger.error("Error during sniffing on channel %s: %s", channel, e)
                time.sleep(0.1)

    def start_scanning(self, interface: str, dwell_time: float = 0.2):
        """
        Starts a background thread that rotates through all channels on the specified interface.
        It first loads the DB networks so alerts can be generated, then starts scanning.
        """
        self.selected_interface = interface
        self.logger.debug("Loading DB networks before starting scan")
        self.load_db_networks()
        self.scanner_running = True

        def background_scan():
            while self.scanner_running:
                self.logger.debug("Starting channel rotation cycle")
                self.scan_networks_scapy(interface, dwell_time=dwell_time)
                self.logger.debug("Completed one channel rotation cycle, sleeping briefly")
                time.sleep(0.2)

        threading.Thread(target=background_scan, daemon=True).start()
        self.logger.info("Global Scapy-based background scanning started on %s", interface)

    def stop_scanning(self):
        """
        Stops the background scanning process.
        """
        self.scanner_running = False
        self.logger.info("Global Scapy-based background scanning stopped.")

    def publish_alert(self, alert_data):
        """
        Calls all registered alert callbacks with the given alert data.
        """
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error("Error in alert callback: %s", e)

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
