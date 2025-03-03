#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path
import logging
project_base = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_base))

logging.basicConfig(level=logging.DEBUG)
cwd = Path(__file__).resolve().parent
logging.info(f"tail_log.py cwd is {cwd}")

# The log directory is assumed to be under the project base in "logs"
log_dir = project_base / "logs"
logging.info(f"tail_log.py log directory is {log_dir}")

# Build the path to the log file (e.g. kalipyfi.log)
log_file = log_dir / "kalipyfi.log"
logging.info(f"tail_log.py will tail log file at {log_file}")

# Clear the screen.
os.system("clear")

def tail_f(filename):
    try:
        with open(filename, "r") as f:
            f.seek(0, os.SEEK_END)  # Move to the end of file
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.5)
    except Exception as e:
        logging.error(f"Error reading {filename}: {e}")


tail_f(log_file)
