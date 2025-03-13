import logging
from pathlib import Path
from typing import Optional, Dict, Any

# locals
from tools.tools import Tool
from tools.helpers.tool_utils import get_gateways
from utils.tool_registry import register_tool

@register_tool("nmap")
class Nmap(Tool):
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

        # For host-specific scans parsed from .gnmap results
        self.parent_dir = None
        self.selected_target_host = None
        self.selected_preset = None
        self.gateways = get_gateways()  # dict mapping interface -> gateway
        self.target_networks = self.get_target_networks()  # Compute CIDR for each interface

        # tools/nmap/submenu.py
        from tools.nmap.submenu import NmapSubmenu
        self.submenu_instance = NmapSubmenu(self)

    def build_nmap_command(self, target: str) -> list:
        """
        Builds an nmap command for a given target (network or host).

        - If scan_mode is "cidr", a new subdirectory is created in self.results_dir
          using a "cidr_" prefix and a timestamp; this directory is stored in self.parent_dir.
        - If scan_mode is "target" and self.parent_dir is set, a subdirectory named after
          the target (IP) is created under self.parent_dir.
        - Otherwise, the output is stored directly in self.results_dir.

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
                # If no parent_dir exists (should not happen if a CIDR scan was done first) fallback to default results
                output_dir = self.results_dir / ("target_" + self.generate_default_prefix())
                output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Default case: use the results directory.
            output_dir = self.results_dir

        self.logger.debug(f"Scan mode: {self.scan_mode} Creating {output_dir}")
        file_prefix = output_dir / self.generate_default_prefix()
        cmd.extend(["-oA", str(file_prefix)])

        # append additional options
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
        """
        Executes an nmap scan using the selected network (self.selected_network).
        """
        if not self.selected_network:
            self.logger.error("No target network selected; cannot build command.")
            return
        if not self.selected_preset:
            self.logger.error("No preset selected; cannot build command.")
            return

        # so scandata can assist view scans menu in showing all fields
        if not self.selected_interface:
            self.selected_interface = self.selected_network

        # so scandata can assist view scans menu in showing all fields
        self.preset_description = self.selected_preset["description"]

        # Build command using the network target.
        cmd_list = self.build_nmap_command(self.selected_network)
        cmd_dict = self.cmd_to_dict(cmd_list)
        response = self.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Network scan initiated successfully: %s", response)
        else:
            self.logger.error("Error initiating network scan via IPC: %s", response)

    def run_target_from_results(self) -> None:
        """
        Executes an nmap scan using the selected target host (self.selected_target_host).
        """
        if not self.selected_target_host:
            self.logger.error("No target host selected for rescan from results.")
            return
        if not self.selected_preset:
            self.logger.error("No preset selected for target rescan.")
            return

        cmd_list = self.build_nmap_command(self.selected_target_host)
        cmd_dict = self.cmd_to_dict(cmd_list)
        self.preset_description = self.selected_preset.get("description", "nmap_scan")
        self.selected_interface = self.selected_network
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
            # fallback: if a target host is set, prefer host scan; otherwise use network scan.
            if self.selected_target_host:
                self.logger.debug("Fallback: target host detected, running host-specific scan.")
                self.run_target_from_results()
            elif self.selected_network:
                self.logger.debug("Fallback: network selection detected, running network scan.")
                self.run_from_selected_network()
            else:
                self.logger.error("No target selected for scan (neither target host nor network).")

    def submenu(self, stdscr) -> None:
        """
        Launches the nmap submenu (interactive UI) using curses.
        """
        self.submenu_instance(stdscr)



