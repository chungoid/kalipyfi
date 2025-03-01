import json
from config.constants import (
    ERROR_KEY, STATUS_KEY, GET_SCANS, SEND_SCAN,
    SWAP_SCAN, STOP_SCAN, UPDATE_LOCK, REMOVE_LOCK,
    KILL_UI, DETACH_UI)


def pack_message(message: dict) -> str:
    """
    Converts a message dictionary into a JSON string.

    :param message: The dictionary to convert.
    :return: A JSON string representation of the message.
    """
    return json.dumps(message)


def unpack_message(message_str: str) -> dict:
    """
    Converts a JSON string into a message dictionary.
    Returns a dictionary with an error key if JSON decoding fails.

    :param message_str: The JSON string to decode.
    :return: A dictionary representing the message.
    """
    try:
        return json.loads(message_str)
    except json.JSONDecodeError:
        return {ERROR_KEY: "Invalid JSON format"}


def handle_get_state(ui_instance, request: dict) -> dict:
    """
    Handles the GET_STATE command.

    Expected keys in request: none.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict containing status and the current UI state.
    """
    state = {"active_scans": ui_instance.active_scans}
    return {"status": "OK", "state": state}


def handle_send_scan(ui_instance, request: dict) -> dict:
    """
    Handles the SEND_SCAN command.

    Expected keys in request:
        - "tool": The tool name (str).
        - "scan_profile": The scan profile to use (str).
        - "command": A command dictionary containing keys 'executable' (str) and 'arguments' (List[str]),
                     and also an "interface" key indicating the scanning interface.

    This function calls the UIManager to allocate a pane and run the command.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with a "status" key (e.g., "SEND_SCAN_OK") and a "pane_id" if successful,
             otherwise an "error" key.
    """
    tool_name = request.get("tool")
    scan_profile = request.get("scan_profile")
    cmd_dict = request.get("command")
    if not all([tool_name, scan_profile, cmd_dict]):
        return {ERROR_KEY: "Missing parameters for SEND_SCAN"}
    pane_id = ui_instance.allocate_scan_pane(tool_name, scan_profile, cmd_dict)
    if pane_id:
        return {"status": "SEND_SCAN_OK", "pane_id": pane_id}
    else:
        return {ERROR_KEY: "Failed to allocate scan pane"}


def handle_get_scans(ui_instance, request: dict) -> dict:
    """
    Handles the GET_SCANS command.

    Expected keys in request:
        - "tool": The tool name (str).

    Returns a list of active scan data (as dicts) for the specified tool.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "OK" and "scans": [list of scan data dicts],
             or an "error" key if parameters are missing.
    """
    tool_name = request.get("tool")
    if not tool_name:
        return {ERROR_KEY: "Missing tool parameter for GET_SCANS"}
    scans = [scan.to_dict() for scan in ui_instance.active_scans.values()
             if scan.tool.lower() == tool_name.lower()]
    return {"status": "OK", "scans": scans}


def handle_swap_scan(ui_instance, request: dict) -> dict:
    """
    Handles the SWAP_SCAN command.

    Expected keys in request:
        - "tool": The tool name (str).
        - "pane_id": The pane ID (str) to swap.
        - "new_title": The new internal title (str) to assign.

    Calls the UIManager to swap the specified pane into the main UI.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "SWAP_SCAN_OK" if successful,
             or an "error" key describing the issue.
    """
    tool_name = request.get("tool")
    pane_id = request.get("pane_id")
    new_title = request.get("new_title")
    if not all([tool_name, pane_id, new_title]):
        return {ERROR_KEY: "Missing parameters for SWAP_SCAN"}
    try:
        ui_instance.swap_scan(tool_name, pane_id, new_title)
        return {"status": "SWAP_SCAN_OK"}
    except Exception as e:
        return {ERROR_KEY: f"SWAP_SCAN error: {e}"}


def handle_stop_scan(ui_instance, request: dict) -> dict:
    """
    Handles the STOP_SCAN command.

    Expected keys in request:
        - "tool": The tool name (str).
        - "pane_id": The pane ID (str) of the scan to stop.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "STOP_SCAN_OK" if successful,
             or an "error" key if parameters are missing or an error occurs.
    """
    tool_name = request.get("tool")
    pane_id = request.get("pane_id")
    if not all([tool_name, pane_id]):
        return {ERROR_KEY: "Missing parameters for STOP_SCAN"}
    try:
        ui_instance.stop_scan(pane_id)
        return {"status": "STOP_SCAN_OK"}
    except Exception as e:
        return {ERROR_KEY: f"STOP_SCAN error: {e}"}


def handle_update_lock(ui_instance, request: dict) -> dict:
    """
    Handles the UPDATE_LOCK command.

    Expected keys in request:
        - "iface": The interface to lock (str).
        - "tool": The tool name (str) requesting the lock.

    Updates the UIManager's interface registry to mark the interface as locked.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "UPDATE_LOCK_OK" if successful,
             or an "error" key if parameters are missing or an error occurs.
    """
    iface = request.get("iface")
    tool_name = request.get("tool")
    if not all([iface, tool_name]):
        return {ERROR_KEY: "Missing parameters for UPDATE_LOCK"}
    try:
        ui_instance.update_interface(iface, True)
        return {"status": "UPDATE_LOCK_OK"}
    except Exception as e:
        return {ERROR_KEY: f"UPDATE_LOCK error: {e}"}


def handle_remove_lock(ui_instance, request: dict) -> dict:
    """
    Handles the REMOVE_LOCK command.

    Expected keys in request:
        - "iface": The interface to unlock (str).

    Updates the UIManager's interface registry to mark the interface as unlocked.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "REMOVE_LOCK_OK" if successful,
             or an "error" key if parameters are missing or an error occurs.
    """
    iface = request.get("iface")
    if not iface:
        return {ERROR_KEY: "Missing iface parameter for REMOVE_LOCK"}
    try:
        ui_instance.update_interface(iface, False)
        return {"status": "REMOVE_LOCK_OK"}
    except Exception as e:
        return {ERROR_KEY: f"REMOVE_LOCK error: {e}"}


def handle_kill_ui(ui_instance, request: dict) -> dict:
    """
    Handles the KILL_UI command.

    No additional parameters are expected.
    This should terminate the UI session.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "KILL_UI_OK" if successful,
             or an "error" key if an error occurs.
    """
    try:
        ui_instance.kill_ui()
        return {"status": "KILL_UI_OK"}
    except Exception as e:
        return {ERROR_KEY: f"KILL_UI error: {e}"}


def handle_detach_ui(ui_instance, request: dict) -> dict:
    """
    Handles the DETACH_UI command.

    No additional parameters are expected.
    This should detach the UI session.

    :param ui_instance: The UIManager instance.
    :param request: The request dictionary.
    :return: A dict with "status": "DETACH_UI_OK" if successful,
             or an "error" key if an error occurs.
    """
    try:
        ui_instance.detach_ui()
        return {"status": "DETACH_UI_OK"}
    except Exception as e:
        return {ERROR_KEY: f"DETACH_UI error: {e}"}
