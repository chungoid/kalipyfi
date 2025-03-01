import os
import re
import subprocess
import sys
import time
import select
import logging
import inspect
from pathlib import Path

project_base = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_base))

def set_root():
    os.setuid(0)

def check_root() -> bool:
    return os.geteuid() == 0

def flush_stdin(timeout=0.1) -> None:
    """Flush any pending input from stdin."""
    time.sleep(timeout)
    while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        sys.stdin.read(1)

def log_ui_state_phase(logger, ui_instance, phase: str, extra_msg: str = "") -> None:
    """
    Logs a debug message with caller info, the phase, and extra info.
    Then, it dumps the UI state and logs differences between
    tmux-reported pane titles and the internal active_scans mapping.

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

    # compare each main UI pane's tmux title vs. internal mapping
    for pane in ui_instance.window.panes:
        title_cmd = f'tmux display-message -p "#{{pane_title}}" -t {pane.pane_id}'
        result = subprocess.run(title_cmd, shell=True, capture_output=True, text=True)
        tmux_title = result.stdout.strip() if result.returncode == 0 else "N/A"
        internal_title = flattened.get(pane.pane_id, "N/A")
        if tmux_title != internal_title:
            logger.debug(
                f"Title mismatch for pane {pane.pane_id}: tmux reported '{tmux_title}' vs. internal mapping '{internal_title}'"
            )

class EscapeSequenceFilter(logging.Filter):
    ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

    def filter(self, record) -> bool:
        # Remove ANSI escape sequences from the message.
        record.msg = self.ansi_escape.sub('', record.msg)
        return True