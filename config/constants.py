from pathlib import Path

#########################
##### DEFAULT PATHS #####
#########################

CONFIG_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIG_DIR.parent
LOG_DIR = BASE_DIR / "logs"
TOOLS_DIR = BASE_DIR / "tools"
UTILS_DIR = BASE_DIR / "utils"
UI_DIR = UTILS_DIR / "ui"
TMUXP_DIR = UI_DIR / "tmuxp"

LOG_FILE = LOG_DIR / "kalipyfi.log"
CURSES_MAIN_MENU = UI_DIR / "main_menu.py"
MAIN_UI_YAML_PATH = TMUXP_DIR / "main_tmuxp.yaml"
DEFAULT_ASCII = TMUXP_DIR / "ascii.txt"
CLEANUP_SCRIPT = TMUXP_DIR / "cleanup.py"

TOOL_PATHS = {
    "hcxtool": TOOLS_DIR / "hcxtool",
}


########################
##### IPC PROTOCOL #####
########################

## DEFAULT SETTINGS ##
DEFAULT_SOCKET_PATH = "/tmp/tmuxp-kalipyfi.sock"
RETRY_DELAY = .1

## keys and commands ##
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
        "DEBUG_STATUS": "DEBUG_STATUS",
    }
}

