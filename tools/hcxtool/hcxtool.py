import logging
import traceback
from abc import ABC
from pathlib import Path
from typing import Optional, Any, Dict


#locals
from tools.tools import Tool
from config.constants import BASE_DIR
from tools.helpers.tool_utils import update_yaml_value
from utils.tool_registry import register_tool
from database.db_manager import get_db_connection
from tools.hcxtool.db import init_hcxtool_schema
from tools.helpers.wpasec import get_wpasec_api_key as wpasec_get_api_key

@register_tool("hcxtool")
class Hcxtool(Tool, ABC):
    def __init__(self,
                 base_dir: Path, # hcxtool module base, not project base
                 config_file: Optional[str] = None,
                 interfaces: Optional[Any] = None,
                 presets: Optional[Dict[str, Any]] = None,
                 ui_instance: Optional[Any] = None) -> None:

        super().__init__(
            name="hcxtool",
            description="utilize hcxtool",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=presets,
            ui_instance=ui_instance
        )

        self.logger = logging.getLogger(self.name)

        from tools.hcxtool.submenu import HcxToolSubmenu
        self.submenu = HcxToolSubmenu(self)

        # hcxtool-specific database schema (tools/hcxtool/db.py)
        conn = get_db_connection(BASE_DIR)
        init_hcxtool_schema(conn)
        conn.close()

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
        # process the scan profile
        self.logger.debug("Building scan command.")
        try:
            cmd_list = self.build_command()
            if not cmd_list:
                self.logger.critical("Error: build_command() returned an empty command.")
                return

            # convert the command list into a structured dictionary
            cmd_dict = self.cmd_to_dict(cmd_list)
            self.logger.debug("Command dict built: %s", cmd_dict)

            # send command to the IPC server
            response = self.run_to_ipc(cmd_dict)
            if not (response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK")):
                self.logger.error("Scan failed to send to pane. Response: %s", response)
                return

        except Exception as e:
            self.logger.critical(f"Error launching scan: {e}")
            self.logger.debug(traceback.format_exc())
            return


        ######################
        ##### utilities  #####
        ######################
    def get_wpasec_api_key(self) -> str:
        return wpasec_get_api_key(self)


    def set_wpasec_key(self, new_key: str) -> None:
        """
        This wrapper method updates the configuration file (self.config_file) by modifying
        the value at the key path ["wpa-sec", "api_key"] using the generic YAML editor helper.

        Parameters
        ----------
        new_key : str
            The new WPA-sec API key to be set in the configuration.

        Returns
        -------
        None
        """
        key_path = ["wpa-sec", "api_key"]
        update_yaml_value(self.config_file, key_path, new_key)
        self.reload_config()

    def export_results(self) -> None:
        """
        Runs the export workflow: generate master results CSV from all pcapng files,
        update that CSV with keys from founds.txt (if found), and then create an HTML map.
        """
        from tools.hcxtool._parser import (
            run_hcxpcapngtool,
            parse_temp_csv,
            append_keys_to_master,
            create_html_map
        )
        results_csv = self.results_dir / "results.csv"
        founds_txt = self.results_dir / "founds.txt"

        # check for caps
        pcapng_files = list(self.results_dir.glob("*.pcapng"))
        if not pcapng_files:
            self.logger.info("No pcapng files found in the results directory.")
            return

        # parse tmp csv
        try:
            temp_csv = run_hcxpcapngtool(self.results_dir)
            master_csv = parse_temp_csv(temp_csv)
            self.logger.info("Master results.csv has been updated from pcapng files.")
        except Exception as e:
            self.logger.error(f"Error while generating results.csv: {e}")
            return

        # append keys from founds.txt, if it exists
        if founds_txt.exists():
            try:
                append_keys_to_master(master_csv, founds_txt)
                self.logger.info("Results CSV updated with keys from founds.txt.")
            except Exception as e:
                self.logger.error(f"Error while appending keys: {e}")
        else:
            self.logger.info("founds.txt not found; skipping key appending step.")

        # create an HTML map from the updated results.csv
        try:
            create_html_map(master_csv)
            self.logger.info("HTML map created from results.csv.")
        except Exception as e:
            self.logger.error(f"Error while creating HTML map: {e}")



