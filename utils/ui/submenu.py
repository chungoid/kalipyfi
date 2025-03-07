# submenu.py
import curses
import logging

from utils import ipc
from config.constants import TOOL_PATHS
from common.process_manager import process_manager
from utils.tool_registry import tool_registry
from utils.helper import get_published_socket_path

socket_path = get_published_socket_path()

## using a self contained draw_menu rather than main_menu's global right now just for testing
## intend to switch to 1 global draw_menu that works across all submenus and main_menu

def draw_menu(stdscr, title, menu_items):
    stdscr.clear()
    stdscr.refresh()
    h, w = stdscr.getmaxyx()
    logging.debug(f"Terminal size: height={h}, width={w}")
    box_height = len(menu_items) + 4
    box_width = max(len(title), *(len(item) for item in menu_items)) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2
    if box_height <= 0 or box_width <= 0 or start_y < 0 or start_x < 0:
        logging.error("Invalid window dimensions in draw_menu.")
        return None
    win = curses.newwin(box_height, box_width, start_y, start_x)
    win.keypad(True)
    win.box()
    win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
    for idx, item in enumerate(menu_items):
        win.addstr(2 + idx, 2, item)
    win.refresh()
    return win

def exit_menu(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    menu_items = ["[1] Detach", "[2] Kill", "[0] Back"]
    title = "Exit Menu"
    menu_win = draw_menu(stdscr, title, menu_items)
    while True:
        key = menu_win.getch()
        try:
            ch = chr(key)
        except Exception:
            continue
        if ch == "1":
            message = {"action": "DETACH_UI"}
            response = ipc.send_ipc_command(message, socket_path)
            if response:
                stdscr.clear()
                stdscr.addstr(0, 0, "Detach command sent. Detaching UI...")
                stdscr.refresh()
                curses.napms(1000)
                break
        elif ch == "2":
            message = {"action": "KILL_UI"}
            response = ipc.send_ipc_command(message, socket_path)
            if response:
                stdscr.clear()
                stdscr.addstr(0, 0, "Kill command sent. Killing UI...")
                stdscr.refresh()
                process_manager.shutdown_all()
                curses.napms(1000)
                import sys
                sys.exit(0)
        elif ch == "0" or key == 27:
            break
    menu_win.erase()
    stdscr.clear()
    stdscr.refresh()

def tools_menu(stdscr):
    """Displays a menu for available tools and launches a tool's submenu when selected."""
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()

    tool_names = tool_registry.get_tool_names()
    if not tool_names:
        tool_names = ["No tools registered"]

    # Build numbered menu items and add a Back option.
    menu_items = [f"[{i+1}] {name}" for i, name in enumerate(tool_names)]
    menu_items.append("[0] Back")
    title = "Tools Menu"

    menu_win = draw_menu(stdscr, title, menu_items)
    while True:
        key = menu_win.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            menu_win = draw_menu(stdscr, title, menu_items)
            continue
        try:
            ch = chr(key)
        except Exception:
            continue

        if ch == "0":
            break
        elif ch.isdigit():
            num = int(ch)
            if 1 <= num <= len(tool_names):
                selected_tool = tool_names[num - 1]
                stdscr.clear()
                stdscr.addstr(0, 0, f"Selected tool: {selected_tool}", curses.A_BOLD)
                stdscr.refresh()
                curses.napms(1500)
                try:
                    tool_path = TOOL_PATHS.get(selected_tool)
                    if not tool_path:
                        raise ValueError(f"No base_dir defined for {selected_tool} in TOOL_PATHS")
                    tool_instance = tool_registry.instantiate_tool(selected_tool, base_dir=str(tool_path))
                    # Launch the tool's submenu.
                    tool_instance.submenu(stdscr)
                    stdscr.clear()
                    stdscr.refresh()
                except Exception as e:
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Error launching tool {selected_tool}: {e}", curses.A_BOLD)
                    stdscr.refresh()
                    stdscr.getch()
                break
    menu_win.erase()
    stdscr.clear()
    stdscr.refresh()

def utils_menu(stdscr):
    """Displays a simple Utils menu with status information."""
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()

    menu_items = ["[1] Status", "[0] Back"]
    title = "Utils Menu"
    menu_win = draw_menu(stdscr, title, menu_items)
    while True:
        key = menu_win.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            menu_win = draw_menu(stdscr, title, menu_items)
            continue
        try:
            ch = chr(key)
        except Exception:
            continue
        if ch == "0":
            break
        elif ch == "1":
            menu_win.erase()
            stdscr.clear()
            stdscr.refresh()
            debug_status_menu(stdscr)
            stdscr.clear()
            stdscr.refresh()
            menu_win = draw_menu(stdscr, title, menu_items)
    menu_win.erase()
    stdscr.clear()
    stdscr.refresh()

def debug_status_menu(stdscr):
    """Fetches and displays process status via IPC."""
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    title = "Status Report"
    # Send a status request via IPC.
    message = {"action": "DEBUG_STATUS"}
    response = ipc.send_ipc_command(message, socket_path)
    stdscr.clear()
    if response.get("status") == "DEBUG_STATUS_OK":
        report = response.get("report", "No report available.")
        stdscr.addstr(0, 0, "Process Status Report:", curses.A_BOLD)
        stdscr.addstr(1, 0, report)
    else:
        stdscr.addstr(0, 0, f"Error: {response.get('error', 'Unknown error')}", curses.A_BOLD)
    stdscr.addstr(curses.LINES - 1, 0, "Press any key to return...")
    stdscr.refresh()
    stdscr.getch()
    stdscr.clear()
    stdscr.refresh()
