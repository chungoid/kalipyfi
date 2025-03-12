# tools/nmap/submenu.py
import curses
import logging
from pathlib import Path
from typing import Optional

# locals
from tools.submenu import BaseSubmenu

class NmapSubmenu(BaseSubmenu):
    def __init__(self, tool_instance):
        super().__init__(tool_instance)
        self.logger = logging.getLogger("NmapSubmenu")
        self.logger.debug("NmapSubmenu initialized.")

    def pre_launch_hook(self, parent_win) -> bool:
        """
        For Nmap, prompt the user to select a target network (CIDR) before launching the scan.
        """
        networks = self.tool.get_target_networks()  # returns dict: interface -> network
        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No target networks available!")
            parent_win.refresh()
            parent_win.getch()
            return False

        # build a menu with CIDR's associated with available interfaces
        menu_items = [f"{iface}: {network}" for iface, network in networks.items()]
        selection = self.draw_paginated_menu(parent_win, "Select Target Network", menu_items)
        if selection == "back":
            return False
        try:
            _, network = selection.split(":", 1)
            self.tool.selected_network = network.strip()
            self.logger.debug("Selected target network: %s", self.tool.selected_network)
            return True
        except Exception as e:
            self.logger.error("Error parsing selected network: %s", e)
            return False

    def choose_gnmap_file(self, parent_win) -> Optional[Path]:
        """
        Presents a paginated menu for the user to choose a subdirectory (from self.tool.results_dir)
        that contains .gnmap files, then automatically selects the .gnmap file from that subdirectory.
        Extensive debug logging is added to trace the execution.
        """
        # Log the results directory absolute path.
        self.logger.debug("Results directory: %s", self.tool.results_dir.resolve())

        # list subdirectories in results (all CIDR scans get unique subdirs, and hosts get subdirs within CIDR subdir)
        subdirs = [d for d in self.tool.results_dir.iterdir() if d.is_dir() and list(d.glob("*.gnmap"))]
        self.logger.debug("Found subdirectories with .gnmap files: %s", [d.name for d in subdirs])
        if not subdirs:
            parent_win.clear()
            parent_win.addstr(0, 0, "No subdirectories with .gnmap files found in results directory!")
            parent_win.refresh()
            parent_win.getch()
            self.logger.debug("No subdirectories found; returning None.")
            return None

        # build menu options from subdirectory names
        subdir_options = [d.name for d in subdirs]
        self.logger.debug("Subdirectory options for menu: %s", subdir_options)
        chosen_subdir_name = self.draw_paginated_menu(parent_win, "Select CIDR Scan Subdirectory", subdir_options)
        self.logger.debug("User selected subdirectory option: %s", chosen_subdir_name)
        if chosen_subdir_name == "back":
            self.logger.debug("User cancelled subdirectory selection.")
            return None

        # find the chosen subdirectory object
        chosen_subdir = next((d for d in subdirs if d.name == chosen_subdir_name), None)
        if not chosen_subdir:
            parent_win.clear()
            parent_win.addstr(0, 0, "Selected subdirectory not found!")
            parent_win.refresh()
            parent_win.getch()
            self.logger.debug("Chosen subdirectory not found; returning None.")
            return None
        self.logger.debug("Chosen subdirectory: %s", chosen_subdir.resolve())

        # list .gnmap files in the chosen subdir
        gnmap_files = list(chosen_subdir.glob("*.gnmap"))
        self.logger.debug("Found .gnmap files in '%s': %s", chosen_subdir.name, [f.name for f in gnmap_files])
        if not gnmap_files:
            parent_win.clear()
            parent_win.addstr(0, 0, "No .gnmap files found in the selected subdirectory!")
            parent_win.refresh()
            parent_win.getch()
            self.logger.debug("No .gnmap files in chosen subdirectory; returning None.")
            return None

        if len(gnmap_files) == 1:
            self.logger.debug("Only one .gnmap file found: %s", gnmap_files[0].name)
            return gnmap_files[0]
        else:
            # if there's multiple, user chooses specific
            options = [f"{f.name}" for f in gnmap_files]
            self.logger.debug("Multiple .gnmap files found. Options: %s", options)
            selection = self.draw_paginated_menu(parent_win, "Select GNMAP File", options)
            self.logger.debug("User selected GNMAP file option: %s", selection)
            if selection == "back":
                self.logger.debug("User cancelled GNMAP file selection.")
                return None
            for f in gnmap_files:
                if f.name in selection:
                    self.logger.debug("Returning selected file: %s", f.resolve())
                    return f
            self.logger.debug("No matching file found in selection; returning None.")
            return None

    def rescan_host_menu(self, parent_win) -> None:
        """
        Allows the user to choose a .gnmap file from the results directory,
        then parses that file to extract hosts, prompts for a preset,
        and finally launches a host-specific scan.
        Extensive debugging logs are included.
        """
        self.logger.debug("Entered rescan_host_menu()")

        # choose a CIDR scan .gnmap file.
        gnmap_file = self.choose_gnmap_file(parent_win)
        if not gnmap_file:
            self.logger.debug("No gnmap file selected; exiting rescan_host_menu()")
            return
        self.logger.debug("Chosen gnmap file: %s", gnmap_file.resolve())

        # parse the chosen file to extract hosts
        hosts = []
        try:
            with gnmap_file.open("r") as f:
                lines = f.readlines()
            self.logger.debug("Read %d lines from %s", len(lines), gnmap_file.name)
            for line in lines:
                if line.startswith("Host:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1]
                        hostname = ""
                        if len(parts) >= 3 and parts[2].startswith("(") and parts[2].endswith(")"):
                            hostname = parts[2][1:-1]
                        entry = f"{ip} ({hostname})" if hostname else ip
                        if entry not in hosts:
                            hosts.append(entry)
                            self.logger.debug("Added host entry: %s", entry)
        except Exception as e:
            self.logger.error("Exception parsing %s: %s", gnmap_file.name, e)
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error parsing {gnmap_file.name}: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        if not hosts:
            self.logger.debug("No hosts found in %s", gnmap_file.name)
            parent_win.clear()
            parent_win.addstr(0, 0, "No hosts found in the selected .gnmap file!")
            parent_win.refresh()
            parent_win.getch()
            return

        self.logger.debug("Parsed hosts: %s", hosts)

        # let the user choose a host from the parsed list
        selection = self.draw_paginated_menu(parent_win, "Select Host for Rescan", hosts)
        self.logger.debug("User selected host option: %s", selection)
        if selection == "back":
            self.logger.debug("User cancelled host selection.")
            return

        # extract the IP address
        try:
            selected_ip = selection.split()[0]
            self.tool.selected_target_host = selected_ip
            self.logger.debug("Extracted target host IP: %s", selected_ip)
        except Exception as e:
            self.logger.error("Error extracting IP from selection '%s': %s", selection, e)
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error processing selection: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        # prompt for a scan preset using configs/config.yaml preset key options
        selected_preset = self.select_preset(parent_win)
        self.logger.debug("User selected preset: %s", selected_preset)
        if selected_preset == "back":
            self.logger.debug("User cancelled preset selection.")
            return
        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get("description", "")
        self.logger.debug("Set tool.selected_preset and preset_description: %s", self.tool.preset_description)

        # launch the scan for the selected host
        try:
            self.tool.scan_mode = "target"
            self.logger.debug("Set scan_mode to 'target', now launching host scan.")
            self.tool.run_target_from_results()
        except Exception as e:
            self.logger.error("Exception during run_target_from_results: %s", e)
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching host scan: {e}")
            parent_win.refresh()
            parent_win.getch()

    def utils_menu(self, parent_win) -> None:
        menu_options = ["Open Results Webserver", "Rescan Specific Host", "Other utilities..."]
        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Scan Host from Results":
                self.rescan_host_menu(parent_win)
            elif selection == "Other utilities...":
                parent_win.clear()
                parent_win.addstr(0, 0, "No other utilities available. Press any key to return.")
                parent_win.refresh()
                parent_win.getch()
            parent_win.clear()
            parent_win.refresh()

    def __call__(self, stdscr) -> None:
        """
        Launches the Nmap submenu using curses. Before showing the menu,
        it resets key state variables and reloads the configuration so that any
        updates made to the config are applied.
        """
        curses.curs_set(0)

        # reset state variables to ensure a clean start
        self.tool.selected_network = None
        self.tool.selected_target_host = None
        self.tool.selected_preset = None
        self.tool.scan_mode = None
        self.tool.parent_dir = None

        # reload available configurations (presets, interfaces, defaults)
        self.tool.reload_config()

        # get updated target networks in case interfaces have changed
        self.tool.target_networks = self.tool.get_target_networks()

        # create the submenu window
        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        # define main menu options
        menu_items = ["Launch Scan", "View Scans", "Utils"]
        numbered_menu = [f"[{i + 1}] {item}" for i, item in enumerate(menu_items)]
        numbered_menu.append("[0] Back")

        while True:
            menu_win = self.draw_menu(submenu_win, f"{self.tool.name} Submenu", numbered_menu)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch == "1":
                self.launch_scan(submenu_win)
            elif ch == "2":
                self.view_scans(submenu_win)
            elif ch == "3":
                self.utils_menu(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()


