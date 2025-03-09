import tempfile
import subprocess
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from tools.tools import Tool
from utils.tool_registry import register_tool


@register_tool("netconnect")
class NetConnectTool(Tool):
    def __init__(self, base_dir: Path, config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, settings: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="netconnect",
            description="Tool for connecting to a network using wpa_supplicant",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=settings
        )
        self.logger = logging.getLogger(self.name.upper())
        # These are set via the submenu
        self.selected_interface = None  # e.g., "wlan0"
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
            config = subprocess.check_output(cmd, text=True)
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

        # Generate wpa_supplicant configuration
        config_text = self.build_wpa_config()
        if config_text is None:
            self.logger.error("Failed to generate wpa_supplicant configuration.")
            return

        # Write the config to a temporary file
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmpfile:
                tmpfile.write(config_text)
                tmpfile_path = tmpfile.name
            self.logger.debug(f"Temporary wpa_supplicant config written to {tmpfile_path}")
        except Exception as e:
            self.logger.error(f"Error writing temporary config file: {e}")
            return

        # Launch wpa_supplicant in the background
        ws_cmd = ["wpa_supplicant", "-B", "-i", self.selected_interface, "-c", tmpfile_path]
        try:
            subprocess.check_call(ws_cmd)
            self.logger.info(f"wpa_supplicant launched on {self.selected_interface}")
        except Exception as e:
            self.logger.error(f"Error launching wpa_supplicant: {e}")
            os.unlink(tmpfile_path)
            return

        # Obtain an IP address using dhclient
        try:
            subprocess.check_call(["dhclient", self.selected_interface])
            self.logger.info("dhclient ran successfully; IP address obtained.")
        except Exception as e:
            self.logger.error(f"Error running dhclient: {e}")
            # Optionally, kill wpa_supplicant here if needed.
            os.unlink(tmpfile_path)
            return

        # Clean up the temporary config file
        try:
            os.unlink(tmpfile_path)
            self.logger.debug("Temporary wpa_supplicant config file removed.")
        except Exception as e:
            self.logger.error(f"Error removing temporary config file: {e}")

        self.logger.info("Connected to network using wpa_supplicant.")
