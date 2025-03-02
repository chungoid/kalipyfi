import curses
import logging
import os
import time
from logging.handlers import QueueListener

from common.logging_setup import get_log_queue, worker_configurer, configure_listener_handlers
from config.constants import TOOL_PATHS, DEFAULT_SOCKET_PATH
from utils import ipc
#from utils.tool_registry import tool_registry
#from tools.hcxtool import hcxtool


log_queue = get_log_queue()
worker_configurer(log_queue)

def draw_menu(stdscr, title, menu_items):
    h, w = stdscr.getmaxyx()
    box_height = len(menu_items) + 4
    box_width = max(len(title), *(len(item) for item in menu_items)) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2
    win = curses.newwin(box_height, box_width, start_y, start_x)
    win.keypad(True)
    win.box()
    win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
    for idx, item in enumerate(menu_items):
        win.addstr(2 + idx, 2, item)
    win.refresh()
    stdscr.refresh()


def exit_menu(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    menu_items = ["[1] Detach", "[2] Kill", "[0] Back"]
    title = "Exit Menu"
    draw_menu(stdscr, title, menu_items)
    while True:
        key = stdscr.getch()
        try:
            ch = chr(key)
        except Exception:
            continue
        if ch == "1":
            # Send detach command via IPC.
            message = {"action": "DETACH_UI"}
            response = ipc.send_ipc_command(message, DEFAULT_SOCKET_PATH)
            if response:
                stdscr.clear()
                stdscr.addstr(0, 0, "Detach command sent. Detaching UI...")
                stdscr.refresh()
                return
        elif ch == "2":
            # Send kill command via IPC.
            message = {"action": "KILL_UI"}
            response = ipc.send_ipc_command(message, DEFAULT_SOCKET_PATH)
            if response:
                stdscr.clear()
                stdscr.addstr(0, 0, "Kill command sent. Killing UI...")
                stdscr.refresh()
        elif ch == "0" or key == 27:
            # Return to main menu.
            break


def tools_menu(stdscr):
    curses.curs_set(0)
    tool_names = tool_registry.get_tool_names()
    if not tool_names:
        tool_names = ["No tools registered"]
    # Build menu: number tools 1..n, and add "[0] Back" as the last option.
    menu_items = [f"[{idx}] {name}" for idx, name in enumerate(tool_names, start=1)]
    menu_items.append("[0] Back")
    title = "Tools Menu"
    stdscr.clear()
    stdscr.refresh()
    draw_menu(stdscr, title, menu_items)

    while True:
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
            continue
        try:
            char = chr(key)
        except Exception:
            continue
        if char.isdigit():
            if char == "0":
                break
            else:
                num = int(char)
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
                        tool_instance.submenu(stdscr)
                        # After the tool submenu exits, clear the screen.
                        stdscr.clear()
                        stdscr.refresh()
                    except Exception as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Error launching tool {selected_tool}: {e}", curses.A_BOLD)
                        stdscr.refresh()
                        stdscr.getch()
                    break
        elif key == 27:
            break


def main_menu(stdscr):
    # Get the shared queue
    log_queue = get_log_queue()
    worker_configurer(log_queue)
    logging.getLogger(__name__).debug("IPC process logging configured")

    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    # Increase delay to allow tmux pane to settle.
    curses.napms(300)  # 300 milliseconds delay; adjust as needed.

    menu_items = ["[1] Tools", "[0] Exit"]
    title = "Main Menu"
    draw_menu(stdscr, title, menu_items)

    while True:
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
            continue
        try:
            char = chr(key)
        except Exception:
            continue
        if char == "1":
            tools_menu(stdscr)
            # After returning from a submenu, clear and redraw the main menu.
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
        elif char == "0":
            exit_menu(stdscr)
            # After the exit menu, if the user chose Back, redraw the main menu.
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)


if __name__ == "__main__":

    def wait_for_ipc_socket(socket_path, timeout=5):
        start_time = time.time()
        while not os.path.exists(socket_path):
            if time.time() - start_time > timeout:
                return False
            time.sleep(0.1)
        return True

####################################################
##### ensure you import each tools module here #####
##### e.g. (from tools.hcxtool import hcxtool) #####
##### they load via tool_registry / decorators #####
####################################################

    # import tools & registry
    from utils.tool_registry import tool_registry
    from tools.hcxtool import hcxtool

    # setup logs for curses menu processes
    log_queue = get_log_queue()
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()
    worker_configurer(log_queue)
    logging.getLogger(__name__).debug("Main process logging configured using QueueHandler")

    # wait for ipc
    wait_for_ipc_socket(DEFAULT_SOCKET_PATH)

    # run menu
    curses.wrapper(main_menu)

