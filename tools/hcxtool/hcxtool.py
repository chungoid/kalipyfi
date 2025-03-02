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
        Determine the scanning interface based on the available presets and global interface configuration.

        If the preset interface is set to "any", this function chooses the first available unlocked interface
        from self.interfaces (from the "wlan" category). Otherwise, it validates and returns the preset interface.

        Raises:
            ValueError: If no suitable interface is found.
        """
        preset_iface = self.presets.get("interface")
        if not preset_iface:
            raise ValueError("No interface specified in the scan settings.")

        # If the preset is "any", choose an unlocked interface.
        if preset_iface.lower() == "any":
            # interfaces from config.yaml as dict
            for category, iface_list in self.interfaces.items():
                for iface in iface_list:
                    iface_name = iface.get("name")
                    if iface_name:
                        # Ensure interface isn't marked as locked.
                        if not iface.get("locked", False):
                            # Additionally, ensure the interface exists on the system.
                            if os.path.isdir(f"/sys/class/net/{iface_name}"):
                                self.logger.info(f"Selected unlocked interface: {iface_name}")
                                return iface_name
            raise ValueError("No unlocked interface available.")
        else:
            # If a specific interface is provided, validate that it exists.
            if os.path.isdir(f"/sys/class/net/{preset_iface}"):
                return preset_iface
            else:
                raise ValueError(f"Interface '{preset_iface}' not found in /sys/class/net/")


    def build_command(self) -> list:
        """
        Builds the hcxdumptool command from the scan settings and options.
        Returns:
            list: The full command as a list of arguments.
        """
        cmd = ["hcxdumptool"]

        # 1. Determine the interface
        scan_interface = self.selected_interface
        cmd.extend(["-i", scan_interface])

        # 2. Determine the output prefix
        prefix = self.presets.get("output_prefix")
        if prefix:
            # If prefix is provided as a string, ensure it's absolute
            if not os.path.isabs(prefix):
                prefix = os.path.join(str(self.results_dir), prefix)
            # Ensure the directory exists
            dir_path = os.path.dirname(prefix)
            if not os.path.isdir(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    self.logger.error(f"Failed to create directory {dir_path}: {e}")
                    return []
            # Convert to a Path object for suffix operations
            prefix = Path(prefix)
        else:
            # Generate a default prefix and convert it to a Path
            prefix = self.results_dir / self.generate_default_prefix()
            self.presets["output_prefix"] = str(prefix)

        # 'prefix' is a Path object
        pcap_file = str(prefix.with_suffix('.pcapng'))
        cmd.extend(["-w", pcap_file])
        self.logger.debug(f"Setting pcapng filepath: {pcap_file}")

        # 3. GPS options
        if self.presets["options"].get("--gpsd", False):
            cmd.append("--gpsd")
            cmd.append("--nmea_pcapng")
            nmea_path = f"--nmea_out={prefix.with_suffix('.nmea')}"
            cmd.append(nmea_path)
            self.logger.debug(f"Setting NMEA filepath: {nmea_path}")

        # 4. Channel/frequency options
        if "channel" in self.presets:
            channel_value = self.presets["channel"]
            if isinstance(channel_value, list):
                channel_str = ",".join(str(ch) for ch in channel_value)
            else:
                channel_str = str(channel_value).strip()
                if " " in channel_str:
                    channel_str = ",".join(channel_str.split())
            cmd.extend(["-c", channel_str])

        # 5. BPF Filter Options
        if self.presets.get("autobpf", False):
            bpf_file = self.config_dir / "filter.bpf"
            self.logger.debug(f"Using auto-generated BPF filter: {bpf_file}")
            cmd.append(f"--bpf={bpf_file}")

        # 6. Merge and append additional options
        merged_options = self.defaults.copy()  # Already merged from YAML and defaults
        # Remove handled keys
        for key in ("-i", "-w", "--gpsd", "--nmea_out", "--nmea_pcapng", "-c", "--bpf"):
            merged_options.pop(key, None)

        for option, value in merged_options.items():
            norm_option = Tool.normalize_cmd_options(option)
            if isinstance(value, bool):
                if value:
                    cmd.append(norm_option)
            elif value is not None:
                cmd.append(f"{norm_option}={value}")

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



