import os
import curses
import logging
from typing import Any, List
from config.constants import DEFAULT_SOCKET_PATH

# local
from utils import ipc

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

    def select_interface(self, parent_win) -> Any:
        interfaces = self.tool.interfaces.get("wlan", [])
        available = [iface.get("name") for iface in interfaces if iface.get("name")]
        if not available:
            parent_win.clear()
            parent_win.addstr(0, 0, "No interfaces available!")
            parent_win.refresh()
            parent_win.getch()
            return None
        menu_items = [f"[{idx}] {name}" for idx, name in enumerate(available, start=1)]
        menu_items.append("[0] Back")
        menu_win = self.draw_menu(parent_win, "Select Interface", menu_items)
        while True:
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch.isdigit():
                if ch == "0":
                    return None
                num = int(ch)
                if 1 <= num <= len(available):
                    selected = available[num - 1]
                    return selected
            elif key == 27:
                return None

    def select_preset(self, parent_win) -> Any:
        """
        Presents a menu of all scan presets.
        Returns the selected preset dictionary or None if cancelled.
        """
        presets_dict = self.tool.presets
        if not presets_dict:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available!")
            parent_win.refresh()
            parent_win.getch()
            return None

        # Sort preset keys (e.g., "1", "2", "3")
        try:
            sorted_keys = sorted(presets_dict.keys(), key=lambda k: int(k))
        except Exception:
            sorted_keys = sorted(presets_dict.keys())
        # Build list of tuples (key, preset)
        preset_list = [(key, presets_dict[key]) for key in sorted_keys]
        menu_items = [
            f"[{idx}] {preset.get('description', 'No description')}"
            for idx, (key, preset) in enumerate(preset_list, start=1)
        ]
        menu_items.append("[0] Back")
        menu_win = self.draw_menu(parent_win, "Select Scan Preset", menu_items)
        while True:
            key_input = menu_win.getch()
            try:
                ch = chr(key_input)
            except Exception:
                continue
            if ch.isdigit():
                selection = int(ch)
                if selection == 0:
                    return None
                elif 1 <= selection <= len(preset_list):
                    _, selected_preset = preset_list[selection - 1]
                    return selected_preset
            elif key_input == 27:  # ESC key
                return None

    def launch_scan(self, parent_win) -> None:
        """
        Handles launching a scan.
        Clears previous selections, prompts for interface and preset,
        and then runs the scan command.
        """
        # Clear previous selections.
        self.tool.selected_interface = None
        self.tool.selected_preset = None
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

        # Confirm the selections
        parent_win.clear()
        confirm_msg = f"Launching scan on {selected_iface} with preset: {selected_preset.get('description', '')}"
        parent_win.addstr(0, 0, confirm_msg)
        parent_win.refresh()
        curses.napms(1500)

        try:
            # Run the tool; the run() method will use self.selected_interface and self.selected_preset.
            self.tool.run()
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching scan: {e}")
            parent_win.refresh()
            parent_win.getch()

    def view_scans(self, parent_win) -> None:
        """
        Handles the 'View Scans' option.
        Simply displays active scans without offering renaming.
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
            display = scan.get("internal_name", scan.get("scan_profile", "Unnamed Scan"))
            menu_items.append(f"[{idx}] {display}")
        menu_items.append("[0] Back")
        menu_win = self.draw_menu(parent_win, "Active Scans", menu_items)

        # In this revised version, we simply display scans.
        while True:
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch.isdigit():
                if ch == "0":
                    return
                # You could add further non-renaming actions here if needed.
            elif key == 27:
                return

    def upload(self, parent_win) -> None:
        """
        Handles the 'Upload' option.
        Lists available .pcapng files from the results directory and lets the user choose an upload option.
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

        menu_items = ["[1] Upload All"]
        for idx, f in enumerate(files, start=2):
            menu_items.append(f"[{idx}] {f}")
        menu_items.append("[0] Cancel")
        menu_win = self.draw_menu(parent_win, "Upload PCAPNG Files", menu_items)

        while True:
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch.isdigit():
                if ch == "0":
                    return
                num = int(ch)
                if num == 1:
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Uploading all files...")
                    parent_win.refresh()
                    curses.napms(1500)
                    parent_win.addstr(1, 0, "Upload All complete.")
                    parent_win.refresh()
                    parent_win.getch()
                    return
                elif 2 <= num < 2 + len(files):
                    selected_file = files[num - 2]
                    parent_win.clear()
                    parent_win.addstr(0, 0, f"Uploading {selected_file}...")
                    parent_win.refresh()
                    curses.napms(1500)
                    parent_win.addstr(1, 0, f"Uploaded {selected_file}.")
                    parent_win.refresh()
                    parent_win.getch()
                    return
            elif key == 27:
                return

    def utils_menu(self, parent_win) -> None:
        """
        Handles the 'Utils' option.
        Currently a placeholder submenu with only a 'Back' option.
        """
        menu_items = ["No utilities available", "[0] Back"]
        menu_win = self.draw_menu(parent_win, "Utils", menu_items)
        while True:
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch == "0" or key == 27:
                return

    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool submenu.
        Before displaying the menu, clears any previous selections.
        """
        curses.curs_set(0)
        # Clear previous selections each time the submenu is launched.
        self.tool.selected_interface = None
        self.tool.selected_preset = None

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        while True:
            menu_items = [
                "[1] Launch Scan",
                "[2] View Scans",
                "[3] Upload",
                "[4] Utils",
                "[0] Back"
            ]
            menu_win = self.draw_menu(submenu_win, "HCXTool Submenu", menu_items)
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
