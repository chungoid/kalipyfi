import os
import time
import shlex
import psutil
import logging
import subprocess
from pathlib import Path
from threading import Thread
from datetime import datetime
from abc import abstractmethod
from typing import Dict, Any, List, Optional

# local
from config.constants import BASE_DIR
from config.config_utils import load_yaml_config
from tools.helpers.autobpf import run_autobpf
from tools.helpers.tool_utils import get_network_from_interface
from utils.ipc_callback import get_shared_callback_socket
from utils.ipc_client import IPCClient


class Tool:
    def __init__(self, name: str, description: str, base_dir: Path,
                 config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None,
                 settings: Optional[Dict[str, Any]] = None,
                 ui_instance: Optional[Any] = None) -> None:

        self.name = name
        self.description = description
        self.base_dir = Path(base_dir).resolve()

        # Set UI instance (via registry)
        self.ui_instance = ui_instance

        if not logging.getLogger().handlers:
            self.logger = logging.getLogger(self.__class__.__name__)

        # Define essential directories based on base_dir
        self.config_dir = self.base_dir / "configs"
        self.results_dir = self.base_dir / "results"

        # Ensure required directories exist.
        self._setup_directories()

        #Setup logger
        self.logger = logging.getLogger(self.name.upper())

        # Determine the configuration file path using a helper function
        self.config_file = self._determine_config_path(config_file)

        # Load configuration
        self.config_data = load_yaml_config(self.config_file, self.logger)

        # Extract config sections
        self.interfaces = self.config_data.get("interfaces", {})
        self.presets = self.config_data.get("presets", {})
        self.defaults = self.config_data.get("defaults", {}) # currently unused, here for future flexibility
        self.selected_interface = None # set in submenu, this is your chosen scan interface
        self.selected_preset = None # set in submenu, this is your yaml built command
        self.preset_description = None # set in submenu, this is the presets description key
        self.extra_macs = None # set in submenu (future addon)

        # set socket path for callback listener
        self.callback_socket = get_shared_callback_socket()

        # Optional Overrides
        if interfaces:
            self.interfaces.update(interfaces)
        if settings:
            self.defaults.update(settings)

        # update config file with available interfaces
        self.sync_connected_wireless_interfaces()

        # debug instancing
        self.logger.info(f"Initialized tool: {self.name} with ui instance: {self.ui_instance} (id: {id(self.ui_instance)})")

    ##############################################
    ##### SUBMENU AND CONFIG/INITIALIZATION ######
    ##############################################
    @abstractmethod
    def submenu(self, stdscr) -> None:
        """
        Launches the tool-specific submenu using curses.
        Must be implemented by concrete tool classes.
        """
        pass

    def _determine_config_path(self, config_file: Optional[str]) -> Path:
        """
        Determines the full path to the configuration file.

        If a config_file string is provided and is relative:
          - If it starts with "tools", assume it is relative to BASE_DIR.
          - If it starts with "configs", assume it is relative to base_dir.
          - Otherwise, assume it is relative to self.config_dir.
        If no config_file is provided, defaults to self.config_dir / "config.yaml".

        :param config_file: Optional string representing the config file path.
        :return: A resolved Path object for the configuration file.
        """
        if config_file:
            config_path = Path(config_file)
            if not config_path.is_absolute():
                if config_path.parts and config_path.parts[0] == "tools":
                    config_path = BASE_DIR / config_path
                elif config_path.parts and config_path.parts[0] == "configs":
                    config_path = self.base_dir / config_path
                else:
                    config_path = self.config_dir / config_path
        else:
            config_path = self.config_dir / "config.yaml"
        return config_path.resolve()

    def _setup_directories(self) -> None:
        """Ensure required directories exist."""
        for d in [self.config_dir, self.results_dir]:
            d.mkdir(parents=True, exist_ok=True)

    #############################
    ##### CORE IPC HANDLING #####
    #############################
    def run_to_ipc(self, cmd_dict: dict):
        """
        Launch the scan command in a background pane via IPC.
        The IPC server will:
          - Get or create the background window for this tool.
          - Allocate or identify a pane.
          - Run the provided command.
        """

        original_cmd = f"{cmd_dict['executable']} {' '.join(cmd_dict['arguments'])}"
        unique_id = int(time.time())
        pid_file = f"/tmp/nmap_{unique_id}.pid"

        # group background job & waiting
        grouped_cmd = f'"( {original_cmd} & echo \\$! > {pid_file}; wait \\$! )"'

        wrapped_cmd = {
            "executable": "bash",
            "arguments": ["-c", grouped_cmd]
        }

        client = IPCClient()

        ipc_message = {
            "action": "SEND_SCAN",
            "tool": self.name,
            "command": wrapped_cmd,
            "interface": self.selected_interface,
            "preset_description": self.preset_description,
            "timestamp": time.time(),
            "callback_socket": self.callback_socket,
        }

        response = client.send(ipc_message)

        if isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            pane_id = response.get("pane_id")
            if pane_id:
                self.logger.debug("Scan command executed successfully in pane %s.", pane_id)
            else:
                self.logger.warning("Scan command succeeded but pane id is missing.")
        else:
            self.logger.error("Error executing scan command via IPC: %s", response)

        # monitor process via pid file
        def wait_and_notify():
            # let file get created
            time.sleep(1)
            try:
                with open(pid_file, "r") as f:
                    nmap_pid = int(f.read().strip())
                self.logger.debug(f"Read nmap PID: {nmap_pid} from {pid_file}.")
            except Exception as e:
                self.logger.error("Failed to read nmap PID from file: %s", e)
                return

            try:
                self.logger.debug(f"Monitoring nmap PID {nmap_pid} with psutil.")
                while True:
                    try:
                        proc = psutil.Process(nmap_pid)
                        if not proc.is_running():
                            break
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(1)
                self.logger.debug(f"nmap PID {nmap_pid} completed successfully.")
            except Exception as e:
                self.logger.error(f"Error monitoring nmap PID {nmap_pid}: {e}")

            # notify callback socket
            try:
                cb_socket = ipc_message.get("callback_socket")
                if cb_socket:
                    from utils.ipc import notify_scan_complete
                    notify_scan_complete(cb_socket, response.get("pane_id"), nmap_pid, self.name)
                    self.logger.debug(f"Sent SCAN_COMPLETE for nmap PID {nmap_pid} to socket {cb_socket}.")
                else:
                    self.logger.warning("Callback socket missing; no SCAN_COMPLETE sent.")
            except Exception as e:
                self.logger.error(f"Error during callback notification: {e}")

        Thread(target=wait_and_notify, daemon=True).start()

        return response

    def run(self):
        self.logger.info("No you run..")
        return

    ######################################
    ##### HELPER METHODS BY CATEGORY #####
    ######################################
