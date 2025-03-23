import curses
import logging
import socket
import time
import yaml
from pathlib import Path
from typing import List, Any, Union

# locals
from utils.ipc_client import IPCClient
from tools.helpers.tool_utils import format_scan_display


class BaseSubmenu:
    def __init__(self, tool_instance):
        """
        Base submenu for all tools.
        """
        self.tool = tool_instance
        self.logger = logging.getLogger("BaseSubmenu")
        self.logger.debug("BaseSubmenu initialized.")
        self.tool.ui_instance.register_active_submenu(self)
        self.alert_queue = []
        self.alert_win = None
        self.alerts_enabled = True
        self.debug_win = None
        self.BACK_OPTION = "back"

    def create_debug_window(self, stdscr, height: int = 4) -> any:
        max_y, max_x = stdscr.getmaxyx()
        debug_win = stdscr.derwin(height, max_x, max_y - height, 0)
        debug_win.clear()
        debug_win.refresh()
        return debug_win

    def show_debug_info(self, debug_lines: list) -> None:
        if self.debug_win is None:
            return
        self.debug_win.clear()
        for idx, line in enumerate(debug_lines):
            try:
                self.debug_win.addstr(idx, 0, line)
            except Exception:
                pass
        self.debug_win.refresh()

    def draw_menu(self, parent_win, title: str, menu_items: List[str]) -> Any:
        parent_win.clear()
        h, w = parent_win.getmaxyx()
        box_height = len(menu_items) + 4
        content_width = max(len(title), *(len(item) for item in menu_items))
        # Limit box width to available width with some margin
        box_width = min(content_width + 4, w - 2)
        start_y = (h - box_height) // 2
        start_x = (w - box_width) // 2
        # Use a derived window so that the absolute screen isn’t affected
        menu_win = parent_win.derwin(box_height, box_width, start_y, start_x)
        menu_win.keypad(True)
        menu_win.box()
        menu_win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
        for idx, item in enumerate(menu_items):
            menu_win.addstr(2 + idx, 2, item)
        menu_win.refresh()
        return menu_win

    def draw_paginated_menu(self, parent_win, title: str, menu_items: List[str]) -> str:
        h, w = parent_win.getmaxyx()
        max_items = max(h - 6, 1)
        total_items = len(menu_items)
        total_pages = (total_items + max_items - 1) // max_items
        current_page = 0

        while True:
            start_index = current_page * max_items
            end_index = start_index + max_items
            page_items = menu_items[start_index:end_index]
            display_items = [f"[{i + 1}] {option}" for i, option in enumerate(page_items)]
            if total_pages > 1:
                pagination_info = f"Pg. {current_page + 1}/{total_pages} (n:ext, p:rev)"
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
                return self.BACK_OPTION
            elif ch.isdigit():
                selection = int(ch)
                if 1 <= selection <= len(page_items):
                    return page_items[selection - 1]

    def toggle_alerts(self):
        """
        Toggles the state of alerts and immediately refreshes the alert display.
        When enabled, it displays alerts stored in the local alert queue.
        When disabled, it clears the alert window.
        """
        self.alerts_enabled = not self.alerts_enabled
        state = "enabled" if self.alerts_enabled else "disabled"
        self.logger.info(f"Alerts have been {state}.")

        if self.alerts_enabled:
            self.display_alert(self.alert_queue)
        else:
            if self.alert_win:
                self.alert_win.erase()
                self.alert_win.box()
                self.alert_win.refresh()

        return state

    def setup_alert_window(self, stdscr):
        """
        Creates a persistent alert window using the main stdscr.
        The alert window will use the full available height and one-third of the available width.
        This should be called when curses is properly initialized.
        """
        h, w = stdscr.getmaxyx()
        alert_height = h
        alert_width = w // 3  # Use one-third of the width.
        self.alert_win = curses.newwin(alert_height, alert_width, 0, 0)
        self.alert_win.box()
        self.alert_win.nodelay(True)
        self.alert_win.refresh()

    def handle_alert(self, alert_data):
        """
        Callback method to process alerts from the global ScapyManager.
        Converts the incoming alert into a unified dictionary format and adds it to the alert queue.
        """
        self.logger.info("Received alert: %s", alert_data)
        if isinstance(alert_data, dict) and alert_data.get("action") == "NETWORK_FOUND":
            message = f"{alert_data.get('ssid', 'Unknown')} ({int(time.time() - alert_data.get('timestamp', time.time()))}s)"
            alert = {
                "action": alert_data["action"],
                "message": message,
                "expiration": time.time() + 120  # keep for 2m
            }
        else:
            alert = {"message": str(alert_data), "expiration": time.time() + 120}
        self.alert_queue.append(alert)
        self.display_alert(self.alert_queue)


    def add_alert(self, alert_msg: str, duration: float = 3):
        """
        Appends an alert message (as a dict) to the alert queue with a set expiration time.
        """
        expiration = time.time() + duration
        alert = {"message": alert_msg, "expiration": expiration}
        self.alert_queue.append(alert)
        self.update_alert_window()

    def update_alert_window(self):
        if not self.alert_win:
            return

        current_time = time.time()
        # remove after 120s
        self.alert_queue = [alert for alert in self.alert_queue if current_time - alert.created_at < 120]

        messages = []
        for alert in self.alert_queue:
            # show bssid and time since alert formed
            if alert.tool == "pyficonnect" and "bssid" in alert.data:
                bssid = alert.data["bssid"]
                elapsed = current_time - alert.created_at
                messages.append(f"{bssid} ({int(elapsed)}s)")
            else:
                messages.append("Unknown alert")

        final_message = "\n".join(messages)

        # Redraw the alert window
        h, w = self.alert_win.getmaxyx()
        self.alert_win.erase()
        self.alert_win.box()
        lines = final_message.splitlines()
        if len(lines) > (h - 2):
            lines = lines[-(h - 2):]
        for row, line in enumerate(lines, start=1):
            try:
                self.alert_win.addstr(row, 2, line[:w - 4])
            except curses.error:
                pass
        self.alert_win.refresh()

    def display_alert(self, alerts: list):
        """
        Processes a list of alerts and formats them for display.
        Alerts may be:
          - full alert dicts from ScapyManager (with 'action' and 'timestamp')
          - display dicts with 'message' and 'expiration'
        """
        formatted_messages = []
        for alert in alerts:
            if isinstance(alert, dict):
                if alert.get("action") == "NETWORK_FOUND" and "ssid" in alert and "timestamp" in alert:
                    ssid = alert["ssid"]
                    time_passed = time.time() - alert["timestamp"]
                    formatted_messages.append(f"{ssid} ({int(time_passed)}s)")
                elif "message" in alert:
                    formatted_messages.append(alert["message"])
                else:
                    self.logger.warning("Unrecognized alert format: %s", alert)
            else:
                formatted_messages.append(str(alert))

        final_message = "\n".join(formatted_messages)
        self._update_alert_window_from_message(final_message)

    def _update_alert_window_from_message(self, message: str):
        if not self.alert_win:
            return

        h, w = self.alert_win.getmaxyx()
        self.alert_win.erase()
        self.alert_win.box()
        lines = message.splitlines() or [message]
        if len(lines) > (h - 2):
            lines = lines[-(h - 2):]
        for row, line in enumerate(lines, start=1):
            try:
                self.alert_win.addstr(row, 2, line[:w - 4])
            except curses.error:
                pass
        self.alert_win.refresh()

    #############################
    ##### MAIN MENU OPTIONS #####
    #############################
    def select_interface(self, parent_win) -> Union[str, None]:
        from tools.helpers.tool_utils import get_available_wireless_interfaces
        while True:
            connected = get_available_wireless_interfaces(self.logger)
            # get config.yaml interfaces
            interfaces = self.tool.interfaces.get("wlan", [])
            # filter found interfaces and display only connected ones
            available = [iface.get("name") for iface in interfaces if iface.get("name") in connected]
            if not available:
                parent_win.clear()
                parent_win.addstr(0, 0,
                                  f"No interfaces from {self.tool.config_file} found."
                                  f"\n\nTip: Use the Utils submenu to edit tool-specific configs.")
                parent_win.refresh()
                parent_win.getch()
                return None
            parent_win.erase()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Select Interface", available)
            parent_win.erase()
            parent_win.refresh()
            if selection == self.BACK_OPTION:
                return None
            return selection

    def select_preset(self, parent_win) -> Union[dict, str]:
        """
        Select preset scan build from tools config file

        :param parent_win:
        :return:
        """
        while True:
            presets = self.tool.presets
            if not presets:
                parent_win.clear()
                parent_win.addstr(0, 0, "No presets available!")
                parent_win.refresh()
                parent_win.getch()
                return self.BACK_OPTION
            try:
                sorted_keys = sorted(presets.keys(), key=lambda k: int(k))
            except Exception:
                sorted_keys = sorted(presets.keys())
            preset_list = [(key, presets[key]) for key in sorted_keys]
            menu_items = [preset.get("description", "No description") for _, preset in preset_list]
            selection = self.draw_paginated_menu(parent_win, "Select Scan Preset", menu_items)
            if selection == self.BACK_OPTION:
                return self.BACK_OPTION
            for key, preset in preset_list:
                if preset.get("description", "No description") == selection:
                    self.logger.debug("Selected preset: %s", preset)
                    return preset
            # if nothing matches, loop again

    def pre_launch_hook(self, parent_win) -> bool:
        """
        Hook for performing any tool-specific actions before launching a scan.
        Default implementation does nothing and returns True.

        :return: bool
        """
        return True

    def launch_scan(self, parent_win) -> None:
        """
        Generic launch scan: executes pre-launch steps (via pre_launch_hook),
        then selects a preset and launches the scan by calling self.tool.run().

        :return: None
        """
        if not self.pre_launch_hook(parent_win):
            self.logger.debug("pre_launch_hook signaled to abort scan launch.")
            return
        self.tool.selected_preset = None
        self.tool.preset_description = None
        while True:
            selected_preset = self.select_preset(parent_win)
            if selected_preset == self.BACK_OPTION:
                return
            self.tool.selected_preset = selected_preset
            self.tool.preset_description = selected_preset.get("description", "")
            parent_win.clear()
            confirm_msg = f"Launching scan with preset: {self.tool.preset_description}"
            parent_win.addstr(0, 0, confirm_msg)
            parent_win.refresh()
            curses.napms(1500)
            try:
                self.tool.run()
                break  # Scan launched successfully; exit loop.
            except Exception as e:
                parent_win.clear()
                parent_win.addstr(0, 0, f"Error launching scan: {e}")
                parent_win.refresh()
                parent_win.getch()
                break

    def view_scans(self, parent_win) -> None:
        """
        Generic view_scans method for displaying active scans and allowing the user to take actions.

        :return: None
        """
        while True:
            client = IPCClient()
            tool_name = getattr(self.tool, 'name', 'tool')
            message = {"action": "GET_SCANS", "tool": tool_name}
            self.logger.debug("view_scans: Sending GET_SCANS for tool '%s'", tool_name)
            response = client.send(message)
            scans = response.get("scans", [])
            parent_win.clear()
            if not scans:
                parent_win.addstr(0, 0, "No active scans found!")
                parent_win.refresh()
                curses.napms(1500)
                return
            menu_items = [format_scan_display(scan) for scan in scans]
            selection = self.draw_paginated_menu(parent_win, "Active Scans", menu_items)
            if selection == "back":
                return
            try:
                selected_index = menu_items.index(selection)
            except ValueError:
                self.logger.error("view_scans: Selected scan not found in list.")
                continue
            selected_scan = scans[selected_index]
            while True:
                parent_win.clear()
                secondary_menu = ["Swap", "Stop", "Cancel"]
                sec_menu_items = [f"[{i + 1}] {item}" for i, item in enumerate(secondary_menu)]
                sec_menu_win = self.draw_menu(parent_win, "Selected Scan Options", sec_menu_items)
                key = sec_menu_win.getch()
                try:
                    ch = chr(key)
                except Exception:
                    ch = ""
                parent_win.clear()
                if ch == "1":
                    new_title = f"{self.tool.selected_interface}_{self.tool.selected_preset.get('description', '')}"
                    swap_message = {
                        "action": "SWAP_SCAN",
                        "tool": tool_name,
                        "pane_id": selected_scan.get("pane_id"),
                        "new_title": new_title
                    }
                    swap_response = client.send(swap_message)
                    if swap_response.get("status", "").startswith("SWAP_SCAN_OK"):
                        parent_win.addstr(0, 0, "Scan swapped successfully!")
                    else:
                        error_text = swap_response.get("error", "Unknown error")
                        parent_win.addstr(0, 0, f"Error swapping scan: {error_text}")
                    parent_win.refresh()
                    curses.napms(1500)
                    break
                elif ch == "2":
                    stop_message = {
                        "action": "STOP_SCAN",
                        "tool": tool_name,
                        "pane_id": selected_scan.get("pane_id")
                    }
                    stop_response = client.send(stop_message)
                    if stop_response.get("status", "").startswith("STOP_SCAN_OK"):
                        parent_win.addstr(0, 0, "Scan stopped successfully!")
                    else:
                        error_text = stop_response.get("error", "Unknown error")
                        parent_win.addstr(0, 0, f"Error stopping scan: {error_text}")
                    parent_win.refresh()
                    curses.napms(1500)
                    break
                else:
                    break  # Cancel or unrecognized; exit secondary loop.
            parent_win.clear()
            parent_win.addstr(0, 0, "Press any key to refresh scans menu, or 0 to go back.")
            parent_win.refresh()
            key = parent_win.getch()
            try:
                if chr(key) == "0":
                    return
            except Exception:
                return

    #################################
    ##### UTILS SUBMENU METHODS #####
    #################################
    def get_utils_menu_options(self) -> list:
        """
        Returns a list of default utility menu options.

        These options will be used in the utilities menu and can be extended or overridden
        by subclasses.

        :return: A list of strings representing the menu options.
        """
        return ["Setup Configs", "Open Results Webserver", "Kill Window"]

    def process_setup_configs_menu(self, parent_win) -> None:
        """
        Presents a nested submenu for setup configurations.
        This method displays the "Setup Configs" options in a loop
        and calls the corresponding method for each selection.
        """
        config_options = ["Create Scan Profile", "Edit Scan Profile", "Edit Interfaces"]
        while True:
            parent_win.clear()
            parent_win.refresh()
            sub_selection = self.draw_paginated_menu(parent_win, "Setup Configs", config_options)
            if sub_selection.lower() == self.BACK_OPTION:
                # User selected 'back' so exit the nested submenu.
                break
            elif sub_selection == "Create Scan Profile":
                self.create_preset_profile_menu(parent_win)
            elif sub_selection == "Edit Scan Profile":
                self.edit_preset_profile_menu(parent_win)
            elif sub_selection == "Edit Interfaces":
                self.edit_interfaces_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()

    def utils_menu(self, parent_win) -> None:
        """
        Presents a generic utilities menu with nested loops so that screen contents
        are cleared between layers and the 'back' option returns only one level.

        Options include:
          - Setup Configs: Opens a nested submenu for configuration setup.
          - Open Results Webserver: Launches the webserver to display results.
          - Kill Window: Opens a submenu to kill background windows.

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
        menu_options = self.get_utils_menu_options()
        while True:
            parent_win.clear()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == self.BACK_OPTION:
                break
            elif selection == "Setup Configs":
                self.process_setup_configs_menu(parent_win)
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Kill Window":
                self.kill_background_window_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()

    def create_preset_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to build a new scan profile based on defaults in defaults.yaml,
        then adds it to the tool's configuration.
        Uses nested loops so that each stage clears the screen and the user can cancel
        at any layer.
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

        # edit each attribute in the default profile
        new_profile = {}
        for opt_key, opt_data in default_profile.items():
            desc = opt_data.get("description", "")
            default_value = opt_data.get("value", "")
            # nested loop to avoid tiling
            while True:
                parent_win.clear()
                if default_value is None:
                    prompt = f"Enable option '{opt_key}'? (t/f, default: f): "
                else:
                    prompt = f"{opt_key} (default: {default_value}): "
                parent_win.addstr(0, 0, prompt)
                parent_win.addstr(2, 0, f"Description: {desc}")
                parent_win.addstr(4, 0, "Enter value (or press Enter to accept default).")
                parent_win.addstr(5, 0, "Type 0 to cancel profile creation.")
                parent_win.refresh()
                curses.echo()
                try:
                    user_input = parent_win.getstr(6, 0).decode("utf-8").strip()
                except Exception:
                    user_input = ""
                curses.noecho()
                if user_input == "0":
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Profile creation cancelled.")
                    parent_win.refresh()
                    parent_win.getch()
                    return
                if default_value is None:
                    # no defaults are boolean, "" empty strings require string entry from user
                    new_val = opt_key if user_input.lower() == "t" else ""
                else:
                    new_val = user_input if user_input != "" else default_value
                new_profile[opt_key] = new_val
                break  # proceed to next attribute

        # prompt for profile ID
        while True:
            parent_win.clear()
            parent_win.addstr(0, 0, "Enter a name/ID for this new profile (leave blank to cancel):")
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
            else:
                break  # valid profile_id provided

        # preview and confirmation loop
        while True:
            parent_win.clear()
            parent_win.addstr(0, 0, f"New Profile ({profile_id}):")
            row = 1
            for key, value in new_profile.items():
                if value not in ("", None):
                    if row >= parent_win.getmaxyx()[0] - 3:
                        parent_win.addstr(row, 0, "Press any key to continue preview...")
                        parent_win.refresh()
                        parent_win.getch()
                        parent_win.clear()
                        row = 1
                        parent_win.addstr(0, 0, f"New Profile ({profile_id}):")
                    parent_win.addstr(row, 0, f"{key}: {value}")
                    row += 1
            parent_win.addstr(row, 0, "Press 1 to Save, 2 to Cancel, or 3 to Re-edit attributes:")
            parent_win.refresh()
            choice = parent_win.getch()
            if chr(choice).lower() == "1":
                break  # save
            elif chr(choice).lower() == "2":
                parent_win.clear()
                parent_win.addstr(0, 0, "Profile creation cancelled.")
                parent_win.refresh()
                parent_win.getch()
                return
            elif chr(choice) == "3":
                # restart the creation process
                return self.create_preset_profile_menu(parent_win)
            # else loop back for confirmation

        # save the new profile.
        try:
            existing_keys = list(self.tool.presets.keys())
            next_key = str(max([int(k) for k in existing_keys]) + 1) if existing_keys else "1"
        except Exception:
            next_key = "1"
        filtered_profile = {k: v for k, v in new_profile.items() if v not in ("", None)}
        self.tool.presets[next_key] = {"description": profile_id, "options": filtered_profile}
        try:
            self.tool.update_presets_in_config(self.tool.presets)
            parent_win.clear()
            self.tool.reload_config()
            parent_win.addstr(0, 0, "New profile created and saved. Press any key to continue...")
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error saving profile: {e}")
        parent_win.refresh()
        parent_win.getch()

    def edit_preset_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to select an existing scan profile to edit, then allows editing of its options.
        Uses nested loops so that the user can back out of the option editing and reselect a profile.
        """
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

        # Outer loop: select a preset to edit.
        while True:
            parent_win.clear()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Edit Profile", menu_items)
            if selection == self.BACK_OPTION:
                return
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
                continue

            options = selected_preset.get("options", {}).copy()
            # inner loop: editing
            while True:
                parent_win.clear()
                parent_win.refresh()
                option_items = [f"{k}: {v}" for k, v in options.items()]
                option_items.append("Finish Editing")
                sub_selection = self.draw_paginated_menu(parent_win, "Select Option to Edit", option_items)
                if sub_selection == self.BACK_OPTION or sub_selection == "Finish Editing":
                    break  # exit after editing
                try:
                    key_to_edit = sub_selection.split(":", 1)[0].strip()
                except Exception:
                    continue
                # new value prompt
                while True:
                    parent_win.clear()
                    prompt = f"Enter new value for {key_to_edit} (current: {options.get(key_to_edit)}):"
                    parent_win.addstr(0, 0, prompt)
                    parent_win.addstr(2, 0, "Press [Enter] to keep current value or type a new value.")
                    parent_win.addstr(3, 0, "Press [0] to cancel editing this option.")
                    parent_win.refresh()
                    curses.echo()
                    try:
                        new_val_bytes = parent_win.getstr(4, 0)
                    except Exception:
                        new_val_bytes = b""
                    curses.noecho()
                    new_val = new_val_bytes.decode("utf-8").strip() if new_val_bytes else ""
                    if new_val == "0":
                        break
                    # if blank, keep current
                    if new_val != "":
                        options[key_to_edit] = new_val
                    break  # proceed to next option

            # after editing, prompt confirm changes
            parent_win.clear()
            parent_win.addstr(0, 0, f"Current profile description: {selected_preset.get('description', '')}")
            parent_win.addstr(1, 0, "Enter new description (or press Enter to keep current):")
            parent_win.refresh()
            curses.echo()
            try:
                new_desc = parent_win.getstr(2, 0).decode("utf-8").strip()
            except Exception:
                new_desc = ""
            curses.noecho()
            if new_desc == "":
                new_desc = selected_preset.get("description", "")

            parent_win.clear()
            parent_win.addstr(0, 0, "Review updated profile:")
            row = 1
            parent_win.addstr(row, 0, f"Description: {new_desc}")
            row += 1
            for k, v in options.items():
                parent_win.addstr(row, 0, f"{k}: {v}")
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
            if chr(confirmation).lower() == 'y':
                self.tool.presets[selected_key] = {"description": new_desc, "options": options}
                try:
                    self.tool.reload_config()
                    parent_win.clear()
                    parent_win.addstr(0, 0, "Profile updated and saved. Press any key to continue...")
                    self.tool.reload_config()
                except Exception as e:
                    parent_win.clear()
                    parent_win.addstr(0, 0, f"Error saving profile: {e}")
                parent_win.refresh()
                parent_win.getch()
                return
            else:
                parent_win.clear()
                parent_win.addstr(0, 0, "Profile edit cancelled. Press any key to re-select a profile.")
                parent_win.refresh()
                parent_win.getch()
                # loop-back to re-display selection

    def open_results_webserver(self, parent_win, port: int = 8000) -> None:
        """
        Starts a webserver serving the tool's results directory.
        The server will host the directory at http://<device-ip>:<port>/<toolname>.

        :param parent_win: The curses window used for displaying the menu.
        :param port: Port the webserver will run on.
        :return: None
        """
        from tools.helpers.webserver import start_webserver
        start_webserver(self.tool.results_dir, port=port)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        finally:
            s.close()
        url = f"http://{local_ip}:{port}/{self.tool.name}"
        parent_win.clear()
        parent_win.addstr(0, 0, f"Webserver started at: {url}")
        parent_win.addstr(1, 0, "Press any key to continue...")
        parent_win.refresh()
        parent_win.getch()

    def kill_background_window_menu(self, parent_win) -> None:
        """
        Displays a menu of active background windows for the current tool and allows the user to kill them.

        Expected request and behavior:
          - Retrieves active scans using the GET_SCANS IPC action.
          - Option 1 in the menu is "Kill All", which will send a KILL_WINDOW command for every background window.
          - Options 2 and onward list individual background windows (formatted via format_scan_display)
            for which the user can select to kill that specific window.

        :param parent_win:
            The curses window used for displaying the menu.
        :return: None
        """
        while True:
            client = IPCClient()
            tool_name = getattr(self.tool, 'name', 'tool')
            message = {"action": "GET_SCANS", "tool": tool_name}
            self.logger.debug("kill_windows_menu: Sending GET_SCANS for tool '%s'", tool_name)
            response = client.send(message)
            scans = response.get("scans", [])
            parent_win.clear()
            if not scans:
                parent_win.addstr(0, 0, "No active background windows found!")
                parent_win.refresh()
                curses.napms(1500)
                return
            menu_items = ["Kill All"] + [format_scan_display(scan) for scan in scans]
            selection = self.draw_paginated_menu(parent_win, "Kill Background Windows", menu_items)
            if selection == "back":
                return
            try:
                selected_index = menu_items.index(selection)
            except ValueError:
                self.logger.error("kill_windows_menu: Selected option not found in list.")
                continue
            parent_win.clear()
            if selected_index == 0:
                for scan in scans:
                    pane_id = scan.get("pane_id")
                    kill_message = {"action": "KILL_WINDOW", "tool": tool_name, "pane_id": pane_id}
                    kill_response = client.send(kill_message)
                    if not kill_response.get("status", "").startswith("KILL_WINDOW_OK"):
                        error_text = kill_response.get("error", "Unknown error")
                        self.logger.error("Error killing window (pane %s): %s", pane_id, error_text)
                parent_win.addstr(0, 0, "All background windows killed successfully!")
            else:
                scan = scans[selected_index - 1]
                pane_id = scan.get("pane_id")
                kill_message = {"action": "KILL_WINDOW", "tool": tool_name, "pane_id": pane_id}
                kill_response = client.send(kill_message)
                if kill_response.get("status", "").startswith("KILL_WINDOW_OK"):
                    parent_win.addstr(0, 0, f"Window for pane {pane_id} killed successfully!")
                else:
                    error_text = kill_response.get("error", "Unknown error")
                    parent_win.addstr(0, 0, f"Error killing window for pane {pane_id}: {error_text}")
            parent_win.refresh()
            curses.napms(1500)
            parent_win.clear()
            parent_win.addstr(0, 0, "Press any key to refresh kill windows menu, or 0 to go back.")
            parent_win.refresh()
            key = parent_win.getch()
            try:
                if chr(key) == "0":
                    return
            except Exception:
                return

    def edit_interfaces_menu(self, parent_win) -> None:
        """
        Retrieves the 'interfaces' section from the tool's configuration file,
        displays the available interface keys (e.g., wlan, bluetooth) or, if the key maps to a list,
        displays the individual interface entries (by their 'name'). For the selected interface entry,
        iterates over its attributes and prompts the user to change each value (or leave it unchanged),
        then saves the updated configuration.
        """
        from tools.helpers.tool_utils import update_yaml_value, get_all_connected_interfaces
        import yaml
        while True:
            config_file = self.tool.config_file
            try:
                with config_file.open("r") as f:
                    config = yaml.safe_load(f) or {}
            except Exception as e:
                self.logger.error(f"Error loading configuration from {config_file}: {e}")
                return

            interfaces = config.get("interfaces", {})
            if not interfaces:
                parent_win.clear()
                parent_win.addstr(0, 0, "No interfaces found in configuration.")
                parent_win.refresh()
                parent_win.getch()
                return

            interface_keys = list(interfaces.keys())
            parent_win.erase()
            parent_win.refresh()
            selection = self.draw_paginated_menu(parent_win, "Select Category", interface_keys)
            if selection.lower() == "back":
                return
            selected_key = selection.strip()
            interface_config = interfaces.get(selected_key)
            if isinstance(interface_config, list):
                # Get only the interface names that are currently connected.
                connected = get_all_connected_interfaces(self.logger)
                list_menu = [iface.get("name", f"Interface {i}")
                             for i, iface in enumerate(interface_config)
                             if iface.get("name") in connected]
                # Append an option to allow adding a new interface.
                add_option = "Add New Interface"
                list_menu.append(add_option)
                parent_win.erase()
                parent_win.refresh()
                selection2 = self.draw_paginated_menu(parent_win, f"Select Entry for '{selected_key}'", list_menu)
                if selection2.lower() == "back":
                    continue  # Return to category selection.
                if selection2 == add_option:
                    self.add_new_interface_for_category(parent_win, selected_key)
                    # Reload configuration and loop back.
                    try:
                        with config_file.open("r") as f:
                            config = yaml.safe_load(f) or {}
                    except Exception as e:
                        self.logger.error(f"Error reloading configuration: {e}")
                        return
                    interfaces = config.get("interfaces", {})
                    continue

                try:
                    selected_index = list_menu.index(selection2)
                except Exception as e:
                    self.logger.error("Error processing selection: %s", e)
                    continue
                # Map the selection back to the full interface_config list.
                # Because list_menu is filtered, we need to find the matching entry.
                chosen_interface = None
                for iface in interface_config:
                    name = iface.get("name")
                    if name in connected and name == selection2:
                        chosen_interface = iface
                        break
                if chosen_interface is None:
                    self.logger.error("Selected interface not found in the configuration.")
                    continue
                key_path_prefix = ["interfaces", selected_key, str(interface_config.index(chosen_interface))]
            elif isinstance(interface_config, dict):
                chosen_interface = interface_config
                key_path_prefix = ["interfaces", selected_key]
            else:
                parent_win.clear()
                parent_win.addstr(0, 0, "Interfaces format unrecognized.")
                parent_win.refresh()
                parent_win.getch()
                return

            # Loop over each attribute for editing.
            for attr, current_value in chosen_interface.items():
                while True:
                    parent_win.erase()
                    parent_win.refresh()
                    prompt = (
                        f"Enter new value for '{attr}' (current: {current_value})\n"
                        "Press [Enter] to keep the current value, or type a new value to update."
                    )
                    parent_win.addstr(0, 0, prompt)
                    parent_win.refresh()
                    curses.echo()
                    try:
                        input_bytes = parent_win.getstr(4, 0)
                    except Exception:
                        input_bytes = b""
                    curses.noecho()
                    user_input = input_bytes.decode("utf-8").strip() if input_bytes else ""
                    new_val = current_value if user_input == "" else user_input
                    try:
                        update_yaml_value(config_file, key_path_prefix + [attr], new_val)
                        self.logger.info(f"Updated {selected_key}[{attr}] to {new_val}")
                        chosen_interface[attr] = new_val
                    except Exception as e:
                        self.logger.error(f"Error updating {selected_key}[{attr}]: {e}")
                    break  # Proceed to next attribute.

            parent_win.erase()
            parent_win.addstr(0, 0, "Interface configuration updated. Press any key to continue.")
            parent_win.refresh()
            parent_win.getch()
            return

    def add_new_interface_for_category(self, parent_win, category: str) -> None:
        """
        Prompts the user to add a new interface value for the given category (e.g., 'wlan')
        and updates the configuration file accordingly. Prompts for description, locked (true/false),
        and name. When prompting for the interface name, it displays the currently connected interfaces.
        """
        from tools.helpers.tool_utils import update_yaml_value, get_available_wireless_interfaces
        config_file = self.tool.config_file

        # load current config
        try:
            with config_file.open("r") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error(f"Error loading configuration from {config_file}: {e}")
            return

        # ensure the category exists and is a list
        if "interfaces" not in config:
            config["interfaces"] = {}
        if category not in config["interfaces"] or not isinstance(config["interfaces"][category], list):
            config["interfaces"][category] = []

        # prompt for description
        parent_win.erase()
        parent_win.addstr(0, 0, f"Enter interface description for '{category}':")
        parent_win.refresh()
        curses.echo()
        try:
            description = parent_win.getstr(1, 0).decode("utf-8").strip()
        except Exception:
            description = ""
        curses.noecho()
        if not description:
            parent_win.erase()
            parent_win.addstr(0, 0, "No description entered. Press any key to return.")
            parent_win.refresh()
            parent_win.getch()
            return

        # get currently connected interfaces and display them in the prompt
        connected = get_available_wireless_interfaces(self.logger)
        available_str = ", ".join(connected) if connected else "None"
        parent_win.erase()
        prompt = (f"Enter interface name for '{category}' (e.g., wlan4):\n"
                  f"Currently Available to Device: {available_str}")
        parent_win.addstr(0, 0, prompt)
        parent_win.refresh()
        curses.echo()
        try:
            name = parent_win.getstr(2, 0).decode("utf-8").strip()
        except Exception:
            name = ""
        curses.noecho()
        if not name:
            parent_win.erase()
            parent_win.addstr(0, 0, "No interface name entered. Press any key to return.")
            parent_win.refresh()
            parent_win.getch()
            return

        # prompt for locked status
        parent_win.erase()
        parent_win.addstr(0, 0, "Set Lock status: (true/false) [default false]:")
        parent_win.refresh()
        curses.echo()
        try:
            locked_str = parent_win.getstr(1, 0).decode("utf-8").strip().lower()
        except Exception:
            locked_str = ""
        curses.noecho()
        locked = True if locked_str == "true" else False

        # build the new interface entry
        new_entry = {"description": description, "name": name, "locked": locked}
        current_list = config["interfaces"][category]
        new_list = current_list + [new_entry]

        # use the update_yaml_value helper to update the entire list
        key_path = ["interfaces", category]
        try:
            update_yaml_value(config_file, key_path, new_list)
            parent_win.erase()
            parent_win.addstr(0, 0, f"Interface '{name}' added successfully. Press any key to continue.")
            parent_win.refresh()
            parent_win.getch()
            self.logger.info(
                f"Added new interface '{name}' under category '{category}' with description '{description}' and locked={locked}.")
        except Exception as e:
            parent_win.erase()
            parent_win.addstr(0, 0, f"Error saving configuration: {e}")
            parent_win.refresh()
            parent_win.getch()
            self.logger.error(f"Error updating configuration file {config_file}: {e}")

    def show_main_menu(self, submenu_win, base_menu_items: List[str], title: str) -> str:
        client = IPCClient()
        while True:
            state_message = {"action": "COPY_MODE", "copy_mode_action": "get_copy_mode_state"}
            state_response = client.send(state_message)
            scrolling_state = False
            if state_response.get("status") == "COPY_MODE_STATE":
                scrolling_state = state_response.get("copy_mode_enabled", False)
            toggle_scrolling_label = f"Scrolling ({'on' if scrolling_state else 'off'})"

            # prepare label
            toggle_alert_label = f"Alerts ({'on' if self.alerts_enabled else 'off'})"

            # build full menu
            full_menu = base_menu_items.copy()
            try:
                utils_index = full_menu.index("Utils")
                full_menu.insert(utils_index + 1, toggle_scrolling_label)
                full_menu.insert(utils_index + 2, toggle_alert_label)
            except ValueError:
                full_menu.append(toggle_scrolling_label)
                full_menu.append(toggle_alert_label)

            selection = self.draw_paginated_menu(submenu_win, title, full_menu)
            if selection.lower() == "back":
                return "back"
            elif selection.startswith("Scrolling"):
                toggle_message = {"action": "COPY_MODE", "copy_mode_action": "toggle"}
                toggle_response = client.send(toggle_message)
                if toggle_response.get("status", "").startswith("COPY_MODE"):
                    new_state = toggle_response.get("copy_mode_enabled", False)
                    submenu_win.clear()
                    submenu_win.addstr(0, 0, f"Scrolling {'enabled' if new_state else 'disabled'}!")
                    submenu_win.refresh()
                    curses.napms(1500)
                else:
                    error_text = toggle_response.get("error", "Unknown error")
                    submenu_win.clear()
                    submenu_win.addstr(0, 0, f"Error toggling scrolling: {error_text}")
                    submenu_win.refresh()
                    curses.napms(1500)
                continue
            elif selection.startswith("Alerts"):
                # toggle the alert popup state
                new_state = self.toggle_alerts()  # change state
                submenu_win.clear()
                submenu_win.refresh()
                continue
            else:
                return selection

    ##########################
    ##### HELPER METHODS #####
    ##########################
    def reset_connection_values(self):
        """
        Resets the connection-related selections to ensure a fresh start.
        """
        self.tool.selected_interface = None
        self.tool.selected_network = None
        self.tool.network_password = None

    def __call__(self, stdscr) -> None:
        curses.curs_set(0)
        self.tool.selected_preset = None
        self.tool.preset_description = None
        self.tool.reload_config(self)
        self.stdscr = stdscr
        h, w = stdscr.getmaxyx()

        # Setup the alert window on the left (one-third of the screen)
        self.setup_alert_window(stdscr)
        alert_width = w // 3

        # Create a submenu window that occupies the rest of the screen
        submenu_win = curses.newwin(h, w - alert_width, 0, alert_width)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        base_menu_items = ["Launch Scan", "Utils"]
        title = getattr(self.tool, "name", "Menu")

        while True:
            selection = self.show_main_menu(submenu_win, base_menu_items, title)
            if selection.lower() == "back":
                break
            elif selection == "Launch Scan":
                self.launch_scan(submenu_win)
            elif selection == "Utils":
                self.utils_menu(submenu_win)
            # Only clear the submenu window (not affecting the alert window)
            submenu_win.clear()
            submenu_win.refresh()
            alerts = self.tool.ui_instance.alerts.get(self.tool.name, [])
            self.display_alert(alerts)

        self.tool.ui_instance.unregister_active_submenu()
        self.logger.debug("Active submenu unregistered in __call__ exit.")


def display_debug_info(win, debug_lines: list) -> None:
    """
    Clears the given window and prints each debug line.
    This function is used to display real-time debugging information.
    """
    win.clear()
    for idx, line in enumerate(debug_lines):
        try:
            win.addstr(idx, 0, line)
        except Exception:
            # In case the window is too small
            pass
    win.refresh()
