import curses
import logging
import time
from typing import List, Tuple, Any

# local
from tools.submenu import BaseSubmenu
from tools.pyficonnect.scapymanager import ScapyManager


class PyfyConnectSubmenu(BaseSubmenu):
    def __init__(self, tool_instance, stdscr=None):
        super().__init__(tool_instance, stdscr)
        self.logger = logging.getLogger("PyfyConnectSubmenu")
        self.logger.debug("PyfyConnectSubmenu initialized.")
        #self.scapy_manager = ScapyManager.get_instance()
        #self.scapy_manager.register_alert_callback(self.handle_alert)

    ###########################
    ##### TOOL SCAN LOGIC #####
    ###########################
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
            return None, None
        menu_items = []
        for ssid, security in networks:
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            menu_items.append(f"{ssid}{sec_str}")
        selection = self.draw_paginated_menu(parent_win, "Available Networks", menu_items)
        if selection == "back":
            return None, None
        chosen_ssid = None
        chosen_security = None
        for ssid, security in networks:
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            if f"{ssid}{sec_str}" == selection:
                chosen_ssid = ssid
                chosen_security = security
                break
        return chosen_ssid, chosen_security

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
          3. Ensure the interface is in managed mode.
          4. Scan for networks.
          5. Prompt for password if needed.
          6. Attempt the connection via self.tool.run() using attempt_connection().

        Uses a nested loop so that if an error occurs, the user can retry or cancel.
        """
        while True:
            # ensure no previous selections
            self.tool.selected_interface = None
            self.tool.selected_network = None
            self.tool.network_password = None

            # select interface to use for the new connection
            selected_iface = self.select_interface(parent_win)
            if not selected_iface:
                self.logger.debug("No interface selected; aborting connection.")
                return
            self.tool.selected_interface = selected_iface

            # helper from tools/helpers/tool_utils.py to ensure managed
            parent_win.clear()
            parent_win.refresh()
            if not self.ensure_interface_managed(parent_win, selected_iface):
                return

            # select network
            chosen_ssid, chosen_security = self.select_network(parent_win)
            if not chosen_ssid:
                self.logger.debug("No network selected; aborting connection.")
                return
            self.tool.selected_network = chosen_ssid

            # password prompt
            if chosen_security and chosen_security != "--":
                pwd = self.prompt_for_password(parent_win, chosen_security)
                self.tool.network_password = pwd
            else:
                self.tool.network_password = ""

            # attempt connection
            result = self.attempt_connection(parent_win, selected_iface, chosen_ssid)
            if result is True:
                break  # success
            elif result is None:
                return
            # retry again if false

    def launch_connect_from_founds(self, parent_win) -> None:
        """
        Connect from Founds:
          1. Reset values and select interface.
          2. Ensure the interface is in managed mode.
          3. Scan for networks.
          4. Retrieve found networks (SSID, key) from the database.
          5. Filter scan results to those found in the DB.
          6. Auto-fill SSID and password based on found records.
          7. Attempt connection using self.tool.run() via a helper.

        Uses a nested loop to allow retry on failure.
        """
        from tools.helpers.tool_utils import get_wifi_networks

        while True:
            self.reset_connection_values()

            selected_iface = self.select_interface(parent_win)
            if not selected_iface:
                self.logger.debug("No interface selected; aborting connect-from-founds.")
                return
            self.tool.selected_interface = selected_iface

            # ensure the interface is in managed mode
            parent_win.clear()
            parent_win.refresh()
            if not self.ensure_interface_managed(parent_win, selected_iface):
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

            # Use the helper to attempt the connection.
            result = self.attempt_connection(parent_win, selected_iface, chosen_ssid)
            if result is True:
                break  # Connection succeeded.
            elif result is None:
                return  # User cancelled.
            # Otherwise, result is False; loop to retry.

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
        Initiates the background scan process for matching networks from the database
        using the global ScapyManager. Forces the user to select an interface, then starts
        the global scanning thread if not already running, and returns immediately to the main menu.
        """
        parent_win.erase()
        parent_win.refresh()
        self.reset_connection_values()

        # Prompt for interface
        selected_iface = self.select_interface(parent_win)
        parent_win.erase()
        parent_win.refresh()
        if not selected_iface:
            self.logger.debug("No interface selected; aborting background scan.")
            return

        # set iface & check for monitor & switch if not
        self.tool.selected_interface = selected_iface
        from tools.helpers.tool_utils import get_interface_mode, switch_interface_to_monitor
        current_mode = get_interface_mode(selected_iface, self.logger)
        if current_mode.lower() != "monitor":
            self.logger.info("Interface %s is in %s mode; switching to monitor mode.", selected_iface, current_mode)
            if not switch_interface_to_monitor(selected_iface, self.logger):
                self.logger.error("Failed to switch interface %s to monitor mode.", selected_iface)
            else:
                self.logger.info("Interface %s successfully switched to monitor mode.", selected_iface)

        # global ScapyManager instance
        from tools.pyficonnect.scapymanager import ScapyManager
        scapymanager = ScapyManager.get_instance()
        scapymanager.load_db_networks()

        # start
        if not scapymanager.scanner_running:
            try:
                scapymanager.start_scanning(selected_iface, dwell_time=0.2)
            except Exception as e:
                parent_win.erase()
                parent_win.addstr(0, 0, f"Error starting background scan: {e}")
                parent_win.refresh()
                curses.napms(2000)
                return
        else:
            self.logger.info("Global background scanning is already running.")

        parent_win.erase()
        parent_win.addstr(0, 0, "Background scan started. Alerts will appear as networks are found.")
        parent_win.refresh()
        curses.napms(1500)
        return

    ###########################
    ##### SUBMENU NESTING #####
    ###########################
    def connection_menu(self, parent_win) -> None:
        """
        Presents a connection management submenu that lets the user choose
        between Manual Connect, Auto-Connect, and Disconnect.
        """
        conn_options = ["Manual Connect", "Auto-Connect", "Disconnect"]
        while True:
            parent_win.clear()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Connection Management", conn_options)
            if selection.lower() == self.BACK_OPTION:
                break
            elif selection == "Manual Connect":
                self.launch_connect(parent_win)
            elif selection == "Auto-Connect":
                self.launch_connect_from_founds(parent_win)
            elif selection == "Disconnect":
                self.launch_disconnect(parent_win)
            # clear and redisplay
            parent_win.clear()
            parent_win.refresh()

    ##########################
    ##### HELPER METHODS #####
    ##########################
    def ensure_interface_managed(self, parent_win, interface) -> bool:
        """
        Checks if the specified interface is in 'managed' mode.
        If not, prompts the user to switch to managed mode.
        Returns True if the interface is (or was successfully switched to) managed;
        otherwise, returns False.
        """
        from tools.helpers.tool_utils import get_interface_mode, switch_interface_to_managed

        current_mode = get_interface_mode(interface, self.logger)
        if current_mode == "managed":
            return True

        parent_win.clear()
        parent_win.addstr(0, 0, f"Interface {interface} is in '{current_mode}' mode.")
        parent_win.addstr(1, 0, "Press 1 to switch to managed mode, or 2 to cancel.")
        parent_win.refresh()
        key = parent_win.getch()
        try:
            if chr(key) == "1":
                if switch_interface_to_managed(interface, self.logger):
                    parent_win.clear()
                    parent_win.addstr(0, 0, f"Switched {interface} to managed mode. Press any key to continue.")
                    parent_win.refresh()
                    parent_win.getch()
                    return True
                else:
                    parent_win.clear()
                    parent_win.addstr(0, 0, f"Failed to switch {interface} to managed mode. Press any key to cancel.")
                    parent_win.refresh()
                    parent_win.getch()
                    return False
            else:
                return False
        except Exception:
            return False

    def attempt_connection(self, parent_win, iface, ssid):
        """
        Attempts to launch the connection by calling self.tool.run().
        Displays a confirmation message before the attempt. If an error occurs,
        prompts the user to retry (any key) or cancel (press "0").

        Returns:
          True  - if the connection was successful.
          False - if the attempt failed and the user wants to retry.
          None  - if the user cancels.
        """
        parent_win.clear()
        confirm_msg = f"Connecting to '{ssid}' on {iface}..."
        parent_win.addstr(0, 0, confirm_msg)
        parent_win.refresh()
        curses.napms(1500)
        try:
            self.tool.run()
            return True
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching connection: {e}")
            parent_win.addstr(1, 0, "Press any key to retry or 0 to cancel.")
            parent_win.refresh()
            key = parent_win.getch()
            try:
                if chr(key) == "0":
                    return None
            except Exception:
                return None
            return False

    def __call__(self, stdscr) -> None:
        curses.curs_set(0)
        self.stdscr = stdscr
        if hasattr(self.tool.ui_instance, "alert_win"):
            del self.tool.ui_instance.alert_win  # Force re-creation
        self.alert_queue = []  # Clear any stale alerts
        # create persistent alert window on the left one‑third
        self.setup_alert_window(stdscr)
        h, w = stdscr.getmaxyx()
        alert_width = w // 3
        # create the submenu window in the remaining right two‑thirds
        submenu_win = curses.newwin(h, w - alert_width, 0, alert_width)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        # start a background thread to update alerts every second
        self.running = True
        import threading, time
        def _alert_updater():
            while self.running:
                self.update_alert_window()
                time.sleep(1)

        updater = threading.Thread(target=_alert_updater, daemon=True)
        updater.start()

        # define the base menu
        base_menu_items = ["Scan", "Manage", "Utils"]
        title = getattr(self.tool, "name", "PyfiConnect")

        while True:
            # draw the main menu in the submenu window
            submenu_win.clear()
            submenu_win.refresh()
            selection = self.show_main_menu(submenu_win, base_menu_items, title)
            if selection.lower() == "back":
                break
            elif selection == "Scan":
                self.launch_background_scan(submenu_win)
            elif selection == "Manage":
                self.connection_menu(submenu_win)
            elif selection == "Utils":
                self.utils_menu(submenu_win)
            # clear after processing
            submenu_win.clear()
            submenu_win.refresh()

        # stop alert signal updates
        self.running = False
        updater.join(timeout=1)
        self.tool.ui_instance.unregister_active_submenu()
        self.scapy_manager.unregister_alert_callback(self.handle_alert)
        self.logger.debug("PyfiConnectSubmenu: Active submenu unregistered in __call__ exit.")