### CONFIG ###
    def sync_connected_wireless_interfaces(self) -> None:
        """
        Checks the 'interfaces' section (e.g., under "wlan") in the configuration file.
        If no wireless interfaces defined in the config are currently connected,
        updates the configuration by auto-adding connected wireless interfaces.
        Uses get_connected_wireless_interfaces and update_yaml_value helpers.
        """
        from tools.helpers.tool_utils import get_connected_wireless_interfaces, update_yaml_value
        import yaml

        try:
            with self.config_file.open("r") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error(f"Error loading configuration from {self.config_file}: {e}")
            return

        # ensure 'interfaces' and 'wlan' exist as list in config file
        if "interfaces" not in config:
            config["interfaces"] = {}
        if "wlan" not in config["interfaces"] or not isinstance(config["interfaces"]["wlan"], list):
            config["interfaces"]["wlan"] = []

        # Get currently connected wireless interfaces.
        connected = get_connected_wireless_interfaces(self.logger)
        self.logger.debug(f"Connected wireless interfaces: {connected}")
        if not connected:
            self.logger.info("No wireless interfaces are currently connected.")
            return

        # build a set of existing interface names from config
        existing_names = {entry.get("name") for entry in config["interfaces"]["wlan"] if entry.get("name")}
        self.logger.debug(f"Existing wireless interface names in config: {existing_names}")

        # prepare new for each found
        new_entries = []
        for iface in connected:
            if iface not in existing_names:
                new_entry = {
                    "description": f"Auto-added interface {iface}",
                    "name": iface,
                    "locked": False
                }
                config["interfaces"]["wlan"].append(new_entry)
                new_entries.append(iface)
                self.logger.info(f"Auto-adding interface '{iface}' to configuration.")

        # if new interfaces are available, add them
        if new_entries:
            try:
                update_yaml_value(self.config_file, ["interfaces", "wlan"], config["interfaces"]["wlan"])
                self.logger.info(f"Auto-added wireless interfaces: {', '.join(new_entries)}")
            except Exception as e:
                self.logger.error(f"Error updating configuration file {self.config_file}: {e}")

        # reload in-memory configs
        self.reload_config()

    def reload_config(self) -> None:
        """
        Reloads the configuration from the YAML file and updates the
        in-memory settings (interfaces, presets, defaults, etc.).
        """

        self.config_data = load_yaml_config(self.config_file, self.logger)
        self.interfaces = self.config_data.get("interfaces", {})
        self.presets = self.config_data.get("presets", {})
        self.defaults = self.config_data.get("defaults", {})
        self.logger.info(f"Configuration reloaded from {self.config_file}")

