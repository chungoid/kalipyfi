import logging
import time
from pathlib import Path
from typing import List, Optional, Any, Dict

# local
from tools.tools import Tool
from utils.tool_registry import register_tool
from tools.netconnect.submenu import NetConnectSubmenu


@register_tool("netconnect")
class NetConnectTool(Tool):
    def __init__(self, base_dir: Path, config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, settings: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="netconnect",
            description="Tool for connecting to a network using nmcli",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=settings
        )
        self.logger = logging.getLogger(self.name.upper())
        self.submenu = NetConnectSubmenu(self)
        # These are set via the submenu
        self.selected_interface = None  # e.g., "wlan0"
        self.selected_network = None  # SSID of the network
        self.network_password = None  # password if needed

    def build_command(self) -> List[str]:
        """
        Build the nmcli command to connect to a network.
        Basic command:
            nmcli device wifi connect <SSID> ifname <interface> [password <password>]
        """
        if not self.selected_interface or not self.selected_network:
            self.logger.error("Interface or network not specified!")
            return []

        # Build the base nmcli connection command.
        cmd = ["nmcli", "device", "wifi", "connect",
               self.selected_network, "ifname", self.selected_interface]

        # Append password if provided.
        if self.network_password:
            cmd.extend(["password", self.network_password])

        self.logger.debug("Built nmcli command: " + " ".join(cmd))
        return cmd

    def run(self, profile=None) -> None:
        """
        Builds the nmcli connection command, converts it to a dictionary,
        and sends it via IPC using the CONNECT_NETWORK action.
        """
        self.logger.info("Starting network connection procedure via nmcli.")

        cmd_list = self.build_command()
        if not cmd_list:
            self.logger.error("Unable to build nmcli command, aborting connection attempt.")
            return

        # Convert the command list to a structured dictionary.
        cmd_dict = self.cmd_to_dict(cmd_list)
        self.logger.debug(f"Command dictionary: {cmd_dict}")

        # Use a pane title based on the interface and network.
        pane_title = f"{self.selected_interface}_{self.selected_network}"

        # Build the IPC message with a custom action "CONNECT_NETWORK".
        ipc_message = {
            "action": "CONNECT_NETWORK",
            "tool": self.name,
            "network": self.selected_network,
            "command": cmd_dict,
            "interface": self.selected_interface,
            "timestamp": time.time()
        }
        self.logger.debug("Sending IPC connection command: %s", ipc_message)

        # Send the IPC message.
        from utils.ipc_client import IPCClient
        client = IPCClient()
        response = client.send(ipc_message)

        if isinstance(response, dict) and response.get("status", "").startswith("CONNECT_NETWORK_OK"):
            self.logger.info("Network connect command sent successfully via IPC.")
        else:
            self.logger.error("Failed to send network connect command via IPC. Response: %s", response)
