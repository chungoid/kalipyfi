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
        Debug information is printed directly to parent_win.
        """
        debug_lines = []  # Collect debug messages to display
        debug_lines.append("DEBUG: Starting choose_gnmap_file()")

        # Log the results directory absolute path.
        results_dir = self.tool.results_dir.resolve()
        debug_lines.append(f"Results directory: {results_dir}")

        # List subdirectories that contain .gnmap files.
        subdirs = [d for d in self.tool.results_dir.iterdir() if d.is_dir() and list(d.glob("*.gnmap"))]
        debug_lines.append(f"Found subdirectories: {[d.name for d in subdirs]}")
        if not subdirs:
            parent_win.clear()
            parent_win.addstr(0, 0, "No subdirectories with .gnmap files found in results directory!")
            for i, line in enumerate(debug_lines, start=1):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return None

        # Build menu options from subdirectory names.
        subdir_options = [d.name for d in subdirs]
        debug_lines.append(f"Subdirectory options: {subdir_options}")
        chosen_subdir_name = self.draw_paginated_menu(parent_win, "Select CIDR Scan Subdirectory", subdir_options)
        debug_lines.append(f"User selected subdirectory option: {chosen_subdir_name}")
        if chosen_subdir_name == "back":
            debug_lines.append("User cancelled subdirectory selection.")
            parent_win.clear()
            for i, line in enumerate(debug_lines):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return None

        chosen_subdir = next((d for d in subdirs if d.name == chosen_subdir_name), None)
        if not chosen_subdir:
            parent_win.clear()
            parent_win.addstr(0, 0, "Selected subdirectory not found!")
            for i, line in enumerate(debug_lines, start=1):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return None
        debug_lines.append(f"Chosen subdirectory: {chosen_subdir.resolve()}")

        # List .gnmap files in the chosen subdirectory.
        gnmap_files = list(chosen_subdir.glob("*.gnmap"))
        debug_lines.append(f"Found .gnmap files: {[f.name for f in gnmap_files]}")
        if not gnmap_files:
            parent_win.clear()
            parent_win.addstr(0, 0, "No .gnmap files found in the selected subdirectory!")
            for i, line in enumerate(debug_lines, start=1):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return None

        # If exactly one file, select it automatically.
        if len(gnmap_files) == 1:
            debug_lines.append(f"Only one .gnmap file found: {gnmap_files[0].name}")
            parent_win.clear()
            for i, line in enumerate(debug_lines):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return gnmap_files[0]
        else:
            # If multiple, let the user choose.
            options = [f"{f.name}" for f in gnmap_files]
            debug_lines.append(f"Multiple .gnmap files found, options: {options}")
            selection = self.draw_paginated_menu(parent_win, "Select GNMAP File", options)
            debug_lines.append(f"User selected GNMAP file option: {selection}")
            if selection == "back":
                debug_lines.append("User cancelled GNMAP file selection.")
                parent_win.clear()
                for i, line in enumerate(debug_lines):
                    parent_win.addstr(i, 0, line)
                parent_win.refresh()
                parent_win.getch()
                return None
            for f in gnmap_files:
                if f.name in selection:
                    debug_lines.append(f"Returning selected file: {f.resolve()}")
                    parent_win.clear()
                    for i, line in enumerate(debug_lines):
                        parent_win.addstr(i, 0, line)
                    parent_win.refresh()
                    parent_win.getch()
                    return f
            debug_lines.append("No matching file found in selection; returning None.")
            parent_win.clear()
            for i, line in enumerate(debug_lines):
                parent_win.addstr(i, 0, line)
            parent_win.refresh()
            parent_win.getch()
            return None

    def rescan_host_menu(self, parent_win) -> None:
        #debug_lines = []
        #debug_lines.append("DEBUG: Entered rescan_host_menu()")
        #self.show_debug_info(debug_lines)

        # Create the debug window once (reserve the bottom 4 lines)
        #self.debug_win = self.create_debug_window(parent_win, height=4)
        #self.show_debug_info(debug_lines)

        # Choose a .gnmap file.
        gnmap_file = self.choose_gnmap_file(parent_win)
        if not gnmap_file:
            #debug_lines.append("DEBUG: No gnmap file selected; exiting rescan_host_menu()")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return
        #debug_lines.append(f"DEBUG: Chosen gnmap file: {gnmap_file.resolve()}")
        #self.show_debug_info(debug_lines)

        # Parse the chosen file...
        hosts = []
        try:
            with gnmap_file.open("r") as f:
                lines = f.readlines()
            #debug_lines.append(f"DEBUG: Read {len(lines)} lines from {gnmap_file.name}")
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
                            #debug_lines.append(f"DEBUG: Added host entry: {entry}")
                            #self.show_debug_info(debug_lines)
        except Exception as e:
            #debug_lines.append(f"ERROR: Exception parsing {gnmap_file.name}: {e}")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return

        if not hosts:
            #debug_lines.append(f"DEBUG: No hosts found in {gnmap_file.name}")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return

        #debug_lines.append(f"DEBUG: Parsed hosts: {hosts}")
        #self.show_debug_info(debug_lines)

        # Let the user choose a host.
        selection = self.draw_paginated_menu(parent_win, "Select Host for Rescan", hosts)
        #debug_lines.append(f"DEBUG: User selected host option: {selection}")
        #self.show_debug_info(debug_lines)
        if selection == "back":
            #debug_lines.append("DEBUG: User cancelled host selection.")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return

        try:
            selected_ip = selection.split()[0]
            self.tool.selected_target_host = selected_ip
            #debug_lines.append(f"DEBUG: Extracted target host IP: {selected_ip}")
            #self.show_debug_info(debug_lines)
        except Exception as e:
            #debug_lines.append(f"ERROR: Error extracting IP from selection '{selection}': {e}")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return

        # Prompt for a preset.
        selected_preset = self.select_preset(parent_win)
        #debug_lines.append(f"DEBUG: User selected preset: {selected_preset}")
        #self.show_debug_info(debug_lines)
        if selected_preset == "back" or not selected_preset:
            #debug_lines.append("DEBUG: User cancelled preset selection.")
            #self.show_debug_info(debug_lines)
            parent_win.getch()
            return

        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get("description", "")
        #debug_lines.append(f"DEBUG: Set preset description: {self.tool.preset_description}")
        #self.show_debug_info(debug_lines)

        # Launch the scan.
        try:
            self.tool.scan_mode = "target"
            #debug_lines.append("DEBUG: Set scan_mode to 'target'. Launching host scan...")
            #self.show_debug_info(debug_lines)
            parent_win.getch()  # Pause so the user can see the debug info.
            self.tool.run_target_from_results()
        except Exception as e:
            #debug_lines.append(f"ERROR: Exception during run_target_from_results: {e}")
            #self.show_debug_info(debug_lines)
            parent_win.getch()

    def utils_menu(self, parent_win) -> None:
        menu_options = ["Open Results Webserver", "Scan Specific Host", "Other utilities..."]
        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Scan Specific Host":
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
        Launches the Nmap submenu using curses.
        This version creates a debug window at the bottom of the entire screen.
        """
        import curses
        curses.curs_set(0)

        # Reset state variables and reload configuration if needed.
        self.tool.selected_network = None
        self.tool.selected_target_host = None
        self.tool.selected_preset = None
        self.tool.scan_mode = None
        self.tool.parent_dir = None
        self.tool.reload_config()
        self.tool.target_networks = self.tool.get_target_networks()

        # Create the debug window using the entire stdscr.
        self.debug_win = self.create_debug_window(stdscr, height=4)

        # Create the main submenu window (covering entire stdscr except the debug window area)
        max_y, max_x = stdscr.getmaxyx()
        menu_height = max_y - 4  # reserve bottom 4 lines for debugging
        submenu_win = stdscr.derwin(menu_height, max_x, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        # Define main menu options.
        menu_items = ["Launch Scan", "View Scans", "Utils", "Back"]
        numbered_menu = [f"[{i + 1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            # Draw the main menu in the submenu window.
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



