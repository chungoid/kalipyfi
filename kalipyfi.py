import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import jinja2

# local
from common.process_manager import process_manager
from config.constants import MAIN_UI_YAML_PATH, TMUXP_DIR, BASE_DIR
from common.logging_setup import get_log_queue, worker_configurer, configure_listener_handlers
from utils.helper import setup_signal_handlers, shutdown_flag


def main():
    # process tracking / signal handler
    process_manager.register_process("main", os.getpid())
    setup_signal_handlers()

    # log queue
    log_queue = get_log_queue()
    from logging.handlers import QueueListener
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()
    worker_configurer(log_queue)
    logging.getLogger("kalipyfi_main()").debug("Main process logging configured using QueueHandler")

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

    # Main loop: continue while shutdown_flag is False.
    while not shutdown_flag:
        time.sleep(1)

    logging.info("Shutting Down Kalipyfi...")
    try:
        process_manager.shutdown_all()
        listener.stop()
        sys.exit(0)
    except Exception as e:
        logging.error(f"Error killing tmuxp process group: {e}")

if __name__ == "__main__":
    main()

