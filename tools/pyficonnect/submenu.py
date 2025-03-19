import curses
import logging
from typing import List, Tuple, Any

# local
from tools.submenu import BaseSubmenu


class PyfyConnectSubmenu(BaseSubmenu):
    def __init__(self, tool_instance):
        """
        Initialize the submenu for NetConnectTool.
        """
        super().__init__(tool_instance)
        self.logger = logging.getLogger("NetConnectToolSubmenu")
        self.logger.debug("NetConnectToolSubmenu initialized.")

    def scan_networks(self) -> List[Tuple[str, str]]:
        """
        Scans for available networks using nmcli on the currently selected interface.
        Returns a list of tuples in the form (SSID, SECURITY).
        """
        from tools.helpers.tool_utils import get_wifi_networks
        if not self.tool.selected_interface:
            self.logger.error("No interface selected for scanning networks.")
            return []
        return get_wifi_networks(self.tool.selected_interface, self.logger)

    def select_connected_interface(self, parent_win) -> any:
        """
        Presents a paginated menu of currently connected interfaces.
        """
        from tools.helpers.tool_utils import get_all_connected_interfaces
        while True:
            connected = get_all_connected_interfaces(self.logger)
            if not connected:
                parent_win.clear()
                parent_win.addstr(0, 0, "No connected interfaces found!")
                parent_win.refresh()
                parent_win.getch()
                return None
            selection = self.draw_paginated_menu(parent_win, "Select Connected Interface", connected)
            if selection == "back":
                return None
            else:
                return selection

    def select_network(self, parent_win) -> Tuple[Any, Any]:
        """
        Uses scan_networks to get available networks, then presents them for selection.
        Returns a tuple (SSID, SECURITY) or (None, None) if cancelled.
        """
        networks = self.scan_networks()
        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No WiFi networks found!")
            parent_win.refresh()
            parent_win.getch()
            return (None, None)
        menu_items = []
        for ssid, security in networks:
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            menu_items.append(f"{ssid}{sec_str}")
        selection = self.draw_paginated_menu(parent_win, "Available Networks", menu_items)
        if selection == "back":
            return (None, None)
        chosen_ssid = None
        chosen_security = None
        for ssid, security in networks:
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            if f"{ssid}{sec_str}" == selection:
                chosen_ssid = ssid
                chosen_security = security
                break
        return (chosen_ssid, chosen_security)

    def prompt_for_password(self, parent_win, security: str) -> str:
        """
        Prompts for a password if the network is secured.
        """
        if not security or security == "--":
            return ""
        parent_win.clear()
        parent_win.addstr(0, 0, "Enter password for secured network:")
        parent_win.refresh()
        curses.echo()
        try:
            pwd = parent_win.getstr(1, 0).decode("utf-8").strip()
        except Exception:
            pwd = ""
        curses.noecho()
        return pwd

    def launch_connect(self, parent_win) -> None:
        """
        Standard connection process:
          1. Reset selections.
          2. Select interface.
          3. Check interface mode; if not managed, prompt to switch.
          4. Scan for networks.
          5. Prompt for password if needed.
          6. Launch connection via self.tool.run().
        Uses a nested loop so that if an error occurs, the user can retry.
        """
        from tools.helpers.tool_utils import get_interface_mode, switch_interface_to_managed, get_wifi_networks
        while True:
            # Reset previous selections
            self.tool.selected_interface = None
            self.tool.selected_network = None
            self.tool.network_password = None

            selected_iface = self.select_interface(parent_win)
            if not selected_iface:
                self.logger.debug("No interface selected; aborting connection.")
                return
            self.tool.selected_interface = selected_iface

            # Check current interface mode.
            current_mode = get_interface_mode(selected_iface, self.logger)
            if current_mode != "managed":
                parent_win.clear()
                parent_win.addstr(0, 0, f"Interface {selected_iface} is in '{current_mode}' mode.")
                parent_win.addstr(1, 0, "Press 1 to switch to managed mode, or 2 to cancel.")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "1":
                        if switch_interface_to_managed(selected_iface, self.logger):
                            parent_win.clear()
                            parent_win.addstr(0, 0,
                                              f"Switched {selected_iface} to managed mode. Press any key to continue.")
                            parent_win.refresh()
                            parent_win.getch()
                        else:
                            parent_win.clear()
                            parent_win.addstr(0, 0,
                                              f"Failed to switch {selected_iface} to managed mode. Press any key to cancel.")
                            parent_win.refresh()
                            parent_win.getch()
                            return
                    else:
                        return
                except Exception:
                    return

            # proceed with network selection
            chosen_ssid, chosen_security = self.select_network(parent_win)
            if not chosen_ssid:
                self.logger.debug("No network selected; aborting connection.")
                return
            self.tool.selected_network = chosen_ssid

            if chosen_security and chosen_security != "--":
                pwd = self.prompt_for_password(parent_win, chosen_security)
                self.tool.network_password = pwd
            else:
                self.tool.network_password = ""

            parent_win.clear()
            confirm_msg = f"Connecting to '{chosen_ssid}' on {selected_iface}..."
            parent_win.addstr(0, 0, confirm_msg)
            parent_win.refresh()
            curses.napms(1500)
            try:
                self.tool.run()
                break  # Successful connection; exit loop.
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error launching connection: {e}")
                parent_win.addstr(1, 0, "Press any key to retry or 0 to cancel.")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "0":
                        return
                except Exception:
                    return

    def launch_connect_from_founds(self, parent_win) -> None:
        """
        Connect from Founds:
          1. Reset values and select interface.
          2. Check interface mode; if not managed, prompt to switch.
          3. Scan for networks.
          4. Retrieve found networks (SSID, key) from the database.
          5. Filter scan results to those found in the DB.
          6. Auto-fill SSID and password based on found records.
          7. Launch the connection.
        Uses a nested loop to allow retry on failure.
        """
        from tools.helpers.tool_utils import (get_interface_mode, switch_interface_to_managed,
                                              get_wifi_networks)

        while True:
            self.reset_connection_values()

            selected_iface = self.select_interface(parent_win)
            if not selected_iface:
                self.logger.debug("No interface selected; aborting connect-from-founds.")
                return
            self.tool.selected_interface = selected_iface

            # Check current interface mode.
            current_mode = get_interface_mode(selected_iface, self.logger)
            if current_mode != "managed":
                parent_win.clear()
                parent_win.addstr(0, 0, f"Interface {selected_iface} is in '{current_mode}' mode.")
                parent_win.addstr(1, 0, "Press 1 to switch to managed mode, or 2 to cancel.")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "1":
                        if switch_interface_to_managed(selected_iface, self.logger):
                            parent_win.clear()
                            parent_win.addstr(0, 0,
                                              f"Switched {selected_iface} to managed mode. Press any key to continue.")
                            parent_win.refresh()
                            parent_win.getch()
                        else:
                            parent_win.clear()
                            parent_win.addstr(0, 0,
                                              f"Failed to switch {selected_iface} to managed mode. Press any key to cancel.")
                            parent_win.refresh()
                            parent_win.getch()
                            return
                    else:
                        return
                except Exception:
                    return

            parent_win.clear()
            parent_win.addstr(0, 0, f"Scanning for networks on {selected_iface}...")
            parent_win.refresh()

            scan_networks = get_wifi_networks(selected_iface, self.logger)
            self.logger.debug(f"Networks found from scan: {scan_networks}")
            if not scan_networks:
                parent_win.clear()
                parent_win.addstr(0, 0, "No networks found from scan!")
                parent_win.refresh()
                parent_win.getch()
                return

            parent_win.clear()
            parent_win.addstr(0, 0, "Loading found networks from database...")
            parent_win.refresh()

            from config.constants import BASE_DIR
            from tools.helpers.sql_utils import get_founds_ssid_and_key
            founds = get_founds_ssid_and_key(BASE_DIR)
            self.logger.debug(f"Raw founds (SSID, key): {founds}")
            if not founds:
                parent_win.clear()
                parent_win.addstr(0, 0, "No found networks in the database!")
                parent_win.refresh()
                parent_win.getch()
                return
            founds_dict = dict(founds)
            self.logger.debug(f"Found networks in DB: {founds_dict}")

            filtered_networks = [(ssid, sec) for ssid, sec in scan_networks if ssid in founds_dict]
            self.logger.debug(f"Filtered networks matching founds: {filtered_networks}")
            if not filtered_networks:
                parent_win.clear()
                parent_win.addstr(0, 0, "No found networks are currently available!")
                parent_win.refresh()
                parent_win.getch()
                return

            menu_items = []
            for ssid, security in filtered_networks:
                sec_str = " (Secured)" if security and security != "--" else " (Open)"
                menu_items.append(f"{ssid}{sec_str}")
            selection = self.draw_paginated_menu(parent_win, "Available Found Networks", menu_items)
            if selection == "back":
                return

            chosen_ssid = None
            chosen_security = None
            for ssid, security in filtered_networks:
                sec_str = " (Secured)" if security and security != "--" else " (Open)"
                if f"{ssid}{sec_str}" == selection:
                    chosen_ssid = ssid
                    chosen_security = security
                    break
            if not chosen_ssid:
                self.logger.debug("No network selected; aborting connect-from-founds.")
                return

            self.tool.selected_network = chosen_ssid
            auto_password = founds_dict.get(chosen_ssid, "")
            self.tool.network_password = auto_password
            self.logger.debug(f"Auto-filled password for '{chosen_ssid}': {auto_password}")

            parent_win.clear()
            confirm_msg = f"Connecting to '{chosen_ssid}' on {selected_iface} (from founds)..."
            parent_win.addstr(0, 0, confirm_msg)
            parent_win.refresh()
            curses.napms(1500)
            try:
                self.tool.run()
                break  # Connection succeeded.
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error launching connection: {e}")
                parent_win.addstr(1, 0, "Press any key to retry or 0 to cancel.")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "0":
                        return
                except Exception:
                    return

    def launch_disconnect(self, parent_win) -> None:
        """
        Disconnects the network on a selected (currently connected) interface.
        """
        selected_iface = self.select_connected_interface(parent_win)
        if not selected_iface:
            self.logger.debug("No connected interface selected; aborting disconnect.")
            return
        self.tool.selected_interface = selected_iface

        parent_win.clear()
        parent_win.addstr(0, 0, f"Disconnecting {selected_iface}...")
        parent_win.refresh()
        try:
            self.tool.disconnect()
            parent_win.addstr(1, 0, "Disconnected successfully.")
        except Exception as e:
            parent_win.addstr(1, 0, f"Error disconnecting: {e}")
        parent_win.refresh()
        parent_win.getch()

    def launch_background_scan(self, parent_win) -> None:
        """
        Initiates the background scan process for matching networks from the database.
        Forces the user to select an interface (resetting previous selections), loads the
        database networks, and starts the background scan thread.
        After execution, the user is prompted to either retry or return to the main menu.
        """
        while True:
            # reset prior attribute selections to none
            parent_win.erase()
            parent_win.refresh()
            self.reset_connection_values()

            # prompt interface selection
            selected_iface = self.select_interface(parent_win)
            parent_win.erase()
            parent_win.refresh()
            if not selected_iface:
                self.logger.debug("No interface selected; aborting background scan.")
                break
            self.tool.selected_interface = selected_iface

            # load database networks (SSID, BSSID, key) into memory.
            self.tool.load_db_networks()

            # start the background scanning thread if not already running.
            if not self.tool.scanner_running:
                self.tool.start_background_scan()
                parent_win.erase()
                parent_win.refresh()
                parent_win.addstr(
                    0, 0,
                    f"Background scan initiated on {self.tool.selected_interface}. Alerts will display when a network is found."
                )
            else:
                parent_win.erase()
                parent_win.refresh()
                parent_win.addstr(0, 0, "Background scan is already running.")

            parent_win.refresh()
            curses.napms(2000)

            # After showing the status, prompt the user for next action.
            parent_win.erase()
            parent_win.refresh()
            parent_win.addstr(0, 0, "Press any key to return to the main menu, or 0 to retry background scan.")
            parent_win.refresh()
            key = parent_win.getch()
            try:
                if chr(key) == "0":
                    continue  # Retry the background scan (loop again)
                else:
                    break  # Exit the loop to return to main menu.
            except Exception:
                break

    def reset_connection_values(self):
        """
        Resets the connection-related selections to ensure a fresh start.
        """
        self.tool.selected_interface = None
        self.tool.selected_network = None
        self.tool.network_password = None

    def __call__(self, stdscr) -> None:
        """
        Launches the NetConnect submenu using curses.
        Main options include:
          - Manual Connect
          - Auto-Connect
          - Disconnect
          - (Plus the dynamic "Toggle Scrolling" option)
          - Back
        """
        curses.curs_set(0)
        self.tool.selected_interface = None
        self.tool.selected_network = None
        self.tool.network_password = None

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        base_menu = ["Start Scanning", "Manual Connect", "Auto-Connect", "Disconnect", "Utils"]
        while True:
            selection = self.show_main_menu(submenu_win, base_menu, "NetConnect")
            if selection.lower() == "back":
                break
            elif selection == "Start Scanning":
                self.launch_background_scan(submenu_win)
            elif selection == "Auto-Connect":
                self.launch_connect_from_founds(submenu_win)
            elif selection == "Manual Connect":
                self.launch_connect(submenu_win)
            elif selection == "Disconnect":
                self.launch_disconnect(submenu_win)
            elif selection == "Utils":
                self.utils_menu(submenu_win)
            submenu_win.clear()
            submenu_win.refresh()

