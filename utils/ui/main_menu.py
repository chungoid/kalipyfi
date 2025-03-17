# utils/ui/main_menu.py
import os
import sys
import time
import logging
import curses
from pathlib import Path
from logging.handlers import QueueListener
import libtmux


project_base = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_base))

# locals
from utils.helper import setup_signal_handlers, publish_socket_path, get_unique_socket_path, \
    wait_for_tmux_session, shutdown_flag
from common.logging_setup import get_log_queue, configure_listener_handlers, worker_configurer
from common.process_manager import process_manager
from utils.ui.ui_manager import UIManager
from utils.ipc import IPCServer
from utils.ipc_callback import get_shared_callback_socket


#####################
##### IMPORTANT #####
#####################
# import all tool modules so they load via decorators
from utils.tool_registry import tool_registry
from tools.hcxtool import hcxtool
from tools.pyfyconnect import pyfyconnect
from tools.nmap import nmap


def draw_menu(stdscr, title, menu_items):
    stdscr.clear()
    stdscr.refresh()
    h, w = stdscr.getmaxyx()
    logging.debug(f"draw_menu: Terminal size: {h}x{w}")

    # Calculate minimum size needed
    min_height = len(menu_items) + 4
    min_width = max(len(title), *(len(item) for item in menu_items)) + 4

    # If terminal is too small, create a smaller menu with scrolling capability
    if h < min_height or w < min_width:
        logging.warning(f"Terminal too small ({h}x{w}), creating compact menu")
        # Create a menu that fits the available space
        box_height = min(h - 2, len(menu_items) + 2)
        box_width = min(w - 2, min_width)

        # Centered as much as possible
        start_y = max(0, (h - box_height) // 2)
        start_x = max(0, (w - box_width) // 2)

        if box_height <= 0 or box_width <= 0:
            logging.error(f"Terminal size ({h}x{w}) too small for even a compact menu")
            return None

        win = curses.newwin(box_height, box_width, start_y, start_x)
        win.keypad(True)
        win.box()

        # Show title if there's room
        if box_width >= len(title) + 2 and box_height > 2:
            win.addstr(1, max(1, (box_width - len(title)) // 2), title[:box_width - 2], curses.A_BOLD)

        # Show as many menu items as possible
        visible_items = min(box_height - 2, len(menu_items))
        for idx in range(visible_items):
            item_text = menu_items[idx][:box_width - 4]
            if 1 + idx < box_height - 1:  # Ensure we don't write outside the window
                win.addstr(1 + idx, 1, item_text)

        win.refresh()
        logging.debug("draw_menu: Compact menu drawn successfully.")
        return win

    # Original code for normal sized terminals
    box_height = min_height
    box_width = min_width
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2

    if start_y < 0 or start_x < 0:
        logging.error(f"Invalid window position: start_y={start_y}, start_x={start_x}")
        return None

    win = curses.newwin(box_height, box_width, start_y, start_x)
    win.keypad(True)
    win.box()
    win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
    for idx, item in enumerate(menu_items):
        win.addstr(2 + idx, 2, item)
    win.refresh()
    logging.debug("draw_menu: Menu drawn successfully.")
    return win

class MainMenu:
    def __init__(self, stdscr, ui_instance, min_height=8, min_width=30, ready_timeout=2):
        self.stdscr = stdscr
        self.title = "Main Menu"
        self.session_name ="kalipyfi"
        self.ui_instance = ui_instance
        self.menu_items = ["[1] Tools", "[2] Utils", "[0] Exit"]
        self.min_height = min_height
        self.min_width = min_width
        self.ready_timeout = ready_timeout

    def wait_for_kalipyfi_session(self, session_name="kalipyfi", expected_panes=2, timeout=2, poll_interval=0.1) -> bool:
        """
        Waits until a tmux session with the given name exists and its first window has at least
        `expected_panes` panes.

        Returns:
            True if the session is found and ready within the timeout, False otherwise.
        """
        logger = logging.getLogger("MainMenu:wait_for_kalipyfi_session")
        logger.debug(
            f"Waiting for tmux session '{session_name}' to have at least {expected_panes} panes (timeout={timeout}s).")
        server = libtmux.Server()
        start_time = time.time()
        while time.time() - start_time < timeout:
            session = server.find_where({"session_name": session_name})
            if session is not None:
                if session.windows:
                    pane_count = len(session.windows[0].panes)
                    logger.debug(f"Found session '{session_name}' with {pane_count} pane(s) in its first window.")
                    if pane_count >= expected_panes:
                        logger.info(f"Session '{session_name}' is ready with {pane_count} panes.")
                        return True
                else:
                    logger.debug(f"Session '{session_name}' exists but has no windows yet.")
            else:
                logger.debug(f"Session '{session_name}' not found.")
            time.sleep(poll_interval)
        logger.error(
            f"Timeout: Session '{session_name}' did not have at least {expected_panes} panes within {timeout} seconds.")
        return False

    def _redraw_menu(self):
        self.stdscr.clear()
        self.stdscr.refresh()
        menu = draw_menu(self.stdscr, self.title, self.menu_items)
        logging.debug("MainMenu: Menu redrawn.")
        return menu

    def run(self):
        logging.debug("MainMenu: run() started.")
        curses.curs_set(0)

        # Wait for tmux session to exist
        if not self.wait_for_kalipyfi_session():
            self.stdscr.addstr(0, 0, "Screen too small or not ready. Please resize your terminal.")
            self.stdscr.refresh()
            self.stdscr.getch()
            logging.error("MainMenu: Screen not ready, exiting run().")
            return

        # Now wait for terminal size to be adequate
        max_tries = 10
        tries = 0
        menu_win = None

        while menu_win is None and tries < max_tries:
            h, w = self.stdscr.getmaxyx()
            logging.debug(f"Terminal size check {tries + 1}/{max_tries}: {h}x{w}")

            if h >= self.min_height and w >= self.min_width:
                menu_win = self._redraw_menu()
                if menu_win is not None:
                    break

            # Show waiting message
            self.stdscr.clear()
            wait_msg = f"Waiting for terminal size ({h}x{w}, need {self.min_height}x{self.min_width})..."
            if h > 0 and w > len(wait_msg):
                self.stdscr.addstr(0, 0, wait_msg)
            self.stdscr.refresh()

            # Wait a bit for terminal to resize/initialize
            time.sleep(0.5)
            tries += 1

        if menu_win is None:
            logging.error(f"Failed to create menu after {max_tries} attempts. Terminal too small.")
            if h > 0 and w > 30:
                self.stdscr.addstr(0, 0, "Terminal too small for menu. Exiting.")
                self.stdscr.refresh()
                self.stdscr.getch()
            return

        self.ui_instance.ready = True  # Mark the UI as ready for registration/handshake
        logging.info("Main UI is fully initialized and ready.")
        logging.debug("MainMenu: Entering main loop.")

        while not shutdown_flag:
            key = menu_win.getch()
            if key == curses.KEY_RESIZE:
                logging.debug("MainMenu: Detected screen resize.")
                self.stdscr.clear()
                self.stdscr.refresh()
                menu_win = self._redraw_menu()
                if menu_win is None:
                    logging.error("MainMenu: Screen became too small after resize.")
                    break
                continue
            try:
                char = chr(key)
            except Exception:
                continue
            logging.debug(f"MainMenu: Key pressed: {char}")
            if char == "1":
                logging.debug("MainMenu: Option 1 selected (Tools).")
                menu_win.erase()
                self.stdscr.clear()
                self.stdscr.refresh()
                from submenu import tools_menu
                tools_menu(self.stdscr)
                self.stdscr.clear()
                self.stdscr.refresh()
                menu_win = self._redraw_menu()
            elif char == "2":
                logging.debug("MainMenu: Option 2 selected (Utils).")
                menu_win.erase()
                self.stdscr.clear()
                self.stdscr.refresh()
                from submenu import utils_menu
                utils_menu(self.stdscr)
                self.stdscr.clear()
                self.stdscr.refresh()
                menu_win = self._redraw_menu()
            elif char == "0":
                logging.debug("MainMenu: Option 0 selected (Exit).")
                menu_win.erase()
                self.stdscr.clear()
                self.stdscr.refresh()
                from submenu import exit_menu
                exit_menu(self.stdscr)
                self.stdscr.clear()
                self.stdscr.refresh()
                menu_win = self._redraw_menu()
        logging.debug("MainMenu: Exiting main loop.")
        menu_win.erase()
        self.stdscr.clear()
        self.stdscr.refresh()


def main():
    process_manager.register_process("main_menu.py", os.getpid())
    setup_signal_handlers()

    log_queue = get_log_queue()
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()
    worker_configurer(log_queue)
    logging.getLogger("main_menu").debug("Main process logging configured using QueueHandler")

    # wait for tmuxp to load
    wait_for_tmux_session("kalipyfi", timeout=30, poll_interval=0.5)

    # Generate a unique socket path and write to /tmp/
    new_socket_path = get_unique_socket_path()
    socket_path = publish_socket_path(new_socket_path)
    logging.debug(f"main: Using socket path: {socket_path}")

    # Set callback socket path
    callback_socket = get_shared_callback_socket()
    logging.debug(f"Main: Shared callback socket: {callback_socket}")

    # Instantiate ui & ipc server instances
    ui_instance = UIManager("kalipyfi")
    ipc_server = IPCServer(ui_instance, socket_path)
    ipc_server.start()

    # Start IPC server with the specific socket path
    time.sleep(2)

    # Run the main menu
    curses.wrapper(lambda stdscr: MainMenu(stdscr, ui_instance).run())

    # Once user hits exit in main menu # testing this
    logging.info("Main menu UI exited. Initiating shutdown.")
    process_manager.shutdown_all()
    logging.info("Shutdown complete. Exiting main_menu.py")
    sys.exit(0)


if __name__ == "__main__":
    main()
