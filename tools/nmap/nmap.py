import logging
from abc import ABC
from pathlib import Path
from typing import Optional, Dict, Any

# locals
from config.constants import BASE_DIR
from tools.tools import Tool
from utils.ipc_callback import get_shared_callback_socket, shared_callback_listener
from utils.tool_registry import register_tool
from tools.helpers.tool_utils import get_gateways
from database.db_manager import get_db_connection
from tools.nmap.db import init_nmap_network_schema, init_nmap_host_schema
from tools.nmap._parser import parse_network_results

@register_tool("nmap")
class Nmap(Tool, ABC):
    def __init__(self, base_dir: Path, config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, presets: Optional[Dict[str, Any]] = None):

        super().__init__(
            name="nmap",
            description="Network scanning using nmap",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=presets
        )
        self.logger = logging.getLogger(self.name)

        # Set a scan mode flag:
        # 'cidr' for full network,
        # 'target' for host specific parsed from results/file.gnmap
        self.scan_mode = None

        # For full-network scans
        self.selected_network = None
        self.current_working_dir = None

        # For host-specific scans parsed from .gnmap results
        self.parent_dir = None
        self.selected_target_host = None
        self.selected_preset = None
        self.gateways = get_gateways()  # dict mapping interface -> gateway
        self.target_networks = self.get_target_networks()  # Compute CIDR for each interface

        # tools/nmap/submenu.py
        from tools.nmap.submenu import NmapSubmenu
        self.submenu_instance = NmapSubmenu(self)

        # override tools.py and set callback socket
        self.callback_socket = get_shared_callback_socket()
        shared_callback_listener.register_callback(self.name, self.on_network_scan_complete)

        # nmap-specific database schema (tools/nmap/db.py)
        conn = get_db_connection(BASE_DIR)
        init_nmap_network_schema(conn)
        init_nmap_host_schema(conn)
        conn.close()

    def submenu(self, stdscr) -> None:
        """
        Launches the nmap submenu (interactive UI) using curses.
        """
        self.submenu_instance(stdscr)

    def build_nmap_command(self, target: str) -> list:
        """
        Builds an nmap command for a given target (network or host).
        The command uses the -oA option so that XML, grepable, and normal output files are generated.
        """
        cmd = ["nmap", target]

        # determine the output directory based on the scan mode
        if self.scan_mode == "cidr":
            if self.parent_dir is None:
                self.parent_dir = self.results_dir / ("cidr_" + self.generate_default_prefix())
                self.parent_dir.mkdir(parents=True, exist_ok=True)
            output_dir = self.parent_dir
        elif self.scan_mode == "target":
            if self.parent_dir is not None:
                # create a subdirectory for the target host under the existing parent_dir
                output_dir = self.parent_dir / target
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                # fallback to default results if no parent_dir exists
                output_dir = self.results_dir / ("target_" + self.generate_default_prefix())
                output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = self.results_dir

        # working directory we can reference
        self.current_working_dir = output_dir

        self.logger.debug(f"Scan mode: {self.scan_mode} Creating output directory: {output_dir}")
        file_prefix = output_dir / self.generate_default_prefix()
        cmd.extend(["-oA", str(file_prefix)])

        # append additional options from the preset
        options = self.selected_preset.get("options", {})
        for flag, val in options.items():
            if isinstance(val, bool):
                if val:
                    cmd.append(flag)
            elif val:
                cmd.extend([flag, str(val)])

        self.logger.debug("Built command: " + " ".join(cmd))
        return cmd

    def run_from_selected_network(self) -> None:
        if not self.selected_network:
            self.logger.error("No target network selected; cannot build command.")
            return
        if not self.selected_preset:
            self.logger.error("No preset selected; cannot build command.")
            return

        # build cmd for target network
        cmd_list = self.build_nmap_command(self.selected_network)
        self.logger.debug("Command list: %s", cmd_list)

        # convert cmd list to dict for ipc compatibility
        cmd_dict = self.cmd_to_dict(cmd_list)
        self.logger.debug("Command dict: %s", cmd_dict)

        # set the preset description from config
        self.preset_description = self.selected_preset["description"]
        # ensure selected_interface is set
        #if not self.selected_interface:
            #self.selected_interface = self.selected_network

        # send to ipc
        response = self.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Network scan initiated successfully: %s", response)
        else:
            self.logger.error("Error initiating network scan via IPC: %s", response)

    def run_target_from_results(self) -> None:
        """
        Executes an nmap scan using the selected target host (self.selected_target_host).
        The overridden run_to_ipc automatically adds the shared callback socket.
        """
        if not self.selected_target_host:
            self.logger.error("No target host selected for rescan from results.")
            return
        if not self.selected_preset:
            self.logger.error("No preset selected for target rescan.")
            return

        # build cmd for target host
        cmd_list = self.build_nmap_command(self.selected_target_host)
        self.logger.debug("Target scan command list: %s", cmd_list)

        # convert cmd list to dict for ipc compatibility
        cmd_dict = self.cmd_to_dict(cmd_list)
        self.logger.debug("Target scan command dict: %s", cmd_dict)

        # set the preset description from config
        self.preset_description = self.selected_preset.get("description", "nmap_scan")
        # ensure selected interface
        if not self.selected_interface:
            self.selected_interface = self.selected_network

        # send to ipc
        response = self.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Target scan initiated successfully: %s", response)
        else:
            self.logger.error("Error initiating target scan via IPC: %s", response)

    def run(self) -> None:
        """
        Executes an nmap scan based on the scan_mode flag.
        If scan_mode is "target", runs a host-specific scan.
        If scan_mode is "cidr", runs a network scan.
        If not set, attempts to decide based on available selections.
        """
        if self.scan_mode == "target":
            self.logger.debug("Running host-specific scan (target mode).")
            self.run_target_from_results()
        elif self.scan_mode == "cidr":
            self.logger.debug("Running network scan (cidr mode).")
            self.run_from_selected_network()
        else:
            # Fallback: if a target host is set, prefer host scan; otherwise use network scan.
            if self.selected_target_host:
                self.logger.debug("Fallback: target host detected, running host-specific scan.")
                self.run_target_from_results()
            elif self.selected_network:
                self.logger.debug("Fallback: network selection detected, running network scan.")
                self.run_from_selected_network()
            else:
                self.logger.error("No target selected for scan (neither target host nor network).")

    def _determine_gnmap_file_path(self) -> Optional[Path]:
        """
        Searches the current working directory for a .gnmap file.

        :return: Optional[Path]:
            the first .gnmap file found (or None if no file exists).
        """
        self.logger.debug(f"Checking for .gnmap files in: {self.current_working_dir}")
        if not hasattr(self, "current_working_dir"):
            self.logger.error("current_working_dir is not set.")
            return None

        gnmap_files = list(Path(self.current_working_dir).glob("*.gnmap"))
        self.logger.debug(f"All files in {self.current_working_dir}: {list(Path(self.current_working_dir).iterdir())}")

        if gnmap_files:
            self.logger.debug(f".gnmap files found: {[str(f) for f in gnmap_files]}")
            return gnmap_files[0]
        else:
            self.logger.error("No .gnmap files found in %s", self.current_working_dir)
            return None

    def on_network_scan_complete(self, message: dict):
        """
        Called when a network scan completes & checks for newly created network scans
        by looking for self.current_working_dir.

        :param message: ipc callback message
        :return: None
        """
        self.logger.info("SCAN_COMPLETE callback received: %s", message)
        gnmap_path = self._determine_gnmap_file_path()
        if gnmap_path is None or not gnmap_path.exists():
            self.logger.error("GNMAP file not found.")
            return
        self.process_network_results(gnmap_path)

    def process_network_results(self, gnmap_path: Path):
        """
        Processes the network scan results from a .gnmap file.
        It parses the file to extract network-level data and host entries,
        then inserts the data into the nmap_network table.

        :param gnmap_path: Path to the .gnmap file.
        """
        from tools.nmap.db import insert_nmap_network_result
        from database.db_manager import get_db_connection
        from config.constants import BASE_DIR

        self.logger.info("Processing scan results from %s", gnmap_path)
        network_data, hosts = parse_network_results(gnmap_path)

        # set cidr value from chosen network
        network_data["cidr"] = self.selected_network

        # arp query router IP if bssid is empty
        if not network_data.get("bssid") and network_data.get("router_ip"):
            arp_output = self.run_shell(f"arp -a {network_data['router_ip']}")
            import re
            m = re.search(r"(([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2}))", arp_output)
            if m:
                network_data["bssid"] = m.group(0)
                self.logger.debug("Extracted BSSID via ARP: %s", network_data["bssid"])
            else:
                network_data["bssid"] = ""
        # open database connection
        conn = get_db_connection(BASE_DIR)
        try:
            # insert scan data to nmap_network table
            network_id = insert_nmap_network_result(
                conn,
                network_data.get("bssid", ""),
                self.get_iface_macs(self.selected_interface),
                network_data["cidr"],
                network_data.get("router_ip", ""),
                network_data.get("router_hostname", ""),
                hosts
            )
            self.logger.info("Inserted network scan with ID: %s", network_id)
            conn.commit()
        except Exception as e:
            self.logger.error("Error inserting scan results into DB: %s", e)
        finally:
            conn.close()






