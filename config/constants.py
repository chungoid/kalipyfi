from pathlib import Path

#########################
##### DEFAULT PATHS #####
#########################

CONFIG_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIG_DIR.parent
LOG_DIR = BASE_DIR / "logs"
UI_DIR = BASE_DIR / "utils" / "ui"
TOOLS_DIR = BASE_DIR / "tools"

CURSES_MAIN_MENU = UI_DIR / "main_menu.py"
LOG_FILE = LOG_DIR / "kalipyfi.log"
MAIN_UI_YAML_PATH = UI_DIR / "tmuxp" / "main_tmuxp.yaml"
BG_YAML_PATH = UI_DIR / "tmuxp" / "background_tmuxp.yaml"
DEFAULT_ASCII = UI_DIR / "tmuxp" / "ascii.txt"

TOOL_PATHS = {
    "hcxtool": TOOLS_DIR / "hcxtool",
}


########################
##### IPC PROTOCOL #####
########################

IPC_CONSTANTS = {
    "keys": {
        "ACTION_KEY": "action",
        "TOOL_KEY": "tool",
        "SCAN_PROFILE_KEY": "scan_profile",
        "COMMAND_KEY": "command",
        "TIMESTAMP_KEY": "timestamp",
        "STATUS_KEY": "status",
        "RESULT_KEY": "result",
        "ERROR_KEY": "error",
    },
    "actions": {
        "GET_STATE": "GET_STATE",
        "GET_SCANS": "GET_SCANS",
        "SEND_SCAN": "SEND_SCAN",
        "SWAP_SCAN": "SWAP_SCAN",
        "STOP_SCAN": "STOP_SCAN",
        "UPDATE_LOCK": "UPDATE_LOCK",
        "REMOVE_LOCK": "REMOVE_LOCK",
        "KILL_UI": "KILL_UI",
        "DETACH_UI": "DETACH_UI",
    }
}


## DEFAULT SETTINGS ##
DEFAULT_SOCKET_PATH = "/tmp/tmuxp-kalipifi.sock"
RETRY_DELAY = 1
