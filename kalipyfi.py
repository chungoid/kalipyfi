import os
import sys
import time
import jinja2
import logging
import subprocess
from pathlib import Path

# local
from common.process_manager import process_manager
from config.constants import MAIN_UI_YAML_PATH, TMUXP_DIR, BASE_DIR, CURRENT_SOCKET_FILE
from common.logging_setup import get_log_queue, worker_configurer, configure_listener_handlers
from utils.helper import setup_signal_handlers, ipc_ping, get_published_socket_path
from utils.ipc_client import IPCClient


def setup_log_queue():
    log_queue = get_log_queue()
    from logging.handlers import QueueListener
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()
    worker_configurer(log_queue)
    logging.getLogger("kalipyfi_main()").debug("Main process logging configured using QueueHandler")


def register_processes_via_ipc(socket_path, tmuxp_pid):
    client = IPCClient(socket_path)

    # Register the main process
    main_registration = {
        "action": "REGISTER_PROCESS",
        "role": "main",
        "pid": os.getpid()
    }
    main_response = client.send(main_registration)
    logging.info(f"Main process registration response: {main_response}")

    # Register the tmuxp process
    tmuxp_registration = {
        "action": "REGISTER_PROCESS",
        "role": "tmuxp",
        "pid": tmuxp_pid
    }
    tmuxp_response = client.send(tmuxp_registration)
    logging.info(f"tmuxp process registration response: {tmuxp_response}")


def main():
    setup_log_queue()
    # process tracking / signal handler
    process_manager.register_process("main", os.getpid())
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
        if os.path.exists(CURRENT_SOCKET_FILE):  # Check if the file exists
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


if __name__ == "__main__":
    main()

