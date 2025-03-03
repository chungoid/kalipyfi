import logging
import os
import traceback
from abc import ABC
from pathlib import Path
from typing import Optional, Any, Dict


#locals
from tools.tools import Tool
from utils.tool_registry import register_tool
from tools.hcxtool.submenu import HcxToolSubmenu

@register_tool("hcxtool")
class Hcxtool(Tool, ABC):
    def __init__(self, base_dir: Path, config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None, presets: Optional[Dict[str, Any]] = None):

        super().__init__(
            name="hcxtool",
            description="utilize hcxtool",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=presets
        )

        self.logger = logging.getLogger(self.name)
        self.submenu = HcxToolSubmenu(self)


    def build_command(self) -> list:
        preset = self.presets
        cmd = ["hcxdumptool"]

        # 1. Determine the interface and add it.
        scan_interface = self.selected_interface
        cmd.extend(["-i", scan_interface])
        self.logger.debug(f"Scan interface: {scan_interface}")

        # 2. Generate the output prefix and add the -w option.
        prefix = self.results_dir / self.generate_default_prefix()
        self.presets["output_prefix"] = str(prefix)
        pcap_file = str(prefix.with_suffix('.pcapng'))
        cmd.extend(["-w", pcap_file])
        self.logger.debug(f"Setting pcapng filepath: {pcap_file}")

        # 3. Add GPS options if set in presets.
        if preset.get("options", {}).get("--gpsd", False):
            cmd.append("--gpsd")
            cmd.append("--nmea_pcapng")
            nmea_path = f"--nmea_out={prefix.with_suffix('.nmea')}"
            cmd.append(nmea_path)
            self.logger.debug(f"Setting NMEA filepath: {nmea_path}")

        # 4. Add channel options from the preset.
        if "channel" in preset:
            channel_value = preset["channel"]
            if isinstance(channel_value, list):
                channel_str = ",".join(str(ch) for ch in channel_value)
            else:
                channel_str = str(channel_value).strip()
                if " " in channel_str:
                    channel_str = ",".join(channel_str.split())
            cmd.extend(["-c", channel_str])
            self.logger.debug(f"Setting channel(s): {channel_str}")

        # 5. Add autobpf option if specified.
        if preset.get("autobpf", False):
            bpf_file = self.config_dir / "filter.bpf"
            self.logger.debug(f"Using auto-generated BPF filter: {bpf_file}")
            cmd.append(f"--bpf={bpf_file}")

        # 6. Add additional options from the preset.
        if "options" in preset:
            for opt, val in preset["options"].items():
                # Only add the option if val is not false.
                if isinstance(val, bool):
                    if val:
                        cmd.append(opt)
                elif val is not None:
                    cmd.append(f"{opt}={val}")

        self.logger.debug("Finished building command: " + " ".join(cmd))
        return cmd


    def run(self, profile=None) -> None:
        # Process the scan profile
        self.logger.debug("Building scan command.")
        try:
            cmd_list = self.build_command()
            if not cmd_list:
                self.logger.critical("Error: build_command() returned an empty command.")
                return

            # Convert the command list into a structured dictionary
            cmd_dict = self.cmd_to_dict(cmd_list)
            self.logger.debug("Command dict built: %s", cmd_dict)

            # Create a pane title; the UI manager will handle pane creation
            pane_title = f"{self.selected_interface}_#{profile}"
            self.logger.debug(f"Using pane title: {pane_title}")

            # Send the structured command to the IPC server
            response = self.run_to_ipc(pane_title, cmd_dict)
            if not (response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK")):
                self.logger.error("Scan failed to send to pane. Response: %s", response)
                return

        except Exception as e:
            self.logger.critical(f"Error launching scan: {e}")
            self.logger.debug(traceback.format_exc())
            return


        ##############################
        ##### utilities for user #####
        ##############################







