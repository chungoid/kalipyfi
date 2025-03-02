import curses
import logging
import os
import time
from pathlib import Path
import jinja2
from logging.handlers import QueueListener

from config.constants import UI_DIR, MAIN_UI_YAML_PATH, CLEANUP_SCRIPT
from common.logging_setup import get_log_queue, worker_configurer, configure_listener_handlers
from utils.ipc import start_ipc_server
from utils.ui.main_menu import main_menu
from utils.ui.ui_manager import UIManager
from tools.hcxtool import hcxtool


def main():
    # Set up the shared log queue and start the QueueListener.
    log_queue = get_log_queue()
    listener_handlers = configure_listener_handlers()
    listener = QueueListener(log_queue, *listener_handlers)
    listener.start()

    # Configure logging for the main process.
    worker_configurer(log_queue)
    logging.getLogger(__name__).debug("Main process logging configured using QueueHandler")

    # Load and render the tmuxp YAML template.
    with open(MAIN_UI_YAML_PATH, "r") as f:
        template_str = f.read()
    template = jinja2.Template(template_str)
    rendered_yaml = template.render(UI_DIR=str(UI_DIR.resolve()))
    tmp_yaml = Path("/tmp/kalipyfi_main.yaml")
    with open(tmp_yaml, "w") as f:
        f.write(rendered_yaml)

    # Launch the tmux session (this should create your UI).
    os.system(f"tmuxp load {tmp_yaml}")

    # Now instantiate the UIManager and start the IPC server.
    ui_manager = UIManager(session_name="kalipyfi")
    start_ipc_server(ui_manager)

    # Block to keep the main process alive.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down...")
    finally:
        listener.stop()


if __name__ == '__main__':
    main()
