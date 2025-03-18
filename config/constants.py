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
    "pyfyconnect": TOOLS_DIR / "pyfyconnect",
    "nmap": TOOLS_DIR / "nmap",
}


########################
##### IPC PROTOCOL #####
########################

## DEFAULT SETTINGS ##
RETRY_DELAY = 0.1
DEFAULT_BASE_SOCKET = "/tmp/tmuxp-kalipyfi"
SOCKET_SUFFIX = ".sock"
# File containing the current socket path (should be updated by the server)
CURRENT_SOCKET_FILE = "/tmp/tmuxp-kalipyfi_current.sock"

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
        "PING": "PING",
        "GET_STATE": "GET_STATE",
        "REGISTER_PROCESS": "REGISTER_PROCESS",
        "UI_READY": "UI_READY",
        "GET_SCANS": "GET_SCANS",
        "SEND_SCAN": "SEND_SCAN",
        "SWAP_SCAN": "SWAP_SCAN",
        "STOP_SCAN": "STOP_SCAN",
        "CONNECT_NETWORK": "CONNECT_NETWORK",
        "COPY_MODE": "COPY_MODE",
        "UPDATE_LOCK": "UPDATE_LOCK",
        "REMOVE_LOCK": "REMOVE_LOCK",
        "KILL_UI": "KILL_UI",
        "DETACH_UI": "DETACH_UI",
        "KILL_WINDOW": "KILL_WINDOW",
        "DEBUG_STATUS": "DEBUG_STATUS",
        "SCAN_COMPLETE": "SCAN_COMPLETE",
    }
}

