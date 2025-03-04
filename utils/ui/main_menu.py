#!/main_menu.py
import os
import sys
import curses
import logging
from multiprocessing import Process
from pathlib import Path
from logging.handlers import QueueListener
project_base = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_base))

### locals ###
from common.process_manager import process_manager
from common.logging_setup import get_log_queue, configure_listener_handlers
from utils import ipc
from config.constants import TOOL_PATHS, DEFAULT_SOCKET_PATH
from utils.helper import (wait_for_ipc_socket, wait_for_tmux_session,
                          setup_signal_handlers, shutdown_flag)


def draw_menu(stdscr, title, menu_items):
    h, w = stdscr.getmaxyx()
    logging.debug(f"Terminal size: height={h}, width={w}")

    box_height = len(menu_items) + 4
    box_width = max(len(title), *(len(item) for item in menu_items)) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2

    logging.debug(f"Computed window dimensions: box_height={box_height}, box_width={box_width}, start_y={start_y}, start_x={start_x}")

    if box_height <= 0 or box_width <= 0 or start_y < 0 or start_x < 0:
        logging.error("Invalid window dimensions, aborting draw_menu.")
        return

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
                process_manager.shutdown()
                listener.stop()
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

def debug_status_menu(stdscr):
    stdscr.clear()
    stdscr.addstr(0, 0, "Fetching process status...", curses.A_BOLD)
    stdscr.refresh()

    # Send the debug command via IPC.
    message = {"action": "DEBUG_STATUS"}
    response = ipc.send_ipc_command(message, DEFAULT_SOCKET_PATH)

    stdscr.clear()
    if response.get("status") == "DEBUG_STATUS_OK":
        report = response.get("report", "No report available.")
        stdscr.addstr(0, 0, "Process Status Report:", curses.A_BOLD)
        stdscr.addstr(1, 0, report)
    else:
        stdscr.addstr(0, 0, f"Error fetching status: {response.get('error', 'Unknown error')}", curses.A_BOLD)

    stdscr.addstr(curses.LINES - 1, 0, "Press any key to return...")
    stdscr.refresh()
    stdscr.getch()

def utils_menu(stdscr):
    curses.curs_set(0)
    menu_items = ["[1] Status", "[0] Back"]
    title = "Utils Menu"
    draw_menu(stdscr, title, menu_items)

    while True:
        key = stdscr.getch()
        try:
            char = chr(key)
        except Exception:
            continue
        if char == "1":
            debug_status_menu(stdscr)
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
        elif char == "0" or key == 27:
            break

def main_menu(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    # Allow pane to settle
    curses.napms(500)  # 500 ms

    menu_items = ["[1] Tools", "[2] Utils", "[0] Exit"]
    title = "Main Menu"
    draw_menu(stdscr, title, menu_items)

    while not shutdown_flag:
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
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
        elif char == "2":
            utils_menu(stdscr)
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
        elif char == "0":
            exit_menu(stdscr)
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)

def run_ipc_server():
     # Create a dedicated UIManager instance for the IPC server.
    from utils.ipc import ipc_server
    from utils.ui.ui_manager import UIManager
    ui_instance = UIManager(session_name="kalipyfi")
    ipc_server(ui_instance, DEFAULT_SOCKET_PATH)


if __name__ == "__main__":
### immediate process tracking
    setup_signal_handlers()
    process_manager.register_process("main_menu__main__", os.getpid())
### import tools to register via decorators
### will add to tools module init later when there's more
    from utils.tool_registry import tool_registry
    from tools.hcxtool import hcxtool # do this for all tools here

##### ensure you import each tools module here #####

# setup logs for curses menu processes
    log_queue = get_log_queue()
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()
    logging.getLogger("main_menu").debug("Main process logging configured using QueueHandler")

    from utils.ui.ui_manager import UIManager
    from utils.ipc import start_ipc_server
    from utils.helper import log_ui_state_phase
    from utils.helper import wait_for_tmux_session
    import time
    #from utils.ipc import run_ipc_server
    from utils.helper import ipc_ping
    import signal
    #import Process

# wait before instantiating
    wait_for_tmux_session("kalipyfi")
    ui_manager = UIManager(session_name="kalipyfi")

    ipc_process = Process(target=run_ipc_server, daemon=True)
    ipc_process.start()
    #start_ipc_server(ui_manager)

    if ipc_ping:
        curses.wrapper(main_menu)

# keep alive til signal handler
    #while not shutdown_flag: # log_ui_state_phase can be uncommented to dump ui state every sleep cycle for debugging
        #log_ui_state_phase(logging.getLogger("kalipyfi_main()"), ui_manager, "after", "init in main")
    while True:
        if not ipc_ping(DEFAULT_SOCKET_PATH) and not shutdown_flag:
            pass
        time.sleep(5)

        logging.info("Shutting Down Kalipyfi...")
        process_manager.shutdown_all()