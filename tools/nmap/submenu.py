# tools/nmap/submenu.py
import curses
import logging
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
