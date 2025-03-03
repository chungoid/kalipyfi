#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import logging
project_base = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_base))

logging.basicConfig(level=logging.DEBUG)
cwd = Path(__file__).resolve().parent
logging.info(f"menu_launcher.py cwd is {cwd}")

# go up one directory
parent_dir = cwd.parent
logging.info(f"menu_launcher.py parent directory is {parent_dir}")

# ui dir
main_menu_path = parent_dir / "main_menu.py"
logging.info(f"menu_launcher.py will execute main_menu.py at {main_menu_path}")

# replace process
os.execvp(sys.executable, [sys.executable, str(main_menu_path)])
