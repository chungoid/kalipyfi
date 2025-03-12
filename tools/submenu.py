# tools/submenu.py (BaseSubmenu)
import curses
import logging
from typing import List, Any, Union


class BaseSubmenu:
    def __init__(self, tool_instance):
        """
        Base submenu for all tools.
        """
        self.tool = tool_instance
        self.logger = logging.getLogger("BaseSubmenu")
        self.logger.debug("BaseSubmenu initialized.")

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
                return "back"
            elif ch.isdigit():
                selection = int(ch)
                if 1 <= selection <= len(page_items):
                    return page_items[selection - 1]

    def select_preset(self, parent_win) -> Union[dict,str]:
        """
        Generic preset selection: displays presets from self.tool.presets and returns
        the selected preset dictionary.
        Tools can override this method if needed.
        """
        presets = self.tool.presets
        if not presets:
            parent_win.clear()
            parent_win.addstr(0, 0, "No presets available!")
            parent_win.refresh()
            parent_win.getch()
            return "back"

        try:
            sorted_keys = sorted(presets.keys(), key=lambda k: int(k))
        except Exception:
            sorted_keys = sorted(presets.keys())
        preset_list = [(key, presets[key]) for key in sorted_keys]
        menu_items = [preset.get("description", "No description") for _, preset in preset_list]
        selection = self.draw_paginated_menu(parent_win, "Select Scan Preset", menu_items)
        if selection == "back":
            return "back"
        for key, preset in preset_list:
            if preset.get("description", "No description") == selection:
                self.logger.debug("Selected preset: %s", preset)
                return preset
        return "back"

    def pre_launch_hook(self, parent_win) -> bool:
        """
        Hook for performing any tool-specific actions before launching a scan.
        Default implementation does nothing and returns True.
        Override in subclasses as needed.
        """
        return True

    def launch_scan(self, parent_win) -> None:
        """
        Generic launch scan: executes pre-launch steps (via pre_launch_hook),
        then selects a preset and launches the scan by calling self.tool.run().
        Tools can override this method entirely if necessary.
        """
        if not self.pre_launch_hook(parent_win):
            self.logger.debug("pre_launch_hook signaled to abort scan launch.")
            return

        self.tool.selected_preset = None
        self.tool.preset_description = None

        selected_preset = self.select_preset(parent_win)
        if selected_preset == "back":
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

    def utils_menu(self, parent_win) -> None:
        """
        Default utilities menu. This is a placeholder that displays a message.
        Tool-specific submenus can override this method to add custom utilities.
        """
        parent_win.clear()
        parent_win.addstr(0, 0, "No utilities available. Press any key to return.")
        parent_win.refresh()
        parent_win.getch()

    def __call__(self, stdscr) -> None:
        """
        Default __call__ implementation that launches the submenu.
        Tools can override this method if additional custom behavior is needed.
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
