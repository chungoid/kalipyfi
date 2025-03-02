import os
import curses
import logging
from typing import Any, List

# local
from utils import ipc


class HcxToolSubmenu:
    def __init__(self, tool_instance):
        """
        Initialize the submenu for Hcxtool.

        :param tool_instance: The Hcxtool instance.
        """
        self.tool = tool_instance
        self.logger = logging.getLogger("HcxToolSubmenu")

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
        # Create an independent window for the menu box.
        menu_win = curses.newwin(box_height, box_width, start_y, start_x)
        menu_win.keypad(True)
        menu_win.box()
        menu_win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
        for idx, item in enumerate(menu_items):
            menu_win.addstr(2 + idx, 2, item)
        menu_win.refresh()
        return menu_win

    def select_scan(self, parent_win) -> None:
        """
        Handles the 'Name Scan' option.
        Runs the original routine: interface selection, preset selection, then launching the scan.
        """
        selected_iface = self.select_interface(parent_win)
        if not selected_iface:
            return
        selected_preset = self.select_preset(parent_win, selected_iface)
        if not selected_preset:
            return

        # Save the scan settings in the tool instance.
        self.tool.scan_settings = selected_preset
        self.tool.scan_settings["interface"] = selected_iface

        parent_win.clear()
        confirm_msg = f"Launching scan on {selected_iface} with preset: {selected_preset.get('description', '')}"
        parent_win.addstr(0, 0, confirm_msg)
        parent_win.refresh()
        curses.napms(1500)
        try:
            self.tool.run(selected_iface)
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching scan: {e}")
            parent_win.refresh()
            parent_win.getch()

    def view_scans(self, parent_win) -> None:
        """
        Handles the 'View Scans' option.
        Fetches active scans via IPC, displays them, and allows selection for swapping.
        """
        tool_name = getattr(self.tool, 'name', 'hcxtool')
        message = {"action": "GET_SCANS", "tool": tool_name}
        response = ipc.send_ipc_command(message)
        scans = response.get("scans", [])
        if not scans:
            parent_win.clear()
            parent_win.addstr(0, 0, "No active scans found!")
            parent_win.refresh()
            parent_win.getch()
            return

        menu_items = []
        for idx, scan in enumerate(scans, start=1):
            display = scan.get("internal_name", scan.get("scan_profile", "Unnamed Scan"))
            menu_items.append(f"[{idx}] {display}")
        menu_items.append("[0] Back")
        menu_win = self.draw_menu(parent_win, "Active", menu_items)

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
                if 1 <= num <= len(scans):
                    selected_scan = scans[num - 1]
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Enter new title for scan: ")
                    parent_win.refresh()
                    curses.echo()
                    new_title = parent_win.getstr(1, 0).decode('utf-8')
                    curses.noecho()
                    swap_message = {
                        "action": "SWAP_SCAN",
                        "tool": tool_name,
                        "pane_id": selected_scan.get("pane_id"),
                        "new_title": new_title
                    }
                    swap_response = ipc.send_ipc_command(swap_message)
                    parent_win.clear()
                    if swap_response.get("status") == "SWAP_SCAN_OK":
                        parent_win.addstr(0, 0, "Scan swapped successfully!")
                    else:
                        parent_win.addstr(0, 0, f"Error swapping scan: {swap_response.get('error', 'Unknown error')}")
                    parent_win.refresh()
                    parent_win.getch()
                    return
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
                    # Placeholder: implement actual upload logic.
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
                    # Placeholder: implement actual file upload logic.
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

    def select_interface(self, parent_win) -> Any:
        """
        Original interface selection routine.
        """
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
                    return available[num - 1]
            elif key == 27:
                return None

    def select_preset(self, parent_win, selected_interface: str) -> Any:
        """
        Original scan preset selection routine.
        """
        presets_dict = self.tool.presets
        filtered = {}
        for key, preset in presets_dict.items():
            preset_iface = preset.get("interface", "").lower()
            if preset_iface == selected_interface.lower() or preset_iface == "any":
                filtered[key] = preset
        if not filtered:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available for this interface!")
            parent_win.refresh()
            parent_win.getch()
            return None
        menu_items = [f"[{key}] {preset.get('description', 'No description')}" for key, preset in filtered.items()]
        menu_items.append("[0] Back")
        menu_win = self.draw_menu(parent_win, "Select Scan Preset", menu_items)
        while True:
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch.isdigit():
                if ch == "0":
                    return None
                elif ch in filtered:
                    return filtered[ch]
            elif key == 27:
                return None

    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool submenu with top-level options.
        Pressing '0' or ESC returns to the main menu.
        """
        curses.curs_set(0)
        h, w = stdscr.getmaxyx()
        # Create a full-screen window for the submenu.
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        while True:
            menu_items = [
                "[1] Launch",
                "[2] View",
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
                self.select_scan(submenu_win)
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