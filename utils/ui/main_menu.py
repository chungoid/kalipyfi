# utils/ui/main_menu.py

import os
import sys
import curses
import time
import logging
from pathlib import Path
from multiprocessing import Process, Lock
from logging.handlers import QueueListener

import libtmux

project_base = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_base))

# locals
import logging, sys, time
from common.process_manager import process_manager
from utils.helper import setup_signal_handlers, ipc_ping, publish_socket_path, get_unique_socket_path, \
    wait_for_tmux_session
from common.logging_setup import get_log_queue, configure_listener_handlers, worker_configurer
from utils.ui.ui_manager import UIManager
from utils.ipc import start_ipc_server, ipc_server, reconnect_ipc_socket
from utils.tool_registry import tool_registry
from tools.hcxtool import hcxtool

from utils.helper import shutdown_flag

def draw_menu(stdscr, title, menu_items):
    stdscr.clear()
    stdscr.refresh()
    h, w = stdscr.getmaxyx()
    logging.debug(f"draw_menu: Terminal size: {h}x{w}")
    box_height = len(menu_items) + 4
    box_width = max(len(title), *(len(item) for item in menu_items)) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2
    logging.debug(f"draw_menu: Menu dimensions: height={box_height}, width={box_width}, start_y={start_y}, start_x={start_x}")
    if box_height <= 0 or box_width <= 0 or start_y < 0 or start_x < 0:
        logging.error("draw_menu: Invalid window dimensions, aborting draw_menu.")
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
    def __init__(self, stdscr, min_height=8, min_width=30, ready_timeout=2):
        self.stdscr = stdscr
        self.title = "Main Menu"
        self.session_name ="kalipyfi"
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

        logging.debug("MainMenu: Entering main loop.")
        while not shutdown_flag:
            key = menu_win.getch()
            if key == curses.KEY_RESIZE:
                logging.debug("MainMenu: Detected screen resize.")
                self.stdscr.clear()
                self.stdscr.refresh()
                menu_win = self._redraw_menu()
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

def run_ipc():
    logger = logging.getLogger("run_ipc")
    logger.debug("run_ipc() started.")

    from utils.ui.ui_manager import UIManager
    # Create a UIManager instance for the 'kalipyfi' session.
    ui_instance = UIManager("kalipyfi")

    # Generate a unique socket name and publish it.
    socket_path = get_unique_socket_path()
    publish_socket_path(socket_path)
    logger.debug(f"run_ipc: Unique socket generated and published: {socket_path}")

    # Start the IPC server on this unique socket.
    ipc_server(ui_instance, socket_path)
    logger.info(f"run_ipc: IPC server started on socket: {socket_path}")
    process_manager.register_process(ipc_server, os.getpid())

    # Wait until the tmux session is fully ready.
    from utils.helper import wait_for_tmux_session, log_ui_state_phase
    try:
        session = wait_for_tmux_session("kalipyfi", timeout=30, poll_interval=0.5)
        log_ui_state_phase(logger, ui_instance, "before", "after waiting for tmux session in run_ipc()")
        logger.info(f"run_ipc: tmux session is fully ready: {session.get('session_name')}")
    except TimeoutError as e:
        logger.error("run_ipc: Timeout waiting for tmux session: " + str(e))
        sys.exit(1)

    return ui_instance


def main():
    logging.debug("Starting main_menu.py: main()")
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
    # Create the UI manager for the session.
    ui_instance = UIManager("kalipyfi")
    start_ipc_server(ui_instance)
    curses.wrapper(lambda stdscr: MainMenu(stdscr).run())

    while True:
        logging.debug("Main loop iteration started.")
        if not ipc_ping():
            logging.debug("Main loop: IPC ping failed. Attempting to reconnect...")
            new_socket = reconnect_ipc_socket()
            if new_socket is not None and ipc_ping(new_socket):
                logging.debug("Main loop: Reconnected successfully to IPC socket.")
            else:
                logging.error("Main loop: Reconnection to IPC socket failed.")
        else:
            logging.debug("Main loop: IPC ping succeeded.")
        time.sleep(1)


if __name__ == "__main__":
    main()
