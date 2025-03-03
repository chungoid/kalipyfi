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

        self.submenu = HcxToolSubmenu(self)

    def get_scan_interface(self) -> str:
        """
        Returns the selected interface that was set via the submenu.
        """
        if self.selected_interface:
            return self.selected_interface
        else:
            raise ValueError("No interface has been selected. Please select an interface via the submenu.")

    def build_command(self) -> list:
        """
        Builds the hcxdumptool command from the scan settings and options.
        Returns:
            list: The full command as a list of arguments.
        """
        preset = self.presets
        cmd = ["hcxdumptool"]

        for p in preset:
            self.logger.info(f"preset {p}")

        # 1. Determine the interface
        scan_interface = self.selected_interface
        cmd.extend(["-i", scan_interface])
        self.logger.debug(f"scan interface: {scan_interface}")

        # 2. Generate a default prefix and convert it to a Path
        prefix = self.results_dir / self.generate_default_prefix()
        self.presets["output_prefix"] = str(prefix)
        # 'prefix' is a Path object
        pcap_file = str(prefix.with_suffix('.pcapng'))
        cmd.extend(["-w", pcap_file])
        self.logger.debug(f"Setting pcapng filepath: {pcap_file}")

        # 3. GPS options
        if preset.get("options", {}).get("--gpsd", False):
            cmd.append("--gpsd")
            cmd.append("--nmea_pcapng")
            nmea_path = f"--nmea_out={prefix.with_suffix('.nmea')}"
            cmd.append(nmea_path)
            self.logger.debug(f"Setting NMEA filepath: {nmea_path}")

        # 4. Check if the preset defines a channel
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


        # 5. Use the 'auto_bpf' (or 'autobpf') flag from the preset
        if preset.get("auto_bpf", False) or preset.get("autobpf", False):
            bpf_file = self.config_dir / "filter.bpf"
            self.logger.debug(f"Using auto-generated BPF filter: {bpf_file}")
            cmd.append(f"--bpf={bpf_file}")

        # 6. Merge and append additional options
        merged_options = self.defaults.copy()
        # Remove handled keys.
        for key in ("-i", "-w", "--gpsd", "--nmea_out", "--nmea_pcapng", "-c", "--bpf"):
            merged_options.pop(key, None)

        # Now, add remaining options from the preset options directly
        if "options" in preset:
            for opt, val in preset["options"].items():
                # For boolean options, include the option if True
                if isinstance(val, bool):
                    if val:
                        cmd.append(opt)
                else:
                    # Otherwise, format it as option=value.
                    cmd.append(f"{opt}={val}")

        # Append remaining default options.
        for opt, val in merged_options.items():
            norm_option = Tool.normalize_cmd_options(opt)
            if isinstance(val, bool):
                if val:
                    cmd.append(norm_option)
            elif val is not None:
                cmd.append(f"{norm_option}={val}")

        self.logger.debug("Finished building command: " + " ".join(cmd))
        return cmd


    def run(self, profile=None) -> None:
        # Process the scan profile and reserve the interface, etc.
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



