import logging
import logging.handlers
import time
from multiprocessing import Queue
from pathlib import Path
from config.constants import LOG_DIR, LOG_FILE

LOG_QUEUE = Queue(-1)

def get_log_queue():
    return LOG_QUEUE


def configure_listener_handlers():
    """Set up file and console handlers for the listener.

    This version creates a new log file for each run (by appending a timestamp)
    and deletes older log files so that only the most recent 3 remain.
    """
    # Ensure the log directory exists.
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create a new log filename by appending a timestamp.
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    # Assume LOG_FILE is something like Path("kalipyfi.log")
    new_log_file = log_dir / f"{LOG_FILE.stem}_{timestamp}{LOG_FILE.suffix}"

    # Clean up older log files—keep only the latest 3.
    backup_count = 3
    all_logs = sorted(log_dir.glob(f"{LOG_FILE.stem}_*{LOG_FILE.suffix}"),
                      key=lambda p: p.stat().st_mtime,
                      reverse=True)
    for old_log in all_logs[backup_count:]:
        try:
            old_log.unlink()
        except Exception as e:
            print(f"Error deleting old log file {old_log}: {e}")

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(process)d] %(message)s'
    )

    # Create a file handler for the new log file.
    file_handler = logging.FileHandler(str(new_log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    return [file_handler]


def worker_configurer(log_queue):
    """Configure logging for a worker process using a QueueHandler."""
    queue_handler = logging.handlers.QueueHandler(log_queue)
    root = logging.getLogger()
    # Clear any existing handlers.
    root.handlers = []
    root.addHandler(queue_handler)
    root.setLevel(logging.DEBUG)
