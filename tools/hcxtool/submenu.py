import os
import yaml
import curses
import logging
from pathlib import Path
from typing import Any, List


# local
from utils.ipc_client import IPCClient
from tools.helpers.tool_utils import format_scan_display
from tools.helpers.webserver import start_webserver
from tools.helpers.wpasec import download_from_wpasec, upload_to_wpasec

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

        Each displayed option is prefixed with its number relative to that page.

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
            The selected option (the original string from menu_items), or "back" if cancelled.
        """
        h, w = parent_win.getmaxyx()
        # Reserve 6 lines for borders, title, and instructions.
        max_items = max(h - 6, 1)
        total_items = len(menu_items)
        total_pages = (total_items + max_items - 1) // max_items
        current_page = 0

        while True:
            start_index = current_page * max_items
            end_index = start_index + max_items
            page_items = menu_items[start_index:end_index]

            # Prefix each item with its number for the current page.
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
            # Otherwise, ignore and wait for a valid key.


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
        selection = self.draw_paginated_menu(parent_win, "Select Interface", available)
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
        # Build a list using the preset descriptions.
        menu_items = [preset.get("description", "No description") for _, preset in preset_list]
        selection = self.draw_paginated_menu(parent_win, "Select Scan Preset", menu_items)
        if selection == "back":
            return None
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
        Displays active scans using pagination and allows the user to choose one.
        After a scan is selected, a secondary menu is presented with options:
          1. Swap (send SWAP_SCAN command)
          2. Stop (send STOP_SCAN command)
          0. Cancel (return to scans list)
        """
        client = IPCClient()
        tool_name = getattr(self.tool, 'name', 'hcxtool')

        message = {"action": "GET_SCANS", "tool": tool_name}
        self.logger.debug(f"view_scans: Sending GET_SCANS for tool '{tool_name}'")
        response = client.send(message)
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

        try:
            selected_index = menu_items.index(selection)
        except ValueError:
            self.logger.error("Selected scan not found in list.")
            return

        selected_scan = scans[selected_index]

        # Present secondary menu: Swap, Stop, Cancel.
        parent_win.clear()
        secondary_menu = ["Swap", "Stop", "Cancel"]
        sec_menu_items = [f"[{i + 1}] {item}" for i, item in enumerate(secondary_menu)]
        sec_menu_win = self.draw_menu(parent_win, "Selected Scan Options", sec_menu_items)
        key = sec_menu_win.getch()
        try:
            ch = chr(key)
        except Exception:
            ch = ""
        if ch == "1":
            # Swap: send SWAP_SCAN
            new_title = f"{self.tool.selected_interface}_{self.tool.selected_preset.get('description', '')}"
            swap_message = {
                "action": "SWAP_SCAN",
                "tool": tool_name,
                "pane_id": selected_scan.get("pane_id"),
                "new_title": new_title
            }
            swap_response = client.send(swap_message)
            parent_win.clear()
            if swap_response.get("status") == "SWAP_SCAN_OK":
                parent_win.addstr(0, 0, "Scan swapped successfully!")
            else:
                error_text = swap_response.get("error", "Unknown error")
                parent_win.addstr(0, 0, f"Error swapping scan: {error_text}")
            parent_win.refresh()
            parent_win.getch()
        elif ch == "2":
            # Stop: send STOP_SCAN
            stop_message = {
                "action": "STOP_SCAN",
                "tool": tool_name,
                "pane_id": selected_scan.get("pane_id")
            }
            stop_response = client.send(stop_message)
            parent_win.clear()
            if stop_response.get("status") == "STOP_SCAN_OK":
                parent_win.addstr(0, 0, "Scan stopped successfully!")
            else:
                error_text = stop_response.get("error", "Unknown error")
                parent_win.addstr(0, 0, f"Error stopping scan: {error_text}")
            parent_win.refresh()
            parent_win.getch()
        else:
            # return to the scans list
            return


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


    def download(self, parent_win) -> None:
        """
        Handles the 'Download' option.
        Downloads data from WPA-sec using the API key and saves it as 'founds.txt'
        in the tool's results directory.
        """
        # Retrieve the API key from the tool's configuration
        api_key = self.tool.get_wpasec_api_key()
        logging.debug(f"api key: {api_key}")

        if not api_key:
            parent_win.clear()
            parent_win.addstr(0, 0, "No API key configured for WPA-sec download!")
            parent_win.refresh()
            parent_win.getch()
            return

        # Confirm download action with the user
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

        # Perform the download
        parent_win.clear()
        parent_win.addstr(0, 0, "Downloading founds from WPA-sec...")
        parent_win.refresh()
        results_dir = getattr(self.tool, "results_dir", "results")
        file_path = download_from_wpasec(self.tool, api_key, results_dir)

        # Show the result
        parent_win.clear()
        if file_path:
            parent_win.addstr(0, 0, f"Download complete. Saved to {file_path}")
        else:
            parent_win.addstr(0, 0, "Error downloading founds!")
        parent_win.refresh()
        parent_win.getch()


    def set_wpasec_key_menu(self, parent_win) -> None:
        """
        Prompts the user to enter a new WPA-sec API key and updates the configuration.
        If the key is too long to display, it wraps within the input field.
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

    def utils_menu(self, parent_win) -> None:
        """
        Displays a Utils submenu with options:
          - WPA-sec (contains all WPA-sec related functions)
          - Create Scan Profile
          - Edit Scan Profile
        (The "[0] Back" option is automatically added by draw_paginated_menu.)
        """
        menu_options = ["WPA-sec", "Create Scan Profile", "Edit Scan Profile"]

        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == "back":
                break
            elif selection == "WPA-sec":
                self.wpasec_menu(parent_win)
            elif selection == "Create Scan Profile":
                self.create_scan_profile_menu(parent_win)
            elif selection == "Edit Scan Profile":
                self.edit_scan_profile_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()


    def wpasec_menu(self, parent_win) -> None:
        """
        Displays a WPA-sec submenu with options:
          - Set WPA-sec Key
          - Upload
          - Download
          - Export Results
        (The "[0] Back" option is automatically added by draw_paginated_menu.)
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

    def create_scan_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to build a new scan profile based on a defaults YAML file and
        adds it to the tool's configuration. For each option in the defaults file:
          - If the default is null (indicating a boolean option), the user is prompted to enter
            't' (for true) or 'f' (for false).
          - Otherwise, the user is prompted to enter a value.
        """
        defaults_path = Path(self.tool.base_dir) / "configs" / "defaults.yaml"
        try:
            with defaults_path.open("r") as f:
                defaults_data = yaml.safe_load(f)
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error loading defaults.yaml: {e}")
            parent_win.refresh()
            parent_win.getch()
            return

        default_profile = defaults_data.get("scan_profile", {})
        if not default_profile:
            parent_win.clear()
            parent_win.addstr(0, 0, "No scan profile defaults found in defaults.yaml.")
            parent_win.refresh()
            parent_win.getch()
            return

        # Initialize new_profile with each key set to its default.
        new_profile = {}
        for opt_key, opt_data in default_profile.items():
            new_profile[opt_key] = opt_data.get("value", "")

        # Loop through each option individually using screen clearance.
        for opt_key, opt_data in default_profile.items():
            desc = opt_data.get("description", "")
            default_value = opt_data.get("value", "")
            parent_win.clear()
            if default_value is None:
                # Boolean option: prompt for t/f.
                prompt = f"Enable option '{opt_key}'? (t/f, default: f): "
            else:
                prompt = f"{opt_key} (default: {default_value}): "
            parent_win.addstr(0, 0, prompt)
            # Add a blank line before the description.
            parent_win.addstr(1, 0, "")
            parent_win.addstr(2, 0, f"Description: {desc}")
            parent_win.addstr(4, 0, "Enter value (or press Enter to accept default):")
            parent_win.refresh()
            curses.echo()
            try:
                user_input = parent_win.getstr(5, 0).decode("utf-8").strip()
            except Exception:
                user_input = ""
            curses.noecho()
            # For boolean options, interpret input accordingly.
            if default_value is None:
                # If user types 't' (case-insensitive), store the flag (opt_key); otherwise, leave blank.
                new_val = opt_key if user_input.lower() == 't' else ""
            else:
                new_val = user_input if user_input != "" else default_value
            new_profile[opt_key] = new_val

        # Prompt for a profile ID/name.
        parent_win.clear()
        parent_win.addstr(0, 0, "Enter a name/ID for this new scan profile (leave blank to cancel):")
        parent_win.refresh()
        curses.echo()
        try:
            profile_id = parent_win.getstr(1, 0).decode("utf-8").strip()
        except Exception:
            profile_id = ""
        curses.noecho()
        if profile_id == "":
            parent_win.clear()
            parent_win.addstr(0, 0, "No profile ID provided. Cancelling.")
            parent_win.refresh()
            parent_win.getch()
            return

        # Review screen: show only non-blank options.
        parent_win.clear()
        parent_win.addstr(0, 0, f"New Scan Profile ({profile_id}):")
        row = 1
        for key, value in new_profile.items():
            if value not in ("", None):
                parent_win.addstr(row, 0, f"{key}: {value}")
                row += 1
                # If we reach near the bottom, pause.
                if row >= parent_win.getmaxyx()[0] - 3:
                    parent_win.addstr(row, 0, "Press any key to continue...")
                    parent_win.refresh()
                    parent_win.getch()
                    parent_win.clear()
                    row = 0
        # Final choice: save or cancel.
        parent_win.addstr(row, 0, "1: Save    2: Cancel")
        parent_win.refresh()
        choice = parent_win.getch()
        if chr(choice).lower() != '1':
            parent_win.clear()
            parent_win.addstr(0, 0, "Profile creation cancelled.")
            parent_win.refresh()
            parent_win.getch()
            return

        # Determine the next available preset key.
        try:
            existing_keys = list(self.tool.presets.keys())
            next_key = str(max([int(k) for k in existing_keys]) + 1) if existing_keys else "1"
        except Exception:
            next_key = "1"
        # Filter new_profile to include only non-blank values.
        filtered_profile = {k: v for k, v in new_profile.items() if v not in ("", None)}
        self.tool.presets[next_key] = {
            "description": profile_id,
            "options": filtered_profile
        }
        try:
            self.tool.update_presets_in_config(self.tool.presets)
            parent_win.clear()
            parent_win.addstr(0, 0, "New scan profile created and saved. Press any key to continue...")
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error saving profile: {e}")
        parent_win.refresh()
        parent_win.getch()


    def edit_scan_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to select an existing scan profile to edit, then allows the user to
        select individual options (from a paginated menu) to edit.
        """
        # List current presets.
        presets_dict = self.tool.presets
        if not presets_dict:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available to edit!")
            parent_win.refresh()
            parent_win.getch()
            return

        try:
            sorted_keys = sorted(presets_dict.keys(), key=lambda k: int(k))
        except Exception:
            sorted_keys = sorted(presets_dict.keys())
        preset_list = [(key, presets_dict[key]) for key in sorted_keys]
        menu_items = [preset.get("description", "No description") for _, preset in preset_list]

        selection = self.draw_paginated_menu(parent_win, "Edit Scan Profile", menu_items)
        if selection == "back":
            return
        # Find the selected preset.
        selected_key = None
        selected_preset = None
        for key, preset in preset_list:
            if preset.get("description", "No description") == selection:
                selected_key = key
                selected_preset = preset
                break
        if not selected_preset:
            parent_win.clear()
            parent_win.addstr(0, 0, "Selected preset not found!")
            parent_win.refresh()
            parent_win.getch()
            return

        # Work on a copy of the options.
        options = selected_preset.get("options", {}).copy()
        while True:
            # Build a list of option strings with current values.
            option_items = []
            for k, v in options.items():
                option_items.append(f"{k}: {v}")
            # Append a "Finish Editing" option.
            option_items.append("Finish Editing")
            selection = self.draw_paginated_menu(parent_win, "Select Option to Edit", option_items)
            if selection == "back" or selection == "Finish Editing":
                break
            # Find the option key from the selection (split at ':')
            try:
                key_to_edit = selection.split(":", 1)[0].strip()
            except Exception:
                continue
            # Prompt the user for a new value for this option.
            parent_win.clear()
            prompt = f"Enter new value for {key_to_edit} (current: {options.get(key_to_edit)}) :"
            parent_win.addstr(0, 0, prompt)
            parent_win.refresh()
            curses.echo()
            try:
                new_val = parent_win.getstr(1, 0).decode("utf-8").strip()
            except Exception:
                new_val = ""
            curses.noecho()
            # Update the option if user provided a value.
            if new_val != "":
                options[key_to_edit] = new_val
            # Clear the screen before redisplaying the options.
            parent_win.clear()
            parent_win.refresh()

        # Allow the user to also edit the preset description.
        parent_win.clear()
        current_desc = selected_preset.get("description", "")
        parent_win.addstr(0, 0, f"Current profile description: {current_desc}")
        parent_win.addstr(1, 0, "Enter new description (or press Enter to keep current):")
        parent_win.refresh()
        curses.echo()
        try:
            new_desc = parent_win.getstr(2, 0).decode("utf-8").strip()
        except Exception:
            new_desc = ""
        curses.noecho()
        if new_desc == "":
            new_desc = current_desc

        # Review the updated profile.
        parent_win.clear()
        parent_win.addstr(0, 0, "Review updated scan profile:")
        row = 1
        parent_win.addstr(row, 0, f"Description: {new_desc}")
        row += 1
        for key, val in options.items():
            parent_win.addstr(row, 0, f"{key}: {val}")
            row += 1
            if row >= parent_win.getmaxyx()[0] - 2:
                parent_win.addstr(row, 0, "Press any key to continue...")
                parent_win.refresh()
                parent_win.getch()
                parent_win.clear()
                row = 0
        parent_win.addstr(row, 0, "Press 'y' to confirm changes, any other key to cancel.")
        parent_win.refresh()
        confirmation = parent_win.getch()
        if chr(confirmation).lower() != 'y':
            parent_win.clear()
            parent_win.addstr(0, 0, "Profile edit cancelled.")
            parent_win.refresh()
            parent_win.getch()
            return

        # Update the preset in memory.
        self.tool.presets[selected_key] = {
            "description": new_desc,
            "options": options
        }

        # Save the updated presets to the configuration file.
        try:
            self.tool.update_presets_in_config(self.tool.presets)
            parent_win.clear()
            parent_win.addstr(0, 0, "Profile updated and saved. Press any key to continue...")
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error saving profile: {e}")
        parent_win.refresh()
        parent_win.getch()


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

        # Main submenu options
        menu_items = ["Launch Scan", "View Scans", "Utils", "Back"]
        numbered_menu = [f"[{i + 1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            menu_win = self.draw_menu(submenu_win, "HCXTool Submenu", numbered_menu)
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