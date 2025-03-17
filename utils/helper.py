# utils/helper.py
import os
import subprocess
import time
import pprint
import signal
import inspect
import logging
import libtmux

# local
from config.constants import DEFAULT_BASE_SOCKET, SOCKET_SUFFIX, CURRENT_SOCKET_FILE
from common.process_manager import process_manager

logger = logging.getLogger(__name__)

# global shutdown flag
# ipc server distributes to change to true on event kill_ui -> kalipyfi.py main()
shutdown_flag = False

def ipc_ping(socket_path: str = None) -> bool:
    import socket
    if socket_path is None:
        socket_path = get_published_socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(socket_path)
            s.send(b'{"action": "PING"}')
            response = s.recv(1024)
            if response:
                return True
    except Exception:
        return False

def get_unique_socket_path(base=DEFAULT_BASE_SOCKET, suffix=SOCKET_SUFFIX):
    """Generate a unique socket path using the process ID and a timestamp."""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    return f"{base}_{pid}_{timestamp}{suffix}"

def publish_socket_path(socket_path, publish_file=CURRENT_SOCKET_FILE):
    with open(publish_file, "w") as f:
        f.write(socket_path)
    return socket_path

def get_published_socket_path(publish_file=CURRENT_SOCKET_FILE):
    """Read the published socket path from the well-known file."""
    with open(publish_file, "r") as f:
        return f.read().strip()

def cleanup_tmp():
    if os.path.exists("/tmp/kalipyfi_main.yaml"):
        os.remove("/tmp/kalipyfi_main.yaml")
    if os.path.exists(CURRENT_SOCKET_FILE):
        os.remove(CURRENT_SOCKET_FILE)

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


def attach_existing_kalipyfi_session(session_name: str = "kalipyfi") -> bool:
    """
    Checks if a tmux session with the given session_name exists.
    If it does, attaches to that session and returns True.
    If it does not exist, returns False without trying to attach.

    :param session_name: The name of the tmux session to check for.
    :return: True if the session exists and the attach command was run successfully, otherwise False.
    """
    try:
        subprocess.check_output(["tmux", "has-session", "-t", session_name], stderr=subprocess.DEVNULL)
        print(f"checking for old sessions...")
    except subprocess.CalledProcessError:
        print(f"Creating new {session_name} session..."
              f"\nInitializing IPC & Logging servers, please wait...")
        logging.info(f"Creating new {session_name} session...")
        return False

    try:
        # attach to the existing session
        ret = subprocess.call(["tmux", "attach-session", "-t", session_name], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        if ret != 0:
            print(f"Failed to attach to session '{session_name}'.")
            return False
        return True
    except Exception as e:
        print(f"Error while attaching to session '{session_name}': {e}")
        return False


def log_ui_state_phase(logger, ui_instance, phase: str, extra_msg: str = "") -> None:
    """
    Logs detailed debug information about the current UI state, including a dump
    of windows, panes, active scans, and interfaces. It also compares the tmuxp-reported
    pane titles with the internal active scan titles to help diagnose any mismatches.

    Parameters
    ----------
    logger : logging.Logger
        The logger to use for output.
    ui_instance : UiManager
        The UI manager instance whose state is to be dumped.
    phase : str
        A label (e.g., "Before", "After") indicating the phase of a swap or operation.
    extra_msg : str, optional
        Additional contextual information to include in the log message.
    """
    caller_frame = inspect.stack()[1]
    file_name = caller_frame.filename.split("/")[-1]
    function_name = caller_frame.function

    logger.debug(
        f"-- file: [{file_name}] -- function: [{function_name}] -- {phase.upper()} SWAPPING -- {extra_msg}"
    )

    # Dump full UI state.
    ui_state = ui_instance.get_ui_state()
    logger.debug("Full UI State:\n%s", pprint.pformat(ui_state, indent=4))

    # Flatten active_scans for easier comparison.
    flattened = {}
    for win in ui_state["windows"]:
        for pane in win["panes"]:
            flattened[pane["pane_id"]] = pane["internal_title"]

    # Compare tmuxp-reported pane titles with internal titles.
    for win in ui_state["windows"]:
        for pane in win["panes"]:
            tmux_title = pane["tmux_title"]
            internal_title = flattened.get(pane["pane_id"], "N/A")
            if tmux_title != internal_title:
                logger.debug(
                    f"Title mismatch for pane {pane['pane_id']}: tmuxp reported '{tmux_title}' vs. internal mapping '{internal_title}'"
                )


def shutdown_ui():
    import subprocess
    import sys
    logging.info("Shutting down UI and associated processes...")

    # Shutdown all registered processes
    process_manager.shutdown_all()

    # Explicitly kill the tmux session
    session_name = "kalipyfi"  # Or get it from your UIManager instance
    try:
        subprocess.run(f"tmux kill-session -t {session_name}", shell=True, check=True)
        logging.debug("tmux session killed via subprocess.")
    except Exception as e:
        logging.exception("Error killing tmux session via command: %s", e)

    # kill the entire process group
    try:
        os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
        logging.debug("Killed entire process group.")
    except Exception as e:
        logging.exception("Error killing process group: %s", e)

    logging.info("Final process status:\n" + process_manager.get_status_report())
    sys.exit(0)

