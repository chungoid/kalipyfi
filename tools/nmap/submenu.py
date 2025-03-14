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

        The user is presented with a menu of items formatted as "iface: network". The interface
        is extracted from the left-hand side and the network (CIDR) from the right-hand side.

        :param parent_win: The parent window (curses window) used for drawing the menu.
        :return: True if a valid network and interface are selected, False otherwise.
        """
        networks = self.tool.get_target_networks()  # returns dict: interface -> network
        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No target networks available!")
            parent_win.refresh()
            parent_win.getch()
            return False

        # build a menu with CIDRs associated with available interfaces
        menu_items = [f"{iface}: {network}" for iface, network in networks.items()]
        selection = self.draw_paginated_menu(parent_win, "Select Target Network", menu_items)
        if selection == "back":
            return False
        try:
            iface, network = selection.split(":", 1)
            self.tool.selected_interface = iface.strip()
            self.tool.selected_network = network.strip()
            self.logger.debug("Selected target network: %s on interface: %s",
                              self.tool.selected_network, self.tool.selected_interface)
            self.tool.scan_mode = "cidr"
            return True
        except Exception as e:
            self.logger.error("Error parsing selected network: %s", e)
            return False

    def choose_gnmap_file(self, parent_win) -> Optional[Path]:
        """
        Presents a paginated menu for the user to choose a subdirectory (from self.tool.results_dir)
        that contains .gnmap files, then automatically selects the .gnmap file from that subdirectory.
        """
        # list subdirectories that contain .gnmap files
        subdirs = [d for d in self.tool.results_dir.iterdir() if d.is_dir() and list(d.glob("*.gnmap"))]
        if not subdirs:
            parent_win.clear()
            parent_win.addstr(0, 0, "No subdirectories with .gnmap files found in results directory! \n\n"
                                    "Note: Network Scans are required for host discovery before performing"
                                    " host-specific scans.")
            parent_win.refresh()
            parent_win.getch()
            return None

        # build menu options from subdirectory names
        subdir_options = [d.name for d in subdirs]
        chosen_subdir_name = self.draw_paginated_menu(parent_win, "Select CIDR Scan Subdirectory", subdir_options)
        if chosen_subdir_name == "back":
            parent_win.clear()
            parent_win.refresh()
            return None

        chosen_subdir = next((d for d in subdirs if d.name == chosen_subdir_name), None)
        if not chosen_subdir:
            parent_win.clear()
            parent_win.addstr(0, 0, "Selected subdirectory not found!")
            parent_win.refresh()
            parent_win.getch()
            return None

        # .gnmap files in the chosen subdirectory
        gnmap_files = list(chosen_subdir.glob("*.gnmap"))
        if not gnmap_files:
            return None

        # if exactly one file, select it automatically
        if len(gnmap_files) == 1:
            parent_win.clear()
            parent_win.refresh()
            return gnmap_files[0]
        else:
            # if multiple, let the user choose
            options = [f.name for f in gnmap_files]
            selection = self.draw_paginated_menu(parent_win, "Select GNMAP File", options)
            if selection == "back":
                parent_win.clear()
                parent_win.refresh()
                return None
            for f in gnmap_files:
                if f.name in selection:
                    parent_win.clear()
                    parent_win.refresh()
                    return f
            parent_win.clear()
            parent_win.refresh()
            return None

    def rescan_host_menu(self, parent_win) -> None:
        """
        Allows the user to choose a .gnmap file from the results directory,
        then parses that file to extract hosts, prompts for a preset,
        and finally launches a host-specific scan.
        """
        gnmap_file = self.choose_gnmap_file(parent_win)
        if not gnmap_file:
            return

        hosts = []
        try:
            with gnmap_file.open("r") as f:
                lines = f.readlines()
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
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error parsing {gnmap_file.name}: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        if not hosts:
            parent_win.clear()
            parent_win.addstr(0, 0, "No hosts found in the selected .gnmap file!")
            parent_win.refresh()
            parent_win.getch()
            return

        selection = self.draw_paginated_menu(parent_win, "Select Host for Rescan", hosts)
        if selection == "back":
            return

        try:
            selected_ip = selection.split()[0]
            self.tool.selected_target_host = selected_ip
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error processing selection: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        selected_preset = self.select_preset(parent_win)
        if selected_preset == "back" or not selected_preset:
            return

        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get("description", "")

        try:
            self.tool.scan_mode = "target"
            self.tool.run_target_from_results()
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching host scan: {e}")
            parent_win.refresh()
            parent_win.getch()

    def utils_menu(self, parent_win) -> None:
        menu_options = ["Open Results Webserver", "Create Scan Profile", "Edit Scan Profile"]
        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Create Scan Profile":
                self.create_preset_profile_menu(parent_win)
            elif selection == "Edit Scan Profile":
                self.edit_preset_profile_menu(parent_win)
            else:
                parent_win.clear()
                parent_win.refresh()
                return

    def __call__(self, stdscr) -> None:
        """
        Launches the Nmap submenu using curses.
        This version creates a debug window at the bottom of the entire screen.
        """
        curses.curs_set(0)

        # Reset state variables and reload configuration if needed.
        self.tool.selected_network = None
        self.tool.selected_target_host = None
        self.tool.selected_preset = None
        self.tool.scan_mode = None
        self.tool.parent_dir = None
        self.tool.reload_config()
        self.tool.target_networks = self.tool.get_target_networks()

        # Create the main submenu window
        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        # Define main menu options.
        menu_items = ["Network Scan", "Host Scan", "View Scans", "Utils", "Back"]
        numbered_menu = [f"[{i + 1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            # Draw the main menu in the submenu window.
            menu_win = self.draw_menu(submenu_win, f"{self.tool.name}", numbered_menu)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch == "1":
                self.launch_scan(submenu_win)
            elif ch == "2":
                self.rescan_host_menu(submenu_win)
            elif ch == "3":
                self.view_scans(submenu_win)
            elif ch == "4":
                self.utils_menu(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()



