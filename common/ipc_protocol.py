import json

# common keys
ACTION_KEY = "action"
TOOL_KEY = "tool"
SCAN_PROFILE_KEY = "scan_profile"
COMMAND_KEY = "command"
TIMESTAMP_KEY = "timestamp"
STATUS_KEY = "status"
RESULT_KEY = "result"
ERROR_KEY = "error"

# expected actions
GET_STATE = "GET_STATE"
GET_SCANS = "GET_SCANS"
SEND_SCAN = "SEND_SCAN"
SWAP_SCAN = "SWAP_SCAN"
STOP_SCAN = "STOP_SCAN"
UPDATE_LOCK = "UPDATE_LOCK"
REMOVE_LOCK = "REMOVE_LOCK"
KILL_UI = "KILL_UI"
DETACH_UI = "DETACH_UI"

def pack_message(message: dict) -> str:
    """
    Converts a message dictionary into a JSON string.
    """
    return json.dumps(message)


def unpack_message(message_str: str) -> dict:
    """
    Converts a JSON string into a message dictionary.
    Returns a dictionary with an error if JSON decoding fails.
    """
    try:
        return json.loads(message_str)
    except json.JSONDecodeError:
        return {ERROR_KEY: "Invalid JSON format"}


def handle_get_state(ui_instance, request: dict) -> dict:
    state = {"active_scans": ui_instance.active_scans}
    return {"status": "OK", "state": state}


def handle_send_scan(ui_instance, request: dict) -> dict:
    """
    Calls the UI to allocate a pane and run the command

    Expected keys: tool, scan_profile, command
    """
    tool_name = request.get("tool")
    scan_profile = request.get("scan_profile")
    cmd_dict = request.get("command")
    if not all([tool_name, scan_profile, cmd_dict]):
        return {ERROR_KEY: "Missing parameters for SEND_SCAN"}

    # Call the UI instance to allocate a pane and run the command.
    pane_id = ui_instance.allocate_scan_pane(tool_name, scan_profile, cmd_dict)
    if pane_id:
        return {"status": f"SEND_SCAN_OK", "pane_id": pane_id}
    else:
        return {ERROR_KEY: "Failed to allocate scan pane"}

