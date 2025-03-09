import curses
import logging
import subprocess
from typing import Any, List, Tuple

import curses
import logging
import subprocess
from typing import Any, List, Tuple

def get_wifi_networks(interface: str, logger: logging.Logger) -> List[Tuple[str, str]]:
    """
    Uses nmcli to scan for available networks on the specified interface.
    Returns a list of tuples in the form (SSID, SECURITY).
    Uses the terse output with selected fields for easier parsing.
    """
    cmd = ["sudo", "nmcli", "-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "ifname", interface]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        logger.error(f"nmcli scan failed: {e}")
        return []
    networks = []
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            ssid = parts[0].strip()
            security = parts[1].strip()  # e.g., '--' indicates an open network
            networks.append((ssid, security))
    return networks


class NetConnectSubmenu:
    def __init__(self, tool_instance):
        """
        Initialize the submenu for NetConnectTool.
        """
        self.tool = tool_instance
        self.logger = logging.getLogger("NetConnectToolSubmenu")
        self.logger.debug("NetConnectToolSubmenu initialized.")

    def draw_menu(self, parent_win, title: str, menu_items: List[str]) -> Any:
        """
        Draws a centered menu with a title and list of options in the given parent window.
        Returns the created window.
        """
        parent_win.clear()
        h, w = parent_win.getmaxyx()
        box_height = len(menu_items) + 4
        box_width = max(len(title), *(len(item) for item in menu_items)) + 4
        start_y = (h - box_height) // 2
        start_x = (w - box_width) // 2
        menu_win = curses.newwin(box_height, box_width, start_y, start_x)
        menu_win.keypad(True)
        menu_win.box()
        menu_win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
        for idx, item in enumerate(menu_items):
            menu_win.addstr(2 + idx, 2, item)
        menu_win.refresh()
        return menu_win

    def draw_paginated_menu(self, parent_win, title: str, menu_items: List[str]) -> str:
        """
        Draws a paginated menu for a list of options.
        Navigation is done via 'n' (next) and 'p' (previous) keys.
        A "[0] Back" option is always included.
        Returns the selected option (the original option string) or "back" if cancelled.
        """
        h, w = parent_win.getmaxyx()
        max_items = max(h - 6, 1)
        total_items = len(menu_items)
        total_pages = (total_items + max_items - 1) // max_items
        current_page = 0

        while True:
            start_index = current_page * max_items
            end_index = start_index + max_items
            page_items = menu_items[start_index:end_index]

            # Prefix each item with its number on this page.
            display_items = [f"[{i+1}] {option}" for i, option in enumerate(page_items)]
            if total_pages > 1:
                pagination_info = f"Page {current_page+1}/{total_pages} (n: next, p: previous)"
                display_items.append(pagination_info)
            display_items.append("[0] Back")

            menu_win = self.draw_menu(parent_win, title, display_items)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue

            if ch.lower() == 'n' and current_page < total_pages - 1:
                current_page += 1
                continue
            elif ch.lower() == 'p' and current_page > 0:
                current_page -= 1
                continue
            elif ch == '0':
                return "back"
            elif ch.isdigit():
                selection = int(ch)
                if 1 <= selection <= len(page_items):
                    return page_items[selection - 1]

    def select_interface(self, parent_win) -> Any:
        """
        Presents a paginated menu of available interfaces (from self.tool.interfaces['wlan']).
        Returns the selected interface name or None if cancelled.
        """
        interfaces = self.tool.interfaces.get("wlan", [])
        available = [iface.get("name") for iface in interfaces if iface.get("name")]
        if not available:
            parent_win.clear()
            parent_win.addstr(0, 0, "No interfaces available!")
            parent_win.refresh()
            parent_win.getch()
            return None
        selection = self.draw_paginated_menu(parent_win, "Select Interface", available)
        if selection == "back":
            return None
        return selection

    def select_network(self, parent_win) -> Tuple[Any, Any]:
        """
        Uses nmcli to scan for WiFi networks on the selected interface.
        Displays the available networks using a paginated menu and returns a tuple:
        (selected SSID, security flag). Returns (None, None) if cancelled.
        """
        if not self.tool.selected_interface:
            self.logger.error("Interface not selected for scanning networks.")
            return (None, None)
        networks = get_wifi_networks(self.tool.selected_interface, self.logger)
        if not networks:
            parent_win.clear()
            parent_win.addstr(0, 0, "No WiFi networks found!")
            parent_win.refresh()
            parent_win.getch()
            return (None, None)
        menu_items = []
        for ssid, security in networks:
            # Indicate if the network is secured (assuming '--' means open)
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            menu_items.append(f"{ssid}{sec_str}")
        selection = self.draw_paginated_menu(parent_win, "Available Networks", menu_items)
        if selection == "back":
            return (None, None)
        chosen_ssid = None
        chosen_security = None
        for ssid, security in networks:
            sec_str = " (Secured)" if security and security != "--" else " (Open)"
            entry = f"{ssid}{sec_str}"
            if entry == selection:
                chosen_ssid = ssid
                chosen_security = security
                break
        return (chosen_ssid, chosen_security)

    def prompt_for_password(self, parent_win, security: str) -> str:
        """
        Prompts the user for a password if the chosen network is secured.
        Returns the entered password.
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
        Handles the connection process:
          1. Select an interface.
          2. Scan and select a network.
          3. Prompt for a password if needed.
          4. Launch the connection via the tool's run() method.
        """
        # Clear previous selections.
        self.tool.selected_interface = None
        self.tool.selected_network = None
        self.tool.network_password = None

        selected_iface = self.select_interface(parent_win)
        if not selected_iface:
            self.logger.debug("No interface selected; aborting connection.")
            return
        self.tool.selected_interface = selected_iface

        chosen_ssid, chosen_security = self.select_network(parent_win)
        if not chosen_ssid:
            self.logger.debug("No network selected; aborting connection.")
            return
        self.tool.selected_network = chosen_ssid

        # Prompt for a password if the network is secured.
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
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching connection: {e}")
            parent_win.refresh()
            parent_win.getch()

    def __call__(self, stdscr) -> None:
        """
        Launches the NetConnect submenu.
        Main options are:
          1. Connect
          0. Back
        """
        curses.curs_set(0)
        # Clear any previous selections.
        self.tool.selected_interface = None
        self.tool.selected_network = None
        self.tool.network_password = None

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        menu_items = ["Connect", "Back"]
        numbered_menu = [f"[{i+1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            menu_win = self.draw_menu(submenu_win, "NetConnect Submenu", numbered_menu)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch == "1":
                self.launch_connect(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()
