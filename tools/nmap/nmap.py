import json
import logging
import subprocess
from abc import ABC
from datetime import datetime
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

        # For host-specific scans from hosts in database
        self.parent_dir = None
        self.selected_target_host = None
        self.selected_preset = None
        self.gateways = get_gateways()  # dict mapping interface -> gateway
        self.target_networks = self.get_target_networks()  # Compute CIDR for each interface
        self.target_ip = None

        # tools/nmap/submenu.py
        from tools.nmap.submenu import NmapSubmenu
        self.submenu_instance = NmapSubmenu(self)

        # override tools.py and set callback socket
        self.callback_socket = get_shared_callback_socket()
        shared_callback_listener.register_callback(self.name, self._on_scan_complete)

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

        if self.scan_mode == "cidr":
            if self.parent_dir is None:
                # create a temporary directory for the network scan
                self.parent_dir = self.results_dir / ("cidr_" + self.generate_default_prefix())
                self.parent_dir.mkdir(parents=True, exist_ok=True)
            output_dir = self.parent_dir
        elif self.scan_mode == "target":
            if hasattr(self, "current_network_dir"):
                # if scanning with the ALL option use "all_hosts" subdirectory
                if " " in target:
                    output_dir = self.current_network_dir / "all_hosts"
                else:
                    # single host: create a subdirectory named after the host IP
                    output_dir = self.current_network_dir / target
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                # fallback if current_network_dir is not set
                output_dir = self.results_dir / ("target_" + self.generate_default_prefix())
                output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = self.results_dir

        self.current_working_dir = output_dir
        self.logger.debug(f"Using output directory: {output_dir}")

        # Set file prefix. For multiple hosts, you might use a fixed name.
        if self.scan_mode == "target" and " " in target:
            file_prefix = output_dir / "combined"
        else:
            file_prefix = output_dir / self.generate_default_prefix()

        cmd.extend(["-oA", str(file_prefix)])
        for flag, val in self.selected_preset.get("options", {}).items():
            if isinstance(val, bool):
                if val:
                    cmd.append(flag)
            elif val:
                cmd.extend([flag, str(val)])
        self.logger.debug("Built command: " + " ".join(cmd))
        return cmd

    def run(self) -> None:
        """
        Executes an nmap scan based on the scan_mode flag.
        If scan_mode is "target", runs a host-specific scan.
        If scan_mode is "cidr", runs a network scan.
        If not set, attempts to decide based on available selections.
        """
        if self.scan_mode == "target":
            if not self.selected_target_host:
                self.logger.error("No target host specified for host scan.")
            else:
                self.logger.debug("Running host-specific scan (target mode) for %s.", self.selected_target_host)
                self.run_db_hosts(self.selected_target_host)
        elif self.scan_mode == "cidr":
            self.logger.debug("Running network scan (cidr mode).")
            self.run_db_networks()
        else:
            # Fallback: if a target host is set, prefer host scan; otherwise use network scan.
            if self.selected_target_host:
                self.logger.debug("Fallback: target host detected (%s), running host-specific scan.",
                                  self.selected_target_host)
                self.run_db_hosts(self.selected_target_host)
            elif self.selected_network:
                self.logger.debug("Fallback: network selection detected, running network scan.")
                self.run_db_networks()
            else:
                self.logger.error("No target selected for scan (neither target host nor network).")

    def _on_scan_complete(self, message: dict):
        """
        Callback function invoked when an nmap scan completes.

        This method is registered with the shared callback listener and is triggered when an
        IPC message with the action "SCAN_COMPLETE" is received. It inspects the current
        self.scan_mode and calls appropriate file-finding, parsing, and database insertion routine.

        :return:
            None
        """
        self.logger.info("SCAN_COMPLETE callback received: %s", message)
        gnmap_path = self._determine_gnmap_file_path()
        if gnmap_path is None or not gnmap_path.exists():
            self.logger.error("GNMAP file not found.")
            return

        if self.scan_mode == "cidr":
            self._process_db_network_results(gnmap_path)
        elif self.scan_mode == "target":
            self._process_db_host_results(gnmap_path)
        else:
            self.logger.error("Unknown scan mode: %s", self.scan_mode)

    ####################################
    ##### DB_NETWORKS SCAN METHODS #####
    ####################################
    def run_db_networks(self) -> None:
        """
        Uses config.yaml's db_networks scan (-sn, ping scan) to populate available hosts
        and on completion automatically imports hosts to database (nmap_network table) by
        parsing with _on_db_networks_complete and its helper in _parser.py parse_network_results.

        :return:
            None
        """
        self.selected_preset = {
            "description": "db_network",
            "options": {
                "-sn": True,
                "-T4": True
            }
        }

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

        # send to ipc
        response = self.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Network scan initiated successfully: %s", response)
        else:
            self.logger.error("Error initiating network scan via IPC: %s", response)

    def _process_db_network_results(self, gnmap_path: Path):
        from tools.nmap.db import insert_nmap_network_result
        from tools.nmap._parser import parse_network_results

        self.logger.info("Processing scan results from %s", gnmap_path)
        network_data, hosts = parse_network_results(gnmap_path)

        # set CIDR value from chosen network
        network_data["cidr"] = self.selected_network

        # ARP query router IP if bssid is empty
        if not network_data.get("bssid") and network_data.get("router_ip"):
            arp_output = self.run_shell(f"arp -a {network_data['router_ip']}")
            import re
            m = re.search(r"(([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2}))", arp_output)
            if m:
                network_data["bssid"] = m.group(0)
                self.logger.debug("Extracted BSSID via ARP: %s", network_data["bssid"])
            else:
                network_data["bssid"] = ""

        # rename the current working directory using the router's MAC address
        router_mac = network_data.get("bssid", None)
        if router_mac:
            new_dir = self.results_dir / router_mac
            try:
                # only rename if the directory doesn't already have that name
                if self.current_working_dir != new_dir:
                    import os
                    os.rename(self.current_working_dir, new_dir)
                    self.current_working_dir = new_dir
                    self.logger.debug("Renamed output directory to: %s", new_dir)
            except Exception as e:
                self.logger.error("Error renaming directory: %s", e)

        # insert results into the database
        conn = get_db_connection(BASE_DIR)
        try:
            network_id = insert_nmap_network_result(
                conn,
                network_data.get("bssid", ""),
                self.get_iface_macs(self.selected_interface),
                network_data["cidr"],
                network_data.get("router_ip", ""),
                network_data.get("router_hostname", ""),
                hosts
            )
            self.current_network_id = network_id
            self.logger.info("Inserted network scan with ID: %s", network_id)
            conn.commit()
        except Exception as e:
            self.logger.error("Error inserting scan results into DB: %s", e)
        finally:
            conn.close()

    #################################
    ##### DB_HOSTS SCAN METHODS #####
    #################################
    def run_db_hosts(self, host_ip: str) -> None:
        """
        Executes an nmap host scan (-A) for a single host specified by host_ip.
        Builds the command for the host scan, sends it via IPC, and lets the
        scan complete callback process the results.
        """
        self.selected_preset = {
            "description": "db_host",
            "options": {
                "-A": True,
                "--top-ports": 1000,
                "-T4": True
            }
        }
        if not host_ip:
            self.logger.error("No host IP provided for host scan.")
            return

        # build the command for the specified host
        cmd_list = self.build_nmap_command(host_ip)
        self.logger.debug("Single host scan command list: %s", cmd_list)

        # convert the command list to a dict for IPC compatibility
        cmd_dict = self.cmd_to_dict(cmd_list)
        self.logger.debug("Single host scan command dict: %s", cmd_dict)

        # set the preset description from configuration
        self.preset_description = self.selected_preset.get("description", "nmap_host_scan")

        # send the command via IPC
        response = self.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Host scan for %s initiated successfully: %s", host_ip, response)
        else:
            self.logger.error("Error initiating host scan for %s via IPC: %s", host_ip, response)

    def _process_db_host_results(self, gnmap_path: Path):
        # existing processing of host results...
        from tools.nmap._parser import parse_host_results
        from tools.nmap.db import insert_nmap_host_result
        self.logger.info("Processing host scan results from %s", gnmap_path)
        hosts_json = parse_host_results(gnmap_path)
        try:
            host_list = json.loads(hosts_json)
        except Exception as e:
            self.logger.error("Error decoding host scan JSON: %s", e)
            return

        if not hasattr(self, "current_network_id") or self.current_network_id is None:
            self.logger.error("No current network ID available; cannot insert host scan results.")
            return

        network_id = self.current_network_id
        now = datetime.now()
        scan_date = now.strftime("%Y-%m-%d")
        scan_time = now.strftime("%H:%M:%S")
        conn = get_db_connection(BASE_DIR)
        for host in host_list:
            host_ip = host.get("ip", "")
            open_ports = json.dumps(host.get("ports", []))
            services = host.get("os", "")
            try:
                insert_nmap_host_result(conn, network_id, host_ip, open_ports, services, scan_date, scan_time)
                self.logger.info("Inserted host scan result for host: %s", host_ip)
            except Exception as e:
                self.logger.error("Error inserting host scan result for %s: %s", host_ip, e)
        conn.commit()
        conn.close()

        # Run searchsploit for each host if in 'all' mode,
        # or run normally if scanning a single host.
        if " " in self.selected_target_host:
            # Multiple targets: run searchsploit per host
            for host in host_list:
                ip = host.get("ip", "")
                if ip:
                    self.run_searchsploit_per_host(gnmap_path, ip)
        else:
            # Single host: run searchsploit normally (or use run_searchsploit)
            self.run_searchsploit(gnmap_path)

    #####################
    ##### UTILITIES #####
    #####################
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

    def run_searchsploit(self, nmap_file: Path) -> None:
        """
        Runs searchsploit on the provided nmap file and outputs the results to a text file
        in the current working directory associated with the db_host scan.
        Output is captured and not printed to the terminal.
        """
        # this sets output path to target hosts dir
        output_file = self.current_working_dir / "searchsploit_results.txt"

        cmd = ["searchsploit", "--nmap", str(nmap_file)]
        self.logger.info(f"Running searchsploit command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            with open(output_file, "w") as f:
                f.write(result.stdout)
            self.logger.info(f"Searchsploit results saved to: {output_file}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Searchsploit command failed: {e}")


    def run_searchsploit_per_host(self, nmap_file: Path, host_ip: str) -> None:
        """
        Runs searchsploit on the provided nmap file for a single host and writes the results to a file
        named after the host's IP in the current working directory.

        :param nmap_file: Path to the GNMAP file generated by the scan.
        :param host_ip: The IP address of the host for which to run searchsploit.
        """
        output_file = self.current_working_dir / f"{host_ip}.txt"
        cmd = ["searchsploit", "--nmap", str(nmap_file)]
        self.logger.info(f"Running searchsploit for {host_ip}: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            with open(output_file, "w") as f:
                f.write(result.stdout)
            self.logger.info(f"Searchsploit results for {host_ip} saved to: {output_file}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Searchsploit command for {host_ip} failed: {e}")








