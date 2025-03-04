import os
import curses
import logging
from typing import Any, List

# local
from utils import ipc
from tools.helpers.tool_utils import format_scan_display
from config.constants import DEFAULT_SOCKET_PATH


class HcxToolSubmenu:
    def __init__(self, tool_instance):
        """
        Initialize the submenu for Hcxtool.
        """
        self.tool = tool_instance
        self.logger = logging.getLogger("HcxToolSubmenu")
        self.logger.debug("HcxToolSubmenu initialized.")

    def draw_menu(self, parent_win, title: str, menu_items: List[str]) -> Any:
        """
        Draws a centered menu with a title and list of options in the given parent window.
        Returns the menu window which should be used for capturing input.
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
        Draws a paginated menu for a list of options. Navigation is done via 'n' (next)
        and 'p' (previous) keys, and a "[0] Back" option is always included.

        The displayed menu items are prefixed with numbers corresponding to their selection index.

        Parameters
        ----------
        parent_win : curses window
            The parent window where the menu is to be displayed.
        title : str
            The title of the menu.
        menu_items : List[str]
            A list of option strings.

        Returns
        -------
        str
            The selected option (as the original string from menu_items), or "back" if cancelled.

        Example
        -------
        >>> selection = self.draw_paginated_menu(parent_win, "Select Option", [f"Item {i}" for i in range(1, 21)])  # doctest: +SKIP
        >>> print(selection)
        Item 7
        """
        h, w = parent_win.getmaxyx()
        # Reserve space: 4 lines for borders, title, and instructions.
        max_items = max(h - 6, 1)
        total_items = len(menu_items)
        total_pages = (total_items + max_items - 1) // max_items
        current_page = 0

        while True:
            start_index = current_page * max_items
            end_index = start_index + max_items
            page_items = menu_items[start_index:end_index]

            # Prefix each item with its number relative to this page.
            display_items = [f"[{i + 1}] {option}" for i, option in enumerate(page_items)]

            if total_pages > 1:
                pagination_info = f"Page {current_page + 1}/{total_pages} (n: next, p: previous)"
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
        Presents a paginated menu of available interfaces.
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
        menu_items = [f"{name}" for name in available]
        selection = self.draw_paginated_menu(parent_win, "Select Interface", menu_items)
        if selection == "back":
            return None
        return selection


    def select_preset(self, parent_win) -> Any:
        """
        Presents a paginated menu of all scan presets.
        Returns the selected preset dictionary or None if cancelled.
        """
        presets_dict = self.tool.presets
        if not presets_dict:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available!")
            parent_win.refresh()
            parent_win.getch()
            return None

        try:
            sorted_keys = sorted(presets_dict.keys(), key=lambda k: int(k))
        except Exception:
            sorted_keys = sorted(presets_dict.keys())
        preset_list = [(key, presets_dict[key]) for key in sorted_keys]
        menu_items = [f"{preset.get('description', 'No description')}" for _, preset in preset_list]
        selection = self.draw_paginated_menu(parent_win, "Select Scan Preset", menu_items)
        if selection == "back":
            return None
        # Find the matching preset in preset_list.
        for key, preset in preset_list:
            if preset.get("description", "No description") == selection:
                self.logger.debug(f"selected preset: {preset}")
                return preset
        return None


    def launch_scan(self, parent_win) -> None:
        """
        Handles launching a scan.
        Clears previous selections, prompts for interface and preset via paginated menus,
        and then runs the scan command.
        """
        self.tool.selected_interface = None
        self.tool.selected_preset = None
        self.tool.preset_description = None
        self.logger.debug("launch_scan: Cleared previous interface and preset selections.")

        selected_iface = self.select_interface(parent_win)
        if not selected_iface:
            self.logger.debug("launch_scan: No interface selected; aborting scan launch.")
            return
        self.tool.selected_interface = selected_iface

        selected_preset = self.select_preset(parent_win)
        if not selected_preset:
            self.logger.debug("launch_scan: No preset selected; aborting scan launch.")
            return
        self.tool.selected_preset = selected_preset
        self.tool.preset_description = selected_preset.get('description', '')

        parent_win.clear()
        confirm_msg = f"Launching scan on {selected_iface} with preset: {selected_preset.get('description', '')}"
        parent_win.addstr(0, 0, confirm_msg)
        parent_win.refresh()
        curses.napms(1500)

        try:
            self.tool.run()
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching scan: {e}")
            parent_win.refresh()
            parent_win.getch()


    def view_scans(self, parent_win) -> None:
        """
        Handles the 'View Scans' option.
        Displays active scans using pagination and allows the user to choose one to swap
        into the main pane via the SWAP_SCAN IPC handler.
        """
        tool_name = getattr(self.tool, 'name', 'hcxtool')
        message = {"action": "GET_SCANS", "tool": tool_name}
        self.logger.debug(f"view_scans: Sending GET_SCANS for tool '{tool_name}'")
        response = ipc.send_ipc_command(message, DEFAULT_SOCKET_PATH)
        scans = response.get("scans", [])
        parent_win.clear()
        if not scans:
            parent_win.addstr(0, 0, "No active scans found!")
            parent_win.refresh()
            parent_win.getch()
            return

        menu_items = []
        for idx, scan in enumerate(scans, start=1):
            formatted = format_scan_display(scan)
            menu_items.append(formatted)
        selection = self.draw_paginated_menu(parent_win, "Active Scans", menu_items)
        if selection == "back":
            return

        # Map the selection back to the scan (assuming the order is preserved).
        try:
            selected_index = menu_items.index(selection)
        except ValueError:
            self.logger.error("Selected scan not found in list.")
            return
        selected_scan = scans[selected_index]
        new_title = f"{self.tool.selected_interface}_{self.tool.selected_preset.get('description', '')}"
        swap_message = {
            "action": "SWAP_SCAN",
            "tool": tool_name,
            "pane_id": selected_scan.get("pane_id"),
            "new_title": new_title
        }
        swap_response = ipc.send_ipc_command(swap_message, DEFAULT_SOCKET_PATH)
        parent_win.clear()
        if swap_response.get("status") == "SWAP_SCAN_OK":
            parent_win.addstr(0, 0, "Scan swapped successfully!")
        else:
            error_text = swap_response.get("error", "Unknown error")
            parent_win.addstr(0, 0, f"Error swapping scan: {error_text}")
        parent_win.refresh()
        parent_win.getch()


    def upload(self, parent_win) -> None:
        """
        Handles the 'Upload' option.
        Lists available .pcapng files from the results directory using pagination and lets the user choose an upload option.
        """
        results_dir = getattr(self.tool, "results_dir", "results")
        try:
            files = [f for f in os.listdir(results_dir) if f.endswith(".pcapng")]
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error accessing results directory: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        if not files:
            parent_win.clear()
            parent_win.addstr(0, 0, "No pcapng files found!")
            parent_win.refresh()
            parent_win.getch()
            return

        menu_items = ["Upload All"] + files
        selection = self.draw_paginated_menu(parent_win, "Upload PCAPNG Files", menu_items)
        if selection == "back":
            return

        parent_win.clear()
        if selection == "Upload All":
            parent_win.addstr(0, 0, "Uploading all files...")
            parent_win.refresh()
            curses.napms(1500)
            parent_win.addstr(1, 0, "Upload All complete.")
        else:
            parent_win.addstr(0, 0, f"Uploading {selection}...")
            parent_win.refresh()
            curses.napms(1500)
            parent_win.addstr(1, 0, f"Uploaded {selection}.")
        parent_win.refresh()
        parent_win.getch()


    def utils_menu(self, parent_win) -> None:
        """
        Handles the 'Utils' option.
        Currently a placeholder submenu using pagination with only a 'Back' option.
        """
        menu_items = ["No utilities available"]
        selection = self.draw_paginated_menu(parent_win, "Utils", menu_items)
        # In this simple case, any selection leads back.
        return

    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool submenu.
        Before displaying the menu, clears any previous selections.
        """
        curses.curs_set(0)
        self.tool.selected_interface = None
        self.tool.selected_preset = None
        self.tool.preset_description = None

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        while True:
            menu_items = [
                "Launch Scan",
                "View Scans",
                "Upload",
                "Utils",
                "Back"
            ]
            # Draw for main menu; may paginate
            menu_win = self.draw_menu(submenu_win, "HCXTool Submenu",
                                      [f"[{i + 1}] {item}" for i, item in enumerate(menu_items)])
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
                self.upload(submenu_win)
            elif ch == "4":
                self.utils_menu(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()
