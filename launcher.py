import subprocess
import os
import time
import logging
from common.process_manager import process_manager

def launch_component(name, command):
    logging.info(f"Launching {name}: {command}")
    proc = subprocess.Popen(command, shell=True, executable="/bin/bash")
    process_manager.register_process(name, proc.pid)
    return proc

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # Launch your main kalipyfi process:
    kalipyfi_proc = launch_component("kalipyfi", "python /home/flip/tmuxp-kalipifi/kalipyfi.py")
    # Optionally, launch the main_menu if needed as a separate pane:
    main_menu_proc = launch_component("main_menu", "bash /home/flip/tmuxp-kalipifi/utils/ui/tmuxp/main_menu.sh")

    # Optionally launch other components (or integrate their functionality into your UI)
    # For example, if show_ascii and tail_log are not crucial, integrate them into the UI.

    # Wait or monitor these processes:
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down all processes.")
        # Use process_manager.shutdown_all() or your custom shutdown routine.
