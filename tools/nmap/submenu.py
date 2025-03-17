# tools/nmap/submenu.py
import curses
import logging
from pathlib import Path
from typing import Optional

from tools.helpers.tool_utils import get_network_from_interface
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
        menu_items = [f"{iface}: {gateway}" for iface, gateway in self.tool.gateways.items()]
        selection = self.draw_paginated_menu(parent_win, "Select Target Network", menu_items)
        if selection == "back":
            return False
        try:
            iface, gateway = selection.split(":", 1)
            self.tool.selected_interface = iface.strip()
            self.tool.selected_network = get_network_from_interface(self.tool.selected_interface)
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

    def db_host_scan_menu(self, parent_win) -> None:
        """
        Presents a menu that lets the user select a network scan from the database,
        then displays the hosts stored in the selected network's JSON blob. The user
        can then choose a host for a detailed (-A) scan.

        Workflow:
          1. Query the nmap_network table for available network scan records.
          2. Sort the records by the created_at timestamp (most recent first).
          3. Display a paginated menu of networks showing: "Router: <ip> (<hostname>) - <timestamp>".
          4. When a network is selected, retrieve its hosts JSON blob and decode it.
          5. Display a paginated menu of hosts.
          6. When a host is selected, set the tool's selected_target_host and current_network_id,
             then launch the host scan.

        Parameters:
            parent_win (curses window): The parent window used for drawing the menus.

        Returns:
            None
        """
        import json
        from database.db_manager import get_db_connection
        from tools.nmap.db import fetch_all_nmap_network_results
        from config.constants import BASE_DIR

        # Query the database for network scan records.
        conn = get_db_connection(BASE_DIR)
        networks = fetch_all_nmap_network_results(conn)
        conn.close()

        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No network scans found in the database!")
            parent_win.refresh()
            parent_win.getch()
            return

        # Sort networks by created_at (most recent first)
        # Assuming the created_at field is at index 7.
        networks_sorted = sorted(networks, key=lambda x: x[7], reverse=True)

        # Build a menu of networks without showing the ID.
        network_menu = []
        for net in networks_sorted:
            router_ip = net[4] if net[4] else "Unknown"
            router_hostname = net[5] if net[5] else ""
            created_at = net[7]
            # Format the timestamp (if needed, you could parse and reformat it)
            menu_str = f"Router: {router_ip} ({router_hostname}) - {created_at}"
            network_menu.append(menu_str)

        # Let the user choose a network.
        selected_network_str = self.draw_paginated_menu(parent_win, "Select Network", network_menu)
        if selected_network_str == "back":
            return

        try:
            # Find the index of the selected option.
            idx = network_menu.index(selected_network_str)
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error processing network selection: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        # Retrieve the corresponding network record.
        selected_network_record = networks_sorted[idx]
        # Save the chosen network ID for later use.
        self.tool.current_network_id = selected_network_record[0]

        # Extract the hosts JSON blob from the selected network record.
        hosts_json = selected_network_record[6]  # Assuming hosts is stored in column index 6.
        try:
            hosts_list = json.loads(hosts_json)
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error parsing hosts JSON: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        if not hosts_list:
            parent_win.clear()
            parent_win.addstr(0, 0, "No hosts found in the selected network scan!")
            parent_win.refresh()
            parent_win.getch()
            return

        # Build a menu list of hosts.
        host_menu = []
        for host in hosts_list:
            ip = host.get("ip", "")
            hostname = host.get("hostname", "")
            entry = f"{ip} ({hostname})" if hostname else ip
            host_menu.append(entry)

        selected_host = self.draw_paginated_menu(parent_win, "Select Host for Port & Service Scan", host_menu)
        if selected_host == "back":
            return

        try:
            selected_ip = selected_host.split()[0]
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error processing host selection: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        # set the target host
        self.tool.selected_target_host = selected_ip

        selected_preset = {
            "description": "db_host",
            "options": {
                "-A": True,
                "--top-ports": 1000,
                "-T4": True
            } }

        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get("description", "")

        try:
            self.tool.scan_mode = "target"
            # Launch the host scan for the selected host.
            self.tool.run_db_hosts(self.tool.selected_target_host)
            parent_win.clear()
            parent_win.addstr(0, 0, f"Scan sent for: {self.tool.selected_target_host} /n"
                                    f"/n Select View Scans from menu to swap scan into view.")
            parent_win.refresh()
            # Pause for 2.5 seconds (2500 ms)
            curses.napms(2500)
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
                self.db_host_scan_menu(submenu_win)
            elif ch == "3":
                self.view_scans(submenu_win)
            elif ch == "4":
                self.utils_menu(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()



