import curses
import math
import logging

# ensure you import each tools module e.g. (from tools.hcxtool import hcxtool)
from config.constants import TOOL_PATHS
from utils.tool_registry import tool_registry
from tools.hcxtool import hcxtool

logging.basicConfig(level=logging.DEBUG)


def draw_menu(stdscr, menu_items):
    """
    Draws the menu items in a centered box.

    :param stdscr: The curses standard screen.
    :param menu_items: A list of strings representing menu options.
    """
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    box_height = len(menu_items) + 2
    box_width = max(len(item) for item in menu_items) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2

    # Draw box borders.
    for i in range(box_width):
        stdscr.addch(start_y, start_x + i, curses.ACS_HLINE)
        stdscr.addch(start_y + box_height - 1, start_x + i, curses.ACS_HLINE)
    for i in range(box_height):
        stdscr.addch(start_y + i, start_x, curses.ACS_VLINE)
        stdscr.addch(start_y + i, start_x + box_width - 1, curses.ACS_VLINE)
    stdscr.addch(start_y, start_x, curses.ACS_ULCORNER)
    stdscr.addch(start_y, start_x + box_width - 1, curses.ACS_URCORNER)
    stdscr.addch(start_y + box_height - 1, start_x, curses.ACS_LLCORNER)
    stdscr.addch(start_y + box_height - 1, start_x + box_width - 1, curses.ACS_LRCORNER)

    # Print the menu items.
    for idx, item in enumerate(menu_items):
        x = start_x + 2
        y = start_y + 1 + idx
        stdscr.addstr(y, x, item)
    stdscr.refresh()


def main_menu(stdscr) -> None:
    """
    Displays the main menu with two options: Tools and Exit.
    User can select using number keys or arrow keys.
    """
    curses.curs_set(0)
    menu_items = ["[1] Tools", "[0] Exit"]
    selected_idx = 0

    while True:
        draw_menu(stdscr, menu_items)
        key = stdscr.getch()
        if key in [curses.KEY_UP, ord('k')]:
            selected_idx = (selected_idx - 1) % len(menu_items)
        elif key in [curses.KEY_DOWN, ord('j')]:
            selected_idx = (selected_idx + 1) % len(menu_items)
        elif key in [curses.KEY_ENTER, 10, 13]:
            if selected_idx == 0:  # Tools
                tools_menu(stdscr)
            elif selected_idx == 1:  # Exit
                break
        # Also allow direct number key input:
        elif chr(key) in ['1', '0']:
            if chr(key) == '1':
                tools_menu(stdscr)
            elif chr(key) == '0':
                break


def tools_menu(stdscr) -> None:
    """
    Displays the tools menu.

    Lists registered tools (with numbers starting at 1) followed by a "[0] Back" option as the last item.
    Pressing a digit key immediately triggers the corresponding action (no Enter key needed).

    :param stdscr: The curses standard screen.
    """
    curses.curs_set(0)
    # Get tool names from the registry
    tool_names = tool_registry.get_tool_names()
    logging.debug("Tool registry contains: %s", tool_names)
    if not tool_names:
        tool_names = ["No tools registered"]

    # Build menu: options for tools (1..n), with Back as the last option
    menu_items = [f"[{idx}] {name}" for idx, name in enumerate(tool_names, start=1)]
    menu_items.append("[0] Back")
    draw_menu(stdscr, menu_items)

    while True:
        key = stdscr.getch()
        try:
            char = chr(key)
        except Exception:
            continue

        if char.isdigit():
            # the last option is always Back
            if char == "0":
                break
            else:
                num = int(char)
                if 1 <= num <= len(tool_names):
                    selected_tool = tool_names[num - 1]
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Selected tool: {selected_tool}")
                    stdscr.refresh()
                    curses.napms(1500)
                    try:
                        # Get the tool's base_dir from the TOOL_PATHS dictionary in config.constants
                        tool_path = TOOL_PATHS.get(selected_tool)
                        if not tool_path:
                            raise ValueError(f"No base_dir defined for {selected_tool} in constants.TOOLS")
                        # Instantiate the tool using its base_dir
                        tool_instance = tool_registry.instantiate_tool(selected_tool, base_dir=str(tool_path))
                        # Launch the tool-specific submenu.
                        tool_instance.submenu(stdscr)
                    except Exception as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Error launching tool {selected_tool}: {e}")
                        stdscr.refresh()
                        stdscr.getch()
                    break
        elif key == 27:  # Escape key to go back for hand havers
            break


if __name__ == "__main__":
    curses.wrapper(main_menu)
