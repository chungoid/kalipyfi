import logging
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
        """
        Builds the hcxdumptool command based solely on the selected interface and the
        options defined in the preset. Only options explicitly provided in the preset
        will be added.

        Expected Behavior:
            - The command starts with "hcxdumptool".
            - The selected interface is appended using the "-i" flag.
            - The output file is set using the "-w" flag, with a .pcapng extension.
            - If "--gpsd" is True in the preset options, the command will also include
              "--gpsd", "--nmea_pcapng", and a corresponding "--nmea_out=" argument.
            - If "autobpf" is True in the preset options, a "--bpf=" option is added.
            - Any other options in the preset’s "options" dictionary are processed as follows:
                  * For boolean options: the flag is appended only if the value is True.
                  * For non-boolean options: the flag is appended in the format "flag=value".

        Returns
        -------
        list
            The list of command-line arguments forming the full hcxdumptool command.
        """
        # ensure that a preset has been selected
        if not hasattr(self, 'selected_preset') or not self.selected_preset:
            self.logger.error("No valid preset selected; cannot build command.")
            return []

        preset = self.selected_preset             # preset dict in config.yaml
        scan_interface = self.selected_interface  # scan_interface selected in submenu
        options = preset.get("options", {})       # options keys in preset dict

        # prepend sudo if not running as root.
        if Tool.check_uuid_for_root():
            cmd = ["hcxdumptool"]
        else:
            cmd = ["sudo", "-E", "hcxdumptool"]

        # 1. append the selected interface
        cmd.extend(["-i", scan_interface])
        self.logger.debug(f"Scan interface: {scan_interface}")

        # 2. determine the output prefix and add the "-w" option
        prefix = self.results_dir / self.generate_default_prefix()
        # Record the output prefix in the preset if specified
        preset["output_prefix"] = str(prefix)
        pcap_file = str(prefix.with_suffix('.pcapng'))
        cmd.extend(["-w", pcap_file])
        self.logger.debug(f"Setting pcapng filepath: {pcap_file}")

        # 3. handle GPS
        if options.get("--gpsd", False):
            cmd.append("--gpsd")
            cmd.append("--nmea_pcapng")
            nmea_arg = f"--nmea_out={prefix.with_suffix('.nmea')}"
            cmd.append(nmea_arg)
            self.logger.debug(f"GPS options enabled: --gpsd, --nmea_pcapng, {nmea_arg}")

        # if autobpf is enabled, run the helper and add --bpf
        if options.get("autobpf", False):
            bpf_file = self.config_dir / "filter.bpf"
            try:
                self.autobpf_helper(
                    scan_interface=self.selected_interface,
                    filter_path=bpf_file,
                    interfaces=self.interfaces,
                    extra_macs=self.extra_macs
                )
            except Exception as e:
                self.logger.error("Error building BPF filter in build_command: " + str(e))
            cmd.append(f"--bpf={bpf_file}")
            self.logger.debug(f"Using autobpf option; adding --bpf={bpf_file}")

        # 4. process remaining options
        # by skipping already handled keys
        for opt, val in options.items():
            if opt in ["autobpf", "--gpsd"]:
                continue
            if isinstance(val, bool):
                if val:
                    cmd.append(opt)
                    self.logger.debug(f"Added flag: {opt}")
            elif val is not None:
                cmd.append(f"{opt}={val}")
                self.logger.debug(f"Added option: {opt}={val}")

        # 5. process channel options if defined in the preset
        if "channel" in preset:
            channel_value = preset["channel"]
            if isinstance(channel_value, list):
                channel_str = ",".join(map(str, channel_value))
            else:
                channel_str = str(channel_value).strip()
                if " " in channel_str:
                    channel_str = ",".join(channel_str.split())
            cmd.extend(["-c", channel_str])
            self.logger.debug(f"Setting channel(s): {channel_str}")

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

            # Set pane title, {interface}_{description}; UI Manager creates.
            preset_description = self.preset_description
            pane_title = f"{self.selected_interface}_{preset_description}"
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







