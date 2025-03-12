import logging
import netifaces
from pathlib import Path
from typing import Optional, Any, Dict

from tools.helpers.tool_utils import get_gateways, get_network_from_interface
# Import your base Tool and the registration decorator.
from tools.tools import Tool
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
        self.logger = logging.getLogger("NMAP")
        self.selected_network = None
        self.selected_preset = None
        self.gateways = get_gateways()  # Initial population, can be refreshed via helper method in submenu
        self.target_networks = self.get_target_networks()  # CIDR calculated via self.elected_network

        from tools.nmap.submenu import NmapSubmenu
        self.submenu_instance = NmapSubmenu(self)

    def build_command(self) -> list:
        """
        Constructs the nmap command based on the selected network and preset options.
        """
        if not self.selected_preset:
            self.logger.error("No preset selected; cannot build command.")
            return []
        if not self.selected_network:
            self.logger.error("No network target selected; cannot build command.")
            return []

        preset = self.selected_preset
        target = self.selected_network

        # start command build with nmap <target>
        cmd = ["nmap", target]

        # append options
        options = preset.get("options", {})
        for flag, val in options.items():
            if isinstance(val, bool):
                if val:
                    cmd.append(flag)
            elif val:
                # handle flag spacing
                cmd.extend([flag, str(val)])

        self.logger.debug("Built nmap command: " + " ".join(cmd))
        return cmd

    def run(self) -> None:
        """
        Runs the nmap scan by building the command and sending it via IPC.
        """
        cmd_list = self.build_command()
        if not cmd_list:
            self.logger.error("Empty command list; aborting scan.")
            return

        # command list -> dict for ipc
        cmd_dict = self.cmd_to_dict(cmd_list)

        # tools/tools.py run_to_ipc()
        response = self.run_to_ipc(self.selected_preset.get("description", "nmap_scan"), cmd_dict)
        if response and isinstance(response, dict):
            self.logger.info("Scan initiated successfully: %s", response)
        else:
            self.logger.error("Error initiating scan via IPC: %s", response)

    def submenu(self, stdscr) -> None:
        """
        Launches the nmap submenu (interactive UI) using curses.
        """
        self.submenu_instance(stdscr)



