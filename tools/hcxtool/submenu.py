import os
import curses
import logging
from pathlib import Path

# locals
from tools.helpers.wpasec import download_from_wpasec, upload_to_wpasec
from tools.submenu import BaseSubmenu

class HcxToolSubmenu(BaseSubmenu):
    def __init__(self, tool_instance):
        super().__init__(tool_instance)
        self.logger = logging.getLogger("HcxToolSubmenu")
        self.logger.debug("HcxToolSubmenu initialized.")

    def pre_launch_hook(self, parent_win) -> bool:
        selected_iface = self.select_interface(parent_win)
        if not selected_iface:
            self.logger.debug("pre_launch_hook: No interface selected; aborting launch.")
            return False
        self.tool.selected_interface = selected_iface
        self.logger.debug("pre_launch_hook: Selected interface: %s", selected_iface)
        return True

    def set_wpasec_key_menu(self, parent_win) -> None:
        while True:
            parent_win.clear()
            parent_win.refresh()
            parent_win.addstr(0, 0, "Enter new WPA-sec API key (or type 0 to cancel):")
            parent_win.refresh()
            curses.echo()
            new_key = parent_win.getstr(1, 0).decode("utf-8")
            curses.noecho()
            if new_key.strip() == "0":
                return
            try:
                self.tool.set_wpasec_key(new_key)
                parent_win.clear()
                parent_win.addstr(0, 0, "WPA-sec API key updated. Press any key to continue...")
                parent_win.refresh()
                parent_win.getch()
                return
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error updating WPA-sec key: {e}")
                parent_win.refresh()
                parent_win.getch()

    def upload(self, parent_win) -> None:
        while True:
            parent_win.clear()
            parent_win.refresh()
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
            parent_win.refresh()
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
                parent_win.addstr(row + 1, 0, "Press any key to retry upload menu, or 0 to go back...")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "0":
                        return
                except Exception:
                    return
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
                parent_win.addstr(2, 0, "Press any key to retry upload menu, or 0 to go back...")
                parent_win.refresh()
                key = parent_win.getch()
                try:
                    if chr(key) == "0":
                        return
                except Exception:
                    return

    def download(self, parent_win) -> None:
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
        menu_options = ["Set WPA-sec Key", "Upload", "Download", "Export Results"]
        while True:
            parent_win.clear()
            parent_win.refresh()
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
                parent_win.clear()
                parent_win.addstr(0, 0, "Exporting Results... please wait a few moments.")
                parent_win.refresh()
                self.tool.export_results()
                parent_win.clear()
                parent_win.addstr(0, 0, "Export complete. Spawn webserver to view results? (y/n): ")
                parent_win.refresh()
                try:
                    key = parent_win.getch()
                    ch = chr(key)
                except Exception:
                    ch = ''
                if ch.lower() == 'y':
                    self.open_results_webserver(parent_win)
                else:
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Export complete. Press any key to continue...")
                    parent_win.refresh()
                    parent_win.getch()
            parent_win.clear()
            parent_win.refresh()

    def utils_menu(self, parent_win) -> None:
        menu_options = self.get_utils_menu_options()  # e.g., ["WPASEC", "Setup Configs", "Open Results Webserver", "Kill Window"]
        while True:
            parent_win.clear()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == self.BACK_OPTION:
                break
            elif selection == "WPASEC":
                self.wpasec_menu(parent_win)
            elif selection == "Setup Configs":
                # Instead of duplicating code, call the helper from BaseSubmenu
                self.process_setup_configs_menu(parent_win)
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Kill Window":
                self.kill_background_window_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()

    def get_utils_menu_options(self) -> list:
        base_options = super().get_utils_menu_options()
        return ["WPASEC"] + base_options

    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool submenu using curses.
        Main options include:
          - Launch Scan
          - View Scans
          - Utils
          - Toggle Scrolling
          - Back
        """
        curses.curs_set(0)
        self.stdscr = stdscr
        self.setup_alert_window(stdscr)
        self.reset_connection_values()

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        base_menu = ["Launch Scan", "View Scans", "Utils"]
        while True:
            submenu_win.clear()
            submenu_win.refresh()
            selection = self.show_main_menu(submenu_win, base_menu, "hcxtool")
            if selection.lower() == "back":
                break
            elif selection == "Launch Scan":
                self.launch_scan(submenu_win)
            elif selection == "View Scans":
                self.view_scans(submenu_win)
            elif selection == "Utils":
                self.utils_menu(submenu_win)
            # clear the window before re-displaying the main menu
            submenu_win.clear()
            submenu_win.refresh()