import logging
import os
import shlex
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from abc import abstractmethod

# local
from config.constants import BASE_DIR
from common.logging_setup import get_log_queue, worker_configurer
from common.config_utils import load_yaml_config
from tools.helpers.autobpf import run_autobpf
from utils.helper import get_published_socket_path


class Tool:
    def __init__(self, name: str, description: str, base_dir: Path,
                 config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, settings: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.description = description
        self.base_dir = Path(base_dir).resolve()

        if not logging.getLogger().handlers:
            worker_configurer(get_log_queue())

        # Define essential directories based on base_dir
        self.config_dir = self.base_dir / "configs"
        self.results_dir = self.base_dir / "results"

        # Ensure required directories exist.
        self._setup_directories()

        #Setup logger
        self.logger = logging.getLogger(self.name.upper())
        self.logger.info(f"Initialized tool: {self.name}")

        # Determine the configuration file path using a helper function
        self.config_file = self._determine_config_path(config_file)
        self.logger.debug(f"Using config file: {self.config_file}")

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

        # Optional Overrides
        if interfaces:
            self.interfaces.update(interfaces)
        if settings:
            self.defaults.update(settings)


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


    @abstractmethod
    def submenu(self, stdscr) -> None:
        """
        Launches the tool-specific submenu using curses.
        Must be implemented by concrete tool classes.
        """
        pass


    def run_to_ipc(self, scan_profile: str, cmd_dict: dict):
        from utils.ipc_client import IPCClient
        client = IPCClient()
        socket_path = get_published_socket_path()
        """
        Launch the scan command in a background pane via IPC.
        The IPC server will:
          - Get or create the background window for this tool.
          - Allocate or identify a pane.
          - Run the provided command.
        """
        ipc_message = {
            "action": "SEND_SCAN",
            "tool": self.name,
            "scan_profile": scan_profile,
            "command": cmd_dict,
            "interface": self.selected_interface,
            "timestamp": time.time()
        }
        self.logger.debug("Sending IPC scan command: %s", ipc_message)

        # response will always be json
        response = client.send(ipc_message)

        if isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            pane_id = response.get("pane_id")
            if pane_id:
                self.logger.debug("Scan command executed successfully in pane %s.", pane_id)
            else:
                self.logger.warning("Scan command succeeded but pane id is missing.")
        else:
            self.logger.error("Error executing scan command via IPC: %s", response)
        return response


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
        """
        return run_autobpf(self, scan_interface, filter_path, interfaces, extra_macs)

    def get_iface_macs(self, interface: str) -> Optional[str]:
        """
        Retrieve the MAC address of a given interface by reading from sysfs.

        If a generic interface name "wlan" is provided, this function looks up
        self.interfaces for the list of specific interface names (e.g., wlan0, wlan1)
        and uses the first available one.

        Returns
        -------
        Optional[str]
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

        Parameters
        ----------
        interfaces : List[str]
            A list of interface identifiers. If the list contains the generic "wlan",
            it will be replaced by the specific interface names defined under self.interfaces["wlan"].

        Returns
        -------
        List[str]
            A unique list of client MAC addresses found on interfaces other than the selected one.
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


    def run(self):
        self.logger.info("No you run..")
        return

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

        Parameters
        ----------
        presets : dict
            A dictionary containing the updated presets.

        Raises
        ------
        Exception
            If there is an error reading from or writing to the configuration file.
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