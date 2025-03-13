import tempfile
import subprocess
import os
import logging
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any

from tools.pyfyconnect.submenu import PyfyConnectSubmenu
from tools.tools import Tool
from utils.tool_registry import register_tool


@register_tool("pyfyconnect")
class PyfyConnectTool(Tool, ABC):
    def __init__(self, base_dir: Path, config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, settings: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="pyfyconnect",
            description="Tool for connecting to a network using wpa_supplicant",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=settings
        )
        self.logger = logging.getLogger(self.name.upper())
        self.submenu = PyfyConnectSubmenu(self)
        # These are set via the submenu
        self.selected_interface = None  # "wlan0, wlan1, etc. from config.yaml"
        self.selected_network = None  # SSID of the network
        self.network_password = None  # Password (if needed)

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
         4. Run a DHCP client (dhclient) to obtain an IP address.
         5. Clean up the temporary config file.
        """
        if not self.selected_interface or not self.selected_network:
            self.logger.error("Interface or network not specified!")
            return

        # generate wpa_supplicant configuration
        config_text = self.build_wpa_config()
        if config_text is None:
            self.logger.error("Failed to generate wpa_supplicant configuration.")
            return

        # write the config to temp file
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

        # obtain an IP address using dhclient
        try:
            subprocess.check_call(["dhclient", self.selected_interface],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info("dhclient ran successfully; IP address obtained.")
        except Exception as e:
            self.logger.error(f"Error running dhclient: {e}")
            os.unlink(tmpfile_path)
            return

        # clean up temp file
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


