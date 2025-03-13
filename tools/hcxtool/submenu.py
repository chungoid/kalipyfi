import os
import yaml
import curses
import logging
from pathlib import Path
from typing import Any, Union

# local imports
from tools.helpers.webserver import start_webserver
from tools.helpers.wpasec import download_from_wpasec, upload_to_wpasec

from tools.submenu import BaseSubmenu

class HcxToolSubmenu(BaseSubmenu):
    def __init__(self, tool_instance):
        super().__init__(tool_instance)
        self.logger = logging.getLogger("HcxToolSubmenu")
        self.logger.debug("HcxToolSubmenu initialized.")

    def pre_launch_hook(self, parent_win) -> bool:
        """
        Before launching a scan, require selection of an interface.
        If no interface is chosen, abort the launch.
        """
        selected_iface = self.select_interface(parent_win)
        if not selected_iface:
            self.logger.debug("pre_launch_hook: No interface selected; aborting launch.")
            return False
        self.tool.selected_interface = selected_iface
        self.logger.debug("pre_launch_hook: Selected interface: %s", selected_iface)
        return True

    def set_wpasec_key_menu(self, parent_win) -> None:
        """
        Prompts the user to enter a new WPA-sec API key and updates the tool configuration.
        """
        parent_win.clear()
        parent_win.addstr(0, 0, "Enter new WPA-sec API key:")
        parent_win.refresh()
        curses.echo()
        new_key = parent_win.getstr(1, 0).decode("utf-8")
        curses.noecho()
        try:
            self.tool.set_wpasec_key(new_key)
            parent_win.clear()
            parent_win.addstr(0, 0, "WPA-sec API key updated. Press any key to continue...")
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error updating WPA-sec key: {e}")
        parent_win.refresh()
        parent_win.getch()

    def upload(self, parent_win) -> None:
        """
        Lists available .pcapng files from the results directory and allows the user to upload one or all.
        """
        results_dir = getattr(self.tool, "results_dir", "results")
        api_key = self.tool.get_wpasec_api_key()
        try:
            files = [f for f in os.listdir(results_dir) if f.endswith(".pcapng")]
        except Exception as e:
            self.logger.error("upload: Error accessing results directory: %s", e)
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
            row = 1
            for file in files:
                file_path = Path(results_dir) / file
                self.logger.debug("upload: Uploading %s...", file_path)
                success = upload_to_wpasec(self.tool, file_path, api_key)
                if success:
                    parent_win.addstr(row, 0, f"Uploaded {file} successfully.")
                else:
                    parent_win.addstr(row, 0, f"Failed to upload {file}.")
                row += 1
            parent_win.addstr(row + 1, 0, "Press any key to return to the upload menu...")
            parent_win.refresh()
            parent_win.getch()
            self.upload(parent_win)
        else:
            file_path = Path(results_dir) / selection
            parent_win.addstr(0, 0, f"Uploading {selection}...")
            parent_win.refresh()
            curses.napms(1500)
            success = upload_to_wpasec(self.tool, file_path, api_key)
            if success:
                parent_win.addstr(1, 0, f"Uploaded {selection} successfully.")
            else:
                parent_win.addstr(1, 0, f"Failed to upload {selection}.")
            parent_win.addstr(2, 0, "Press any key to return to the upload menu...")
            parent_win.refresh()
            parent_win.getch()
            self.upload(parent_win)

    def download(self, parent_win) -> None:
        """
        Downloads data from WPA-sec using the API key and saves it as 'founds.txt'
        in the tool's results directory.
        """
        api_key = self.tool.get_wpasec_api_key()
        self.logger.debug("download: API key: %s", api_key)
        if not api_key:
            parent_win.clear()
            parent_win.addstr(0, 0, "No API key configured for WPA-sec download!")
            parent_win.refresh()
            parent_win.getch()
            return

        parent_win.clear()
        parent_win.addstr(0, 0, "Download founds from WPA-sec? (y/n)")
        parent_win.refresh()
        try:
            key = parent_win.getch()
            ch = chr(key)
        except Exception:
            return
        if ch.lower() != 'y':
            return

        parent_win.clear()
        parent_win.addstr(0, 0, "Downloading founds from WPA-sec...")
        parent_win.refresh()
        results_dir = getattr(self.tool, "results_dir", "results")
        file_path = download_from_wpasec(self.tool, api_key, results_dir)
        parent_win.clear()
        if file_path:
            parent_win.addstr(0, 0, f"Download complete. Saved to {file_path}")
        else:
            parent_win.addstr(0, 0, "Error downloading founds!")
        parent_win.refresh()
        parent_win.getch()

    def wpasec_menu(self, parent_win) -> None:
        """
        Displays a WPA-sec submenu with options for setting the API key, uploading,
        downloading, and exporting results.
        """
        menu_options = ["Set WPA-sec Key", "Upload", "Download", "Export Results"]
        while True:
            selection = self.draw_paginated_menu(parent_win, "WPA-sec", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "Set WPA-sec Key":
                self.set_wpasec_key_menu(parent_win)
            elif selection == "Upload":
                self.upload(parent_win)
            elif selection == "Download":
                self.download(parent_win)
            elif selection == "Export Results":
                parent_win.addstr(0, 0, "Exporting Results... please wait a few moments.")
                self.tool.export_results()
                curses.napms(2500)
                parent_win.refresh()
                parent_win.clear()
                parent_win.addstr(0, 0, "Export complete. Spawn webserver to view results? (y/n): ")
                parent_win.refresh()
                try:
                    key = parent_win.getch()
                    ch = chr(key)
                except Exception:
                    ch = ''
                if ch.lower() == 'y':
                    start_webserver(self.tool.results_dir)
                    parent_win.clear()
                    parent_win.addstr(0, 0,
                        "Webserver started on port 8000.\nVisit http://<device-ip>:8000/map.html\nPress any key to continue...")
                    parent_win.refresh()
                    parent_win.getch()
                else:
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Export complete. Press any key to continue...")
                    parent_win.refresh()
                    parent_win.getch()
            parent_win.clear()
            parent_win.refresh()

    def utils_menu(self, parent_win) -> None:
        """
        Displays a Utils submenu with options for WPA-sec functions, creating and editing scan profiles.
        """
        menu_options = ["WPA-sec", "Create Scan Profile", "Edit Scan Profile"]
        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "WPA-sec":
                self.wpasec_menu(parent_win)
            elif selection == "Create Scan Profile":
                self.create_preset_profile_menu(parent_win)
            elif selection == "Edit Scan Profile":
                self.edit_preset_profile_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()

    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool Submenu.
        Main options are:
          1. Launch Scan
          2. View Scans
          3. Utils
          0. Back
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

        menu_items = ["Launch Scan", "View Scans", "Utils", "Back"]
        numbered_menu = [f"[{i+1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            menu_win = self.draw_menu(submenu_win, "hcxtool", numbered_menu)
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
