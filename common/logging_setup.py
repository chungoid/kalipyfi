import logging

# local
from config.constants import LOG_DIR, LOG_FILE


def setup_logging():
    """Configure logging to only log to a file and suppress unnecessary tmux logs."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()  # Root logger
    logger.setLevel(logging.DEBUG)

    # Remove all handlers to prevent duplication
    if logger.hasHandlers():
        logger.handlers.clear()

    # File Handler
    file_handler = logging.FileHandler(str(LOG_FILE))
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Completely suppress `libtmux` debug output
    logging.getLogger("libtmux").setLevel(logging.WARNING)  # Only log warnings/errors
    logging.getLogger("libtmux._internal").setLevel(logging.WARNING)

    # Suppress excessive tmux debugging from subprocess calls
    class SuppressTmuxDebugFilter(logging.Filter):
        def filter(self, record):
            return "self.stdout for /usr/bin/tmux" not in record.getMessage()

    file_handler.addFilter(SuppressTmuxDebugFilter())