import os
import sys
import time
import jinja2
import logging
import subprocess
import logging.handlers
from pathlib import Path

# local
from common.process_manager import process_manager
from config.config_utils import wait_for_logging_server, register_processes_via_ipc
from config.constants import MAIN_UI_YAML_PATH, TMUXP_DIR, BASE_DIR, CURRENT_SOCKET_FILE
from utils.helper import setup_signal_handlers, ipc_ping, get_published_socket_path, attach_existing_kalipyfi_session


def start_logging_server():
    project_base = Path(__file__).resolve().parent
    logging_server_path = project_base / "common" / "logging_server.py"
    proc = subprocess.Popen(
        [sys.executable, str(logging_server_path)],
        cwd=str(project_base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return proc

def main():
    # process tracking / signal handler
    process_manager.register_process(__name__, os.getpid())
    setup_signal_handlers()

    # load tmuxp template
    with open(MAIN_UI_YAML_PATH, "r") as f:
        template_str = f.read()
    template = jinja2.Template(template_str)
    rendered_yaml = template.render(
        BASE_DIR=str(BASE_DIR.resolve()),
        TMUXP_DIR=str(TMUXP_DIR.resolve())
    )
    tmp_yaml = Path("/tmp/kalipyfi_main.yaml")
    with open(tmp_yaml, "w") as f:
        f.write(rendered_yaml)

    # launch tmuxp template
    tmuxp_cmd = f"tmuxp load {tmp_yaml}"
    logging.info(f"Launching tmux session with command: {tmuxp_cmd}")
    tmuxp_proc = subprocess.Popen(
        tmuxp_cmd,
        shell=True,
        executable="/bin/bash",
        preexec_fn=os.setsid,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    process_manager.register_process("tmuxp", tmuxp_proc.pid)

    timeout = 30
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(CURRENT_SOCKET_FILE):  # Check if main_menu wrote new sock file yet
            socket_path = get_published_socket_path()
            if ipc_ping(socket_path):
                logging.info("UI IPC server is ready; proceeding with process registration.")
                break
        time.sleep(0.5)
    else:
        logging.error("Timeout waiting for UI IPC server to become ready.")
        sys.exit(1)

    # Register the processes via IPC
    register_processes_via_ipc(get_published_socket_path(), tmuxp_proc.pid)

    # Wait for tmuxp to exit
    tmuxp_proc.wait()


if __name__ == '__main__':
    if attach_existing_kalipyfi_session():
        # reattach to old
        sys.exit(0)
    else:
        # create fresh session
        log_proc = start_logging_server()
        if wait_for_logging_server():
            logging.info("Logging server is up!")
        else:
            logging.error("Logging server did not start within the timeout period.")
        main()