### HARDWARE RELATED ###
    def get_scan_interface(self) -> str:
        """
        Returns the selected interface that was set via the submenu.
        """
        if self.selected_interface:
            return self.selected_interface
        else:
            raise ValueError("No interface has been selected. Please select an interface via the submenu.")

    def autobpf_helper(self,
                       scan_interface: str,
                       filter_path: Path,
                       interfaces: List[str],
                       extra_macs: Optional[List[str]] = None) -> bool:
        """
        Wrapper method to generate a BPF filter.

        :param: scan_interface: Interface name
        :param: filter_path: Path to the filter file
        :param: interfaces: List of interface names
        :param: extra_macs: List of extra mac addresses to filter
        :return: bool
        """
        return run_autobpf(self, scan_interface, filter_path, interfaces, extra_macs)

    def get_iface_macs(self, interface: str) -> Optional[str]:
        """
        Retrieve the MAC address of a given interface by reading from sysfs.

        If a generic interface name "wlan" is provided, this function looks up
        self.interfaces for the list of specific interface names (e.g., wlan0, wlan1)
        and uses the first available one.

        :return: Optional[str]:
            The MAC address as a string if found; otherwise, None.
        """
        if interface == "wlan":
            wlan_list = self.interfaces.get("wlan", [])
            if wlan_list:
                # Use the first available interface name from the list.
                interface = wlan_list[0].get("name")
            else:
                self.logger.warning("No wlan interfaces defined in self.interfaces.")
                return None
        try:
            with open(f"/sys/class/net/{interface}/address", "r") as f:
                mac = f.read().strip()
                return mac
        except Exception as e:
            self.logger.warning(f"Could not read MAC address from /sys/class/net/{interface}/address: {e}")
            return None

    def get_associated_macs(self, interfaces: List[str]) -> List[str]:
        """
        Scan the provided interfaces for associated client MAC addresses, excluding
        the interface currently selected for scanning (self.selected_interface).

        This function is used to build a Berkeley Packet Filter (BPF) to protect the
        non-selected interfaces by including the MAC addresses of associated clients/APs.

        :param: interfaces: List of interface identifiers. (e.g. wlan0, wlan1)
        :return: List[str]: A unique list of client MAC addresses associated with all interfaces other than
        the current self.selected_interface.
        """
        client_macs = set()
        selected_iface = self.selected_interface

        # exclude selected interface
        # get associates of all other attached interfaces
        refined_interfaces = []
        for iface in interfaces:
            if iface == "wlan":
                refined_interfaces += [
                    item.get("name")
                    for item in self.interfaces.get("wlan", [])
                    if item.get("name") and item.get("name") != selected_iface
                ]
            elif iface != selected_iface:
                refined_interfaces.append(iface)

        if not refined_interfaces:
            self.logger.warning(
                "No valid interfaces found for associated MAC scanning after excluding the selected interface."
            )
            return list(client_macs)

        for iface in refined_interfaces:
            output = self.run_shell(f"sudo iw dev {iface} station dump")
            if output:
                for line in output.splitlines():
                    stripped_line = line.strip()
                    if stripped_line.startswith("Station "):
                        parts = stripped_line.split()
                        if len(parts) >= 2:
                            mac_address = parts[1]
                            self.logger.debug(f"Found MAC address: {mac_address} in line: {stripped_line}")
                            client_macs.add(mac_address)
            else:
                self.logger.info(
                    f"No associated macs found for {iface}. "
                )
        self.logger.info(f"Found associated client MAC(s): {client_macs}")
        return list(client_macs)

