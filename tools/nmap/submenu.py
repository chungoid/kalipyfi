# tools/nmap/submenu.py
import curses
import logging
import json
from pathlib import Path
from typing import Optional

# locals
from tools.submenu import BaseSubmenu
from tools.helpers.tool_utils import get_network_from_interface
from database.db_manager import get_db_connection
from config.constants import BASE_DIR


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

        :param parent_win: (curses window): The window used for displaying the menu.
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

        :param parent_win: (curses window): The window used for displaying the menu.
        :return: Path to the .gnmap file, or None if no file was selected.
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

    def db_network_scan_menu(self, parent_win) -> None:
        """
        Allows the user to select a target network from available interfaces,
        then initiates a network scan (-sn) to discover hosts and import the results
        into the database.

        Workflow:
          1. Retrieve available networks from interfaces.
          2. Present a menu of "interface: network" options.
          3. Upon selection, set the selected interface and network.
          4. Set a preset for a network scan (e.g. using -sn).
          5. Build the nmap command and run it via IPC.
          6. Show a brief message (2.5 sec) before returning to the menu.

        :param parent_win: (curses window): The window used for displaying the menu.

        Returns:
            None
        """
        # retrieve available networks
        networks = self.tool.get_target_networks()  # dict: interface -> network (CIDR)
        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No target networks available!")
            parent_win.refresh()
            parent_win.getch()
            return

        # build a menu of available networks using interface and network
        menu_items = [f"{iface}: {network}" for iface, network in networks.items()]
        selection = self.draw_paginated_menu(parent_win, "Select Target Network", menu_items)
        if selection == "back":
            return

        # parse the selection and set interface/network in the tool instance
        try:
            iface, network = selection.split(":", 1)
            self.tool.selected_interface = iface.strip()
            self.tool.selected_network = network.strip()
            self.logger.debug("Selected target network: %s on interface: %s",
                              self.tool.selected_network, self.tool.selected_interface)
            self.tool.scan_mode = "cidr"
        except Exception as e:
            self.logger.error("Error parsing selected network: %s", e)
            return

        # set preset for a network scan
        selected_preset = {
            "description": "db_network",
            "options": {
                "-sn": True,
                "-T4": True
            }
        }
        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get("description", "")

        # build the nmap command for the selected network and run via IPC
        cmd_list = self.tool.build_nmap_command(self.tool.selected_network)
        cmd_dict = self.tool.cmd_to_dict(cmd_list)

        parent_win.clear()
        parent_win.addstr(0, 0, f"Initiating network scan for: {self.tool.selected_network}")
        parent_win.refresh()

        response = self.tool.run_to_ipc(cmd_dict)
        if response and isinstance(response, dict) and response.get("status", "").startswith("SEND_SCAN_OK"):
            self.logger.info("Network scan initiated successfully: %s", response)
            parent_win.addstr(1, 0, "Scan sent. Processing results...")
        else:
            self.logger.error("Error initiating network scan via IPC: %s", response)
            parent_win.addstr(1, 0, f"Error initiating scan: {response}")
        parent_win.refresh()

        curses.napms(2500)

    def db_host_scan_menu(self, parent_win) -> None:
        """
        Presents a menu that lets the user select a network scan from the database,
        then displays the hosts stored in the selected network's JSON blob. The user
        can then choose a host for a detailed (-A) scan, or select "ALL" to scan every host.
        This implementation uses nested loops so that if the user selects "back" in the host
        selection menu, they are returned to the network selection menu rather than the main tool menu.
        """
        from tools.nmap.db import fetch_all_nmap_network_results
        from config.constants import BASE_DIR
        import json

        # query the database for network scan records
        conn = get_db_connection(BASE_DIR)
        networks = fetch_all_nmap_network_results(conn)
        conn.close()

        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No network scans found in the database!")
            parent_win.refresh()
            parent_win.getch()
            return

        # sort networks by created_at (most recent first)
        networks_sorted = sorted(networks, key=lambda x: x[7], reverse=True)

        # build a menu of networks
        network_menu = []
        for net in networks_sorted:
            router_ip = net[4] if net[4] else "Unknown"
            router_hostname = net[5] if net[5] else ""
            created_at = net[7]
            menu_str = f"Router: {router_ip} ({router_hostname}) - {created_at}"
            network_menu.append(menu_str)

        # outer loop: network selection
        while True:
            parent_win.clear()
            parent_win.refresh()
            selected_network_str = self.draw_paginated_menu(parent_win, "Select Network", network_menu)
            if selected_network_str == "back":
                return  # exit db_host_scan_menu entirely
            try:
                idx = network_menu.index(selected_network_str)
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error processing network selection: {e}")
                parent_win.refresh()
                parent_win.getch()
                continue

            selected_network_record = networks_sorted[idx]
            self.tool.current_network_id = selected_network_record[0]

            # extract and decode the hosts JSON blob
            hosts_json = selected_network_record[6]
            try:
                hosts_list = json.loads(hosts_json)
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error parsing hosts JSON: {e}")
                parent_win.refresh()
                parent_win.getch()
                continue

            if not hosts_list:
                parent_win.clear()
                parent_win.addstr(0, 0, "No hosts found in the selected network scan!")
                parent_win.refresh()
                parent_win.getch()
                continue

            # inner loop: host selection for the chosen network
            while True:
                parent_win.clear()
                parent_win.refresh()
                host_menu = ["ALL"]
                for host in hosts_list:
                    ip = host.get("ip", "")
                    hostname = host.get("hostname", "")
                    entry = f"{ip} ({hostname})" if hostname else ip
                    host_menu.append(entry)

                selected_host = self.draw_paginated_menu(parent_win, "Select Host for Port & Service Scan", host_menu)
                if selected_host == "back":
                    # go back to the network selection menu
                    break

                # set common preset for host scans
                selected_preset = {
                    "description": "db_host",
                    "options": {
                        "-A": True,
                        "--top-ports": 1000,
                        "-T4": True
                    }
                }
                self.tool.selected_preset = selected_preset
                self.tool.preset_description = selected_preset.get("description", "")
                self.tool.scan_mode = "target"

                if selected_host.upper() == "ALL":
                    all_ips = [host.get("ip", "") for host in hosts_list if host.get("ip", "")]
                    combined_ips = " ".join(all_ips)
                    self.tool.selected_target_host = combined_ips
                    try:
                        self.tool.run_db_hosts(combined_ips)
                        parent_win.clear()
                        parent_win.addstr(0, 0,
                                          "Scan sent for all hosts.\nSelect 'View Scans' from menu to swap scan into view.")
                        parent_win.refresh()
                        curses.napms(2500)
                        return  # sent scan; exit the menu
                    except Exception as e:
                        parent_win.clear()
                        parent_win.addstr(0, 0, f"Error launching host scan: {e}")
                        parent_win.refresh()
                        parent_win.getch()
                        # optionally, break or continue to allow re-selection.
                        break
                else:
                    try:
                        selected_ip = selected_host.split()[0]
                    except Exception as e:
                        parent_win.clear()
                        parent_win.addstr(0, 0, f"Error processing host selection: {e}")
                        parent_win.refresh()
                        parent_win.getch()
                        continue

                    self.tool.selected_target_host = selected_ip
                    try:
                        self.tool.run_db_hosts(selected_ip)
                        parent_win.clear()
                        parent_win.addstr(0, 0,
                                          f"Scan sent for: {selected_ip}\nSelect 'View Scans' from menu to swap scan into view.")
                        parent_win.refresh()
                        curses.napms(2500)
                        return  # sent scan; exit the submenu.
                    except Exception as e:
                        parent_win.clear()
                        parent_win.addstr(0, 0, f"Error launching host scan: {e}")
                        parent_win.refresh()
                        parent_win.getch()
                        break  # break to re-show the network menu.

    #################################
    ##### UTILS SUBMENU METHODS #####
    #################################
    def get_utils_menu_options(self) -> list:
        """
        Returns a list of utility menu options for Nmap.

        Extends the base utilities options by adding an Nmap-specific option.

        :return: A list of strings representing the menu options.
        """
        base_options = super().get_utils_menu_options()

        # will uncomment and use in future if more options added
        # return ["Edit Nmap Options"] + base_options
        return base_options

    def edit_nmap_options_menu(self, parent_win) -> None:
        """
        Presents a menu for editing Nmap-specific configuration options.

        (Implement prompts as needed; here it is a placeholder.)

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
        parent_win.clear()
        parent_win.addstr(0, 0, "Editing Nmap Options not yet implemented.")
        parent_win.addstr(1, 0, "Press any key to continue...")
        parent_win.refresh()
        parent_win.getch()

    def utils_menu(self, parent_win) -> None:
        """
        Presents menu options by overriding get_utils_menu_options() from the
        base class & adding nmap specific options in nmap submenu's override method.

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
        super().utils_menu(parent_win)

    def __call__(self, stdscr) -> None:
        """
        Launches the Nmap submenu using curses.
        Main options include:
          - Network Scan
          - Host Scan
          - View Scans
          - Utils
          - (Plus the dynamic "Toggle Scrolling" option inserted by the base helper)
          - Back
        """
        curses.curs_set(0)
        # Reset state variables and reload configuration.
        self.tool.selected_network = None
        self.tool.selected_target_host = None
        self.tool.selected_preset = None
        self.tool.scan_mode = None
        self.tool.parent_dir = None
        self.tool.reload_config()
        self.tool.target_networks = self.tool.get_target_networks()

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        base_menu = ["Network Scan", "Host Scan", "View Scans", "Utils"]
        while True:
            selection = self.show_main_menu(submenu_win, base_menu, f"{self.tool.name}")
            if selection.lower() == "back":
                break
            elif selection == "Network Scan":
                self.db_network_scan_menu(submenu_win)
            elif selection == "Host Scan":
                self.db_host_scan_menu(submenu_win)
            elif selection == "View Scans":
                self.view_scans(submenu_win)
            elif selection == "Utils":
                self.utils_menu(submenu_win)
            submenu_win.clear()
            submenu_win.refresh()




