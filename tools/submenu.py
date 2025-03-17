import curses
import logging
import socket
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
        self.debug_win = None

    def create_debug_window(self, stdscr, height: int = 4) -> any:
        """
        Creates a debug window that occupies the bottom 'height' lines
        of the entire screen (stdscr).
        """
        max_y, max_x = stdscr.getmaxyx()
        debug_win = stdscr.derwin(height, max_x, max_y - height, 0)
        debug_win.clear()
        debug_win.refresh()
        return debug_win

    def show_debug_info(self, debug_lines: list) -> None:
        """
        Uses self.debug_win to display the provided debug_lines.
        If self.debug_win is not set, does nothing.
        """
        if self.debug_win is None:
            return
        self.debug_win.clear()
        for idx, line in enumerate(debug_lines):
            try:
                self.debug_win.addstr(idx, 0, line)
            except Exception:
                # In case the window is too small.
                pass
        self.debug_win.refresh()

    def draw_menu(self, parent_win, title: str, menu_items: List[str]) -> Any:
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
        h, w = parent_win.getmaxyx()
        max_items = max(h - 6, 1)
        total_items = len(menu_items)
        total_pages = (total_items + max_items - 1) // max_items
        current_page = 0

        while True:
            start_index = current_page * max_items
            end_index = start_index + max_items
            page_items = menu_items[start_index:end_index]

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
                return BACK_OPTION
            elif ch.isdigit():
                selection = int(ch)
                if 1 <= selection <= len(page_items):
                    return page_items[selection - 1]

    def select_interface(self, parent_win) -> Union[str, None]:
        """
        Presents a paginated menu of available interfaces from self.tool.interfaces["wlan"].
        Returns the selected interface name or BACK_OPTION/None if cancelled.
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
        if selection == BACK_OPTION:
            return None
        return selection

    def select_preset(self, parent_win) -> Union[dict, str]:
        """
        Generic preset selection: displays presets from self.tool.presets and returns
        the selected preset dictionary.
        """
        presets = self.tool.presets
        if not presets:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available!")
            parent_win.refresh()
            parent_win.getch()
            return BACK_OPTION

        try:
            sorted_keys = sorted(presets.keys(), key=lambda k: int(k))
        except Exception:
            sorted_keys = sorted(presets.keys())
        preset_list = [(key, presets[key]) for key in sorted_keys]
        menu_items = [preset.get("description", "No description") for _, preset in preset_list]
        selection = self.draw_paginated_menu(parent_win, "Select Scan Preset", menu_items)
        if selection == BACK_OPTION:
            return BACK_OPTION
        for key, preset in preset_list:
            if preset.get("description", "No description") == selection:
                self.logger.debug("Selected preset: %s", preset)
                return preset
        return BACK_OPTION

    def create_preset_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to build a new scan profile based on defaults in defaults.yaml,
        then adds it to the tool's configuration.
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

        new_profile = {opt_key: opt_data.get("value", "") for opt_key, opt_data in default_profile.items()}

        for opt_key, opt_data in default_profile.items():
            desc = opt_data.get("description", "")
            default_value = opt_data.get("value", "")
            parent_win.clear()
            prompt = (f"Enable option '{opt_key}'? (t/f, default: f): "
                      if default_value is None else f"{opt_key} (default: {default_value}): ")
            parent_win.addstr(0, 0, prompt)
            parent_win.addstr(2, 0, f"Description: {desc}")
            parent_win.addstr(4, 0, "Enter value (or press Enter to accept default):")
            parent_win.refresh()
            curses.echo()
            try:
                user_input = parent_win.getstr(5, 0).decode("utf-8").strip()
            except Exception:
                user_input = ""
            curses.noecho()
            new_val = opt_key if default_value is None and user_input.lower() == 't' else (user_input if user_input != "" else default_value)
            new_profile[opt_key] = new_val

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

        parent_win.clear()
        parent_win.addstr(0, 0, f"New Profile ({profile_id}):")
        row = 1
        for key, value in new_profile.items():
            if value not in ("", None):
                parent_win.addstr(row, 0, f"{key}: {value}")
                row += 1
                if row >= parent_win.getmaxyx()[0] - 3:
                    parent_win.addstr(row, 0, "Press any key to continue...")
                    parent_win.refresh()
                    parent_win.getch()
                    parent_win.clear()
                    row = 0
        parent_win.addstr(row, 0, "1: Save    2: Cancel")
        parent_win.refresh()
        choice = parent_win.getch()
        if chr(choice).lower() != '1':
            parent_win.clear()
            parent_win.addstr(0, 0, "Profile creation cancelled.")
            parent_win.refresh()
            parent_win.getch()
            return

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


    def pre_launch_hook(self, parent_win) -> bool:
        """
        Hook for performing any tool-specific actions before launching a scan.
        Default implementation does nothing and returns True.
        """
        return True

    def launch_scan(self, parent_win) -> None:
        """
        Generic launch scan: executes pre-launch steps (via pre_launch_hook),
        then selects a preset and launches the scan by calling self.tool.run().
        """
        if not self.pre_launch_hook(parent_win):
            self.logger.debug("pre_launch_hook signaled to abort scan launch.")
            return

        self.tool.selected_preset = None
        self.tool.preset_description = None

        selected_preset = self.select_preset(parent_win)
        if selected_preset == BACK_OPTION:
            self.logger.debug("launch_scan: No preset selected; aborting scan launch.")
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
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error launching scan: {e}")
            parent_win.refresh()
            parent_win.getch()

    def view_scans(self, parent_win) -> None:
        """
        Generic view_scans method for displaying active scans and allowing the user to take actions.
        """
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
            curses.napms(1500)  # pause (1.5 seconds)
            return

        # format each scan for display
        menu_items = [format_scan_display(scan) for scan in scans]
        selection = self.draw_paginated_menu(parent_win, "Active Scans", menu_items)
        if selection == "back":
            return

        try:
            selected_index = menu_items.index(selection)
        except ValueError:
            self.logger.error("view_scans: Selected scan not found in list.")
            return

        selected_scan = scans[selected_index]

        # secondary menu for actions
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
            # Swap: change pane title.
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
        elif ch == "2":
            # stop scan
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
        else:
            # Cancel – simply return.
            return
        parent_win.refresh()
        curses.napms(1500)  # 1.5s pause then return

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

    def utils_menu(self, parent_win) -> None:
        """
        Presents a generic utilities menu.

        Options include:
          - Setup Configs: Opens a submenu for configuration setup.
          - Open Results Webserver: Launches the webserver to display results.
          - Kill Window: Opens a submenu to kill one or all background windows.

        Subclasses can override get_utils_menu_options() to add or change options.

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
        menu_options = self.get_utils_menu_options()
        while True:
            selection = self.draw_paginated_menu(parent_win, "Utils", menu_options)
            if selection.lower() == BACK_OPTION:
                break
            elif selection == "Setup Configs":
                # display a secondary menu for configuration setup
                config_options = ["Create Scan Profile", "Edit Scan Profile", "Edit Interfaces"]
                sub_selection = self.draw_paginated_menu(parent_win, "Setup Configs", config_options)
                if sub_selection.lower() != BACK_OPTION:
                    if sub_selection == "Create Scan Profile":
                        self.create_preset_profile_menu(parent_win)
                    elif sub_selection == "Edit Scan Profile":
                        self.edit_preset_profile_menu(parent_win)
                    elif sub_selection == "Edit Interfaces":
                        self.edit_interfaces_menu(parent_win)
            elif selection == "Open Results Webserver":
                self.open_results_webserver(parent_win)
            elif selection == "Kill Window":
                self.kill_background_window_menu(parent_win)
            parent_win.clear()
            parent_win.refresh()

    def edit_preset_profile_menu(self, parent_win) -> None:
        """
        Prompts the user to select an existing scan profile to edit, then allows editing of its options.
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

        selection = self.draw_paginated_menu(parent_win, "Edit Profile", menu_items)
        if selection == BACK_OPTION:
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
            return

        options = selected_preset.get("options", {}).copy()
        while True:
            option_items = [f"{k}: {v}" for k, v in options.items()]
            option_items.append("Finish Editing")
            selection = self.draw_paginated_menu(parent_win, "Select Option to Edit", option_items)
            if selection == BACK_OPTION or selection == "Finish Editing":
                break
            try:
                key_to_edit = selection.split(":", 1)[0].strip()
            except Exception:
                continue
            parent_win.clear()
            prompt = f"Enter new value for {key_to_edit} (current: {options.get(key_to_edit)}):"
            parent_win.addstr(0, 0, prompt)
            parent_win.refresh()
            curses.echo()
            try:
                new_val = parent_win.getstr(1, 0).decode("utf-8").strip()
            except Exception:
                new_val = ""
            curses.noecho()
            if new_val != "":
                options[key_to_edit] = new_val
            parent_win.clear()
            parent_win.refresh()

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

        parent_win.clear()
        parent_win.addstr(0, 0, "Review updated profile:")
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

        self.tool.presets[selected_key] = {"description": new_desc, "options": options}
        try:
            self.tool.update_presets_in_config(self.tool.presets)
            parent_win.clear()
            parent_win.addstr(0, 0, "Profile updated and saved. Press any key to continue...")
            self.tool.reload_config()
        except Exception as e:
            parent_win.clear()
            parent_win.addstr(0, 0, f"Error saving profile: {e}")
        parent_win.refresh()
        parent_win.getch()

    def open_results_webserver(self, parent_win, port: int = 8000) -> None:
        """
        Starts a webserver serving the tool's results directory.
        The server will host the directory at http://<device-ip>:<port>/<toolname>.

        :param: parent_win
        :param: port:
            port of the webserver

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

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
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

        # option 1 is kill all background, 2+ are individual windows
        menu_items = ["Kill All"]
        menu_items.extend([format_scan_display(scan) for scan in scans])
        selection = self.draw_paginated_menu(parent_win, "Kill Background Windows", menu_items)
        if selection == "back":
            return

        try:
            selected_index = menu_items.index(selection)
        except ValueError:
            self.logger.error("kill_windows_menu: Selected option not found in list.")
            return

        parent_win.clear()
        if selected_index == 0:
            # kill all bg windows
            for scan in scans:
                pane_id = scan.get("pane_id")
                kill_message = {"action": "KILL_WINDOW", "tool": tool_name, "pane_id": pane_id}
                kill_response = client.send(kill_message)
                if not kill_response.get("status", "").startswith("KILL_WINDOW_OK"):
                    error_text = kill_response.get("error", "Unknown error")
                    self.logger.error("Error killing window (pane %s): %s", pane_id, error_text)
            parent_win.addstr(0, 0, "All background windows killed successfully!")
        else:
            # kill a single window
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

    def edit_interfaces_menu(self, parent_win) -> None:
        """
        This method retrieves the 'interfaces' section from the tool's configuration file,
        displays the available interface keys (e.g., wlan, bluetooth) or, if the key maps to a list,
        displays the individual interface entries (by their 'name'). For the selected interface entry,
        it iterates over its attributes (such as name, description, locked), prompts the user to change
        each value (or leave it unchanged), and saves the updated configuration using update_yaml_value().

        :param parent_win: The curses window used for displaying the menu.
        :return: None
        """
        import yaml
        from tools.helpers.tool_utils import update_yaml_value

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

        # build a menu of interface keys from the interfaces dictionary
        interface_keys = list(interfaces.keys())
        selection = self.draw_paginated_menu(parent_win, "Select Interface Category", interface_keys)
        if selection.lower() == "back":
            return

        selected_key = selection.strip()
        interface_config = interfaces.get(selected_key)
        # determine list or dict (future-proof for new interface keys besides wlan)
        if isinstance(interface_config, list):
            # build list by interface names
            list_menu = [iface.get("name", f"Interface {i}") for i, iface in enumerate(interface_config)]
            selection2 = self.draw_paginated_menu(parent_win, f"Select Entry for '{selected_key}'", list_menu)
            if selection2.lower() == "back":
                return
            try:
                selected_index = list_menu.index(selection2)
            except Exception as e:
                self.logger.error("Error processing selection: %s", e)
                return
            chosen_interface = interface_config[selected_index]
            key_path_prefix = ["interfaces", selected_key, str(selected_index)]
        elif isinstance(interface_config, dict):
            chosen_interface = interface_config
            key_path_prefix = ["interfaces", selected_key]
        else:
            parent_win.clear()
            parent_win.addstr(0, 0, "Interfaces format unrecognized.")
            parent_win.refresh()
            parent_win.getch()
            return

        # iterate over interface attributes
        for attr, current_value in chosen_interface.items():
            parent_win.clear()
            prompt = f"Enter new value for '{attr}' (current: {current_value}) or leave blank to keep: "
            parent_win.addstr(0, 0, prompt)
            parent_win.refresh()
            try:
                new_val_bytes = parent_win.getstr(1, 0)
            except Exception:
                new_val_bytes = b""
            new_val = new_val_bytes.decode("utf-8").strip() if new_val_bytes else ""
            if new_val != "":
                try:
                    # update config file
                    update_yaml_value(config_file, key_path_prefix + [attr], new_val)
                    self.logger.info(f"Updated {selected_key}[{attr}] to {new_val}")
                    # update the in-memory config (so edits following can see it)
                    chosen_interface[attr] = new_val
                except Exception as e:
                    self.logger.error(f"Error updating {selected_key}[{attr}]: {e}")
        parent_win.clear()
        parent_win.addstr(0, 0, "Interface configuration updated. Press any key to continue.")
        parent_win.refresh()
        parent_win.getch()


    def __call__(self, stdscr) -> None:
        """
        Launches the HCXTool Submenu.
        Main options: Launch Scan, Utils, Back.
        """
        curses.curs_set(0)
        self.tool.selected_preset = None
        self.tool.preset_description = None

        h, w = stdscr.getmaxyx()
        submenu_win = curses.newwin(h, w, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        menu_items = ["Launch Scan", "Utils", "Back"]
        numbered_menu = [f"[{i+1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        while True:
            menu_win = self.draw_menu(submenu_win, f"{self.tool.name}", numbered_menu)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue
            if ch == "1":
                self.launch_scan(submenu_win)
            elif ch == "2":
                self.utils_menu(submenu_win)
            elif ch == "0" or key == 27:
                break
            submenu_win.clear()
            submenu_win.refresh()


# Constant for "back" selection
BACK_OPTION = "back"

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