### NETWORK RELATED ###
    def refresh_gateways(self):
        """
        Refreshes the gateway information by re-invoking the helper function.
        """
        from tools.helpers.tool_utils import get_gateways
        self.gateways = get_gateways()
        self.logger.info("Gateways refreshed: %s", self.gateways)

    def get_target_networks(self) -> dict:
        """
        Returns a dictionary mapping each interface (from self.interfaces)
        to its computed network (CIDR notation).
        """
        target_networks = {}
        for iface_info in self.interfaces.get("wlan", []):
            iface = iface_info.get("name")
            if iface:
                network = get_network_from_interface(iface)
                if network:
                    target_networks[iface] = network
        return target_networks


    ##########################
    ##### STATIC METHODS #####
    ##########################
    @staticmethod
    def check_uuid_for_root() -> bool:
        return os.getuid() == 0

    @staticmethod
    def normalize_cmd_options(key: str) -> str:
        """Ensure an option key starts with appropriate dashes."""
        return key if key.startswith("-") else "--" + key

    @staticmethod
    def cmd_to_dict(cmd_list: list) -> dict:
        """
        Converts a command list (e.g., ["hcxdumptool", "-i", "wlan1", ...])
        into a structured dictionary.
        """
        if not cmd_list:
            return {}
        return {
            "executable": cmd_list[0],
            "arguments": cmd_list[1:]
        }

    @staticmethod
    def cmd_to_string(cmd_list: list) -> str:
        """
        turn full cmd's from list format to string.
        :param cmd_list: list: the command to turn into string.
        :return: str: the string representation of the command.
        """
        logging.debug(f"received command list: {cmd_list}")
        cmd_str = None
        try:
            cmd_str = shlex.join(cmd_list)
            logging.debug(f"converted to command string: {cmd_str}")
        except Exception as e:
            logging.debug(f"failed to convert to command string: {e}")
        return cmd_str

    @staticmethod
    def run_shell(command: str) -> Optional[str]:
        """
        Execute a shell command and return its output.

        :param command: str: The command to execute.
        :return: command string

        Returns:
            Optional[str]: The command output if successful; otherwise, None.
        """
        try:
            output = subprocess.check_output(
                command, shell=True, stderr=subprocess.STDOUT, text=True
            )
            return output.strip()
        except subprocess.CalledProcessError as e:
            logging.debug(f"Error running command '{command}': {e.output}")
            return None

    @staticmethod
    def generate_default_prefix() -> str:
        """
        d-m-h-m format, same pcapng/nmea file prefix
        :returns str: Default prefix
        """
        return datetime.now().strftime("%m-%d_%H:%M:%S")

    #############################
    ##### SUBMENU UTILITIES #####
    #############################
    def update_presets_in_config(self, presets: dict) -> None:
        """
        Updates the tool's configuration file with the new presets, filtering out any options
        that have blank values (either an empty string or None).

        :param presets: A dictionary containing updated presets.
        :raises ValueError: If there is an error reading from or writing to the configuration file.
        :return: None
        """
        import yaml

        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error(f"Failed to load configuration file {self.config_file}: {e}")
            raise

        new_presets = {}
        for key, preset in presets.items():
            if "options" in preset and isinstance(preset["options"], dict):
                filtered_options = {k: v for k, v in preset["options"].items() if v not in ("", None)}
                preset["options"] = filtered_options
            new_presets[key] = preset

        config["presets"] = new_presets

        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            self.logger.info(f"Configuration updated with new presets in {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to write updated configuration to {self.config_file}: {e}")
            raise