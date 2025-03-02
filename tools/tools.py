import logging
import shlex
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from abc import abstractmethod


# local
from config.constants import BASE_DIR
from common.config_utils import load_yaml_config
from tools.helpers.autobpf import run_autobpf
from utils.ipc import send_ipc_command


class Tool:
    def __init__(self, name: str, description: str, base_dir: Path,
                 config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, settings: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.description = description
        self.base_dir = Path(base_dir).resolve()

        # Define essential directories based on base_dir.
        self.config_dir = self.base_dir / "configs"
        self.results_dir = self.base_dir / "results"

        # Ensure required directories exist.
        self._setup_directories()

        # Setup logger.
        self.logger = logging.getLogger(f"{self.name.upper()}")
        self.logger.info(f"Initialized tool: {self.name}")

        # Determine the configuration file path using a helper function.
        self.config_file = self._determine_config_path(config_file)
        self.logger.debug(f"Using config file: {self.config_file}")

        # Load configuration.
        self.config_data = load_yaml_config(self.config_file, self.logger)

        # Extract config sections.
        self.interfaces = self.config_data.get("interfaces", {})
        self.presets = self.config_data.get("presets", {})
        self.defaults = self.config_data.get("defaults", {})

        # Optional Overrides.
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
        """
        Launch the scan command in a background pane via IPC.
        The IPC server will:
          - Get or create the background window for this tool.
          - Allocate or identify a pane.
          - Run the provided command.

        The message is now structured as a dictionary.
        """
        ipc_message = {
            "action": "SEND_SCAN",
            "tool": self.name,
            "scan_profile": scan_profile,
            "command": cmd_dict,
            "timestamp": time.time()  # Optionally include a timestamp.
        }
        self.logger.debug("Sending IPC scan command: %s", ipc_message)

        # Send the structured message; assume send_ipc_command handles JSON.
        response = send_ipc_command(ipc_message)

        if isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            pane_id = response.get("pane_id")
            if pane_id:
                self.logger.debug("Scan command executed successfully in pane %s.", pane_id)
            else:
                self.logger.warning("Scan command succeeded but pane id is missing.")
        else:
            self.logger.error("Error executing scan command via IPC: %s", response)
        return response


    def autobpf_helper(self,
                       scan_interface: str,
                       filter_path: Path,
                       interfaces: List[str],
                       extra_macs: Optional[List[str]] = None) -> bool:
        """
        Wrapper method to generate a BPF filter using the autobpf helper.
        """
        return run_autobpf(self, scan_interface, filter_path, interfaces, extra_macs)


    def get_iface_macs(self, interface: str) -> Optional[str]:
        """
        Retrieve the MAC address of a given interface by reading from sysfs.

        Returns:
            List[str]: A list of MAC addresses attached to your device.
        """
        try:
            with open(f"/sys/class/net/{interface}/address", "r") as f:
                mac = f.read().strip()
                return mac
        except Exception as e:
            self.logger.warning(f"Could not read MAC address from /sys/class/net/{interface}/address: {e}")
            return None


    def get_associated_macs(self, interfaces: List[str]) -> List[str]:
        """
        Scan the provided interfaces for associated client MAC addresses.
        For each interface, uses 'sudo iw dev <iface> station dump'
        to extract connected client MAC addresses.

        Returns:
            List[str]: A unique list of client MAC addresses.
        """
        # todo: simplify this using self.interfaces dict and maybe split into two

        client_macs = set()
        for iface in interfaces:
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
                self.logger.warning(
                    f"Could not retrieve station dump for interface {iface} "
                    f"please ignore this warning if it is your selected scan interface."
                )
        self.logger.info(f"Found associated client MAC(s): {client_macs}")
        return list(client_macs)


    def run(self):
        self.logger.info("No you run..")
        return


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
        :param cmd_list:
        :return:
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

        Parameters:
            command (str): The command to execute.

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
        Returns:
            str: The generated prefix string.
        """
        return datetime.now().strftime("%d-%m_%H:%M")