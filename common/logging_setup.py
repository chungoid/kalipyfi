import logging
import logging.handlers
from multiprocessing import Queue
from pathlib import Path
from config.constants import LOG_DIR, LOG_FILE


LOG_QUEUE = Queue(-1)

def get_log_queue():
    return LOG_QUEUE

def configure_listener_handlers():
    """Set up file and console handlers for the listener."""
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(process)d] %(message)s')

    # File handler
    file_handler = logging.FileHandler(str(LOG_FILE))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    return [file_handler]

def worker_configurer(log_queue):
    """Configure logging for a worker process using a QueueHandler."""
    queue_handler = logging.handlers.QueueHandler(log_queue)
    root = logging.getLogger()
    # clear any existing handlers
    root.handlers = []
    root.addHandler(queue_handler)
    root.setLevel(logging.DEBUG)
