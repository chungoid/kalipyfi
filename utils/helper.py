import os
import shutil
import socket
import subprocess
import time
import logging
import inspect
import signal
import libtmux

# local
from config.constants import DEFAULT_SOCKET_PATH

shutdown_flag = False

def cleanup_tmp():
    if os.path.exists("/tmp/kalipyfi_main.yaml"):
        os.remove("/tmp/kalipyfi_main.yaml")

def handle_shutdown_signal(signum, frame):
    global shutdown_flag
    logging.info(f"Received shutdown signal: {signum}")
    shutdown_flag = True

def setup_signal_handlers():
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

def wait_for_tmux_session(session_name: str, timeout: int = 30, poll_interval: float = 0.5) -> libtmux.Session:
    """
    Waits until a tmux session with the given name exists and all its panes have valid (non-zero)
    dimensions. Returns the session if found within the timeout, or raises a TimeoutError.
    """
    server = libtmux.Server()
    start_time = time.time()
    while time.time() - start_time < timeout:
        session = server.find_where({"session_name": session_name})
        if session:
            valid = True
            for window in session.windows:
                for pane in window.panes:
                    try:
                        height = int(pane["pane_height"])
                        width = int(pane["pane_width"])
                    except (KeyError, ValueError) as e:
                        valid = False
                        logging.debug(f"Pane {pane['pane_id']} missing or invalid dimensions: {e}")
                        break
                    if height <= 0 or width <= 0:
                        valid = False
                        logging.debug(f"Pane {pane['pane_id']} has non-positive dimensions: height={height}, width={width}")
                        break
                if not valid:
                    break
            if valid:
                logging.info(f"Found valid session '{session_name}' with proper pane dimensions.")
                return session
            else:
                logging.debug(f"Session '{session_name}' found but waiting for valid pane dimensions.")
        else:
            logging.debug(f"Session '{session_name}' not found yet.")
        time.sleep(poll_interval)
    raise TimeoutError(f"Timeout waiting for tmux session '{session_name}' to be fully ready.")


def wait_for_ipc_socket(socket_path: str=DEFAULT_SOCKET_PATH, timeout: float=5, retry_delay: float=0.1) -> bool:
    """
    Waits for the IPC socket at `socket_path` to become available.
    Tries to establish a connection until the timeout is reached.

    Args:
        socket_path (str): Path to the Unix socket.
        timeout (float): Maximum time to wait in seconds.
        retry_delay (float): Delay between retries in seconds.

    Returns:
        bool: True if connection is successful, False otherwise.
    """
    logger = logging.getLogger("helper:wait_for_ipc_socket")
    start_time = time.time()
    attempt = 0
    logger.debug(f"wait_for_ipc_socket: Waiting for socket at {socket_path} with timeout {timeout}s.")

    while True:
        attempt += 1
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(retry_delay)
                s.connect(socket_path)
            logger.debug(f"wait_for_ipc_socket: Successfully connected to {socket_path} on attempt {attempt}.")
            return True
        except socket.error as e:
            elapsed = time.time() - start_time
            logger.debug(f"wait_for_ipc_socket: Attempt {attempt} failed: {e}. Elapsed time: {elapsed:.2f}s.")
            if elapsed > timeout:
                logger.error(f"wait_for_ipc_socket: Timed out after {timeout}s waiting for socket {socket_path}.")
                return False
            time.sleep(retry_delay)

def log_ui_state_phase(logger, ui_instance, phase: str, extra_msg: str = "") -> None:
    """
    Logs a debug message with caller info, the phase, and extra info.
    Then, it dumps the UI state and logs differences between
    tmuxp-reported pane titles and the internal active_scans mapping.

    Args:
        logger (logging.Logger): Logger to use.
        ui_instance (UiInstance): UiInstance to use.
        phase (str): Before or After as keyword to log place in function.
        extra_msg (str, optional): Additional info if phase keyword isn't enough.
    """
    caller_frame = inspect.stack()[1]
    file_name = caller_frame.filename.split("/")[-1]
    function_name = caller_frame.function

    logger.debug(
        f"-- file: [{file_name}] -- function: [{function_name}] -- {phase.upper()} SWAPPING -- {extra_msg}"
    )
    ui_instance.dump_ui_state()

    # flatten active_scans for comparison
    flattened = {}
    for tool, mapping in ui_instance.active_scans.items():
        flattened.update(mapping)

    # compare each main UI pane's tmuxp title vs. internal mapping
    for pane in ui_instance.window.panes:
        title_cmd = f'tmuxp display-message -p "#{{pane_title}}" -t {pane.pane_id}'
        result = subprocess.run(title_cmd, shell=True, capture_output=True, text=True)
        tmux_title = result.stdout.strip() if result.returncode == 0 else "N/A"
        internal_title = flattened.get(pane.pane_id, "N/A")
        if tmux_title != internal_title:
            logger.debug(
                f"Title mismatch for pane {pane.pane_id}: tmuxp reported '{tmux_title}' vs. internal mapping '{internal_title}'"
            )
