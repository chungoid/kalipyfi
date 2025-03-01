from pathlib import Path

# Default Directories
CONFIG_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIG_DIR.parent
LOG_DIR = BASE_DIR / "logs"
UI_DIR = BASE_DIR / "utils" / "ui"
TOOLS_DIR = BASE_DIR / "tools"

# Default Files
CURSES_MAIN_MENU = UI_DIR / "main_menu.py"
LOG_FILE = LOG_DIR / "kalipyfi.log"
MAIN_UI_YAML_PATH = UI_DIR / "tmuxp" / "main_tmuxp.yaml"
BG_YAML_PATH = UI_DIR / "tmuxp" / "background_tmuxp.yaml"
DEFAULT_ASCII = UI_DIR / "tmuxp" / "ascii.txt"

# Tool Paths
TOOL_PATHS = {
    "hcxtool": TOOLS_DIR / "hcxtool",
}


# DEFAULT IPC SETTINGS
DEFAULT_SOCKET_PATH = 5000
RETRY_DELAY = 1
