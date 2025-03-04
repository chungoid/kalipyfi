import json
import logging

# local
from config.constants import IPC_CONSTANTS

ERROR_KEY = IPC_CONSTANTS["keys"]["ERROR_KEY"]

def pack_message(message: dict) -> str:
    """
    Converts a message dictionary into a JSON string.

    Expected Format:
        A Python dictionary representing the message to be sent.

    Parameters
    ----------
    message : dict
        The message data to be serialized into JSON.

    Returns
    -------
    str
        The resulting JSON string.

    Raises
    ------
    Exception
        If there is an error during JSON serialization.
    """
    logger = logging.getLogger("ipc_proto:pack_message")
    logger.debug(f"pack_message: Packing message: {message}")
    try:
        json_str = json.dumps(message)
        logger.debug(f"pack_message: Resulting JSON string: {json_str}")
        return json_str
    except Exception as e:
        logger.exception("pack_message: Exception while packing message")
        raise

def unpack_message(message_str: str) -> dict:
    """
    Converts a JSON string into a message dictionary.

    Expected Format:
        A JSON-formatted string representing the message.

    Parameters
    ----------
    message_str : str
        The JSON string to be deserialized.

    Returns
    -------
    dict
        The resulting message dictionary. If JSON decoding fails, returns a dictionary
        with an error key.
    """
    logger = logging.getLogger("ipc_proto:unpack_message")
    logger.debug(f"unpack_message: Unpacking message string: {message_str}")
    try:
        message = json.loads(message_str)
        logger.debug(f"unpack_message: Unpacked message: {message}")
        return message
    except json.JSONDecodeError:
        logger.error("unpack_message: Invalid JSON format")
        return {ERROR_KEY: "Invalid JSON format"}
    except Exception as e:
        logger.exception("unpack_message: Exception while unpacking message")
        return {ERROR_KEY: str(e)}

def handle_get_state(ui_instance, request: dict) -> dict:
    """
    Handles the GET_STATE command by retrieving the current state of the UI.

    Expected Format:
        {
            "action": "GET_STATE",
            // additional optional keys may be present
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance containing the current state.
    request : dict
        The request dictionary for the GET_STATE command.

    Returns
    -------
    dict
        A dictionary with keys:
            "status": "OK" if successful,
            "state": containing state information (e.g. active scans),
        or an error dictionary if an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_get_state")
    logger.debug("handle_get_state: Called")
    try:
        state = {"active_scans": ui_instance.active_scans}
        logger.debug(f"handle_get_state: Returning state: {state}")
        return {"status": "OK", "state": state}
    except Exception as e:
        logger.exception("handle_get_state: Exception")
        return {ERROR_KEY: str(e)}

def handle_send_scan(ui_instance, request: dict) -> dict:
    """
    Handles the SEND_SCAN command by allocating a new scan pane and launching the scan command.

    Expected Format:
        {
            "action": "SEND_SCAN",
            "tool": <tool_name>,
            "scan_profile": <scan_profile>,
            "command": <cmd_dict>,  // A dictionary with keys 'executable' and 'arguments'
            "timestamp": <timestamp>  // (Optional) A timestamp value
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance responsible for scan operations.
    request : dict
        The request dictionary for the SEND_SCAN command.

    Returns
    -------
    dict
        A dictionary with:
            "status": "SEND_SCAN_OK" and "pane_id": <pane_id> if successful,
        or an error dictionary with an appropriate error message.
    """
    logger = logging.getLogger("ipc_proto:handle_send_scan")
    logger.debug(f"handle_send_scan: Received request: {request}")
    tool_name = request.get("tool")                  # tool which sent the scan
    scan_profile = request.get("scan_profile")       # selected profile from 'preset'
    cmd_dict = request.get("command")                # built command to be run in tmux
    interface = request.get("interface", "unknown")  # selected scan interface from submenu
    timestamp = request.get("timestamp")
    if not all([tool_name, scan_profile, cmd_dict]):
        logger.error("handle_send_scan: Missing parameters")
        return {ERROR_KEY: "Missing parameters for SEND_SCAN"}
    try:
        pane_id = ui_instance.allocate_scan_window(tool_name, scan_profile, cmd_dict, interface, timestamp)
        if pane_id:
            logger.debug(f"handle_send_scan: Successfully allocated pane: {pane_id}")
            return {"status": "SEND_SCAN_OK", "pane_id": pane_id}
        else:
            logger.error("handle_send_scan: Failed to allocate scan pane")
            return {ERROR_KEY: "Failed to allocate scan pane"}
    except Exception as e:
        logger.exception("handle_send_scan: Exception occurred")
        return {ERROR_KEY: str(e)}

def handle_get_scans(ui_instance, request: dict) -> dict:
    """
     Handles the GET_SCANS command by retrieving a list of active scans for a specified tool.

    Expected Format:
        {
            "action": "GET_SCANS",
            "tool": <tool_name>
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance containing scan information.
    request : dict
        The request dictionary for the GET_SCANS command.

    Returns
    -------
    dict
        A dictionary with:
            "status": "OK" and "scans": <list of scans> if successful,
        or an error dictionary if an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_get_scans")
    logger.debug(f"handle_get_scans: Received request: {request}")
    tool_name = request.get("tool")
    if not tool_name:
        logger.error("handle_get_scans: Missing tool parameter")
        return {ERROR_KEY: "Missing tool parameter for GET_SCANS"}
    try:
        scans = [scan.to_dict() for scan in ui_instance.active_scans.values()
                 if scan.tool.lower() == tool_name.lower()]
        logger.debug(f"handle_get_scans: Found scans: {scans}")
        return {"status": "OK", "scans": scans}
    except Exception as e:
        logger.exception("handle_get_scans: Exception occurred")
        return {ERROR_KEY: str(e)}


def handle_swap_scan(ui_instance, request: dict) -> dict:
    """
    Handles the SWAP_SCAN command.

    Expected Format:
        {
            "tool": <tool_name>,
            "pane_id": <pane_id>,
            "new_title": <new_title>
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that will process the command.
    request : dict
        A dictionary containing the SWAP_SCAN parameters.

    Returns
    -------
    dict
        A dictionary containing either a success status ("SWAP_SCAN_OK") or an error message
        with the key specified by ERROR_KEY.
    """

    logger = logging.getLogger("ipc_proto:handle_swap_scan")
    logger.debug(f"handle_swap_scan: Received request: {request}")
    tool_name = request.get("tool")
    pane_id = request.get("pane_id")
    new_title = request.get("new_title")
    if not all([tool_name, pane_id, new_title]):
        logger.error("handle_swap_scan: Missing parameters")
        return {ERROR_KEY: "Missing parameters for SWAP_SCAN"}
    try:
        ui_instance.swap_scan(tool_name, pane_id, new_title)
        logger.debug("handle_swap_scan: Swap successful")
        return {"status": "SWAP_SCAN_OK"}
    except Exception as e:
        logger.exception("handle_swap_scan: Exception occurred")
        return {ERROR_KEY: f"SWAP_SCAN error: {e}"}


def handle_stop_scan(ui_instance, request: dict) -> dict:
    """
     Handles the STOP_SCAN command by terminating the scan running in a specified pane.

    Expected Format:
        {
            "action": "STOP_SCAN",
            "tool": <tool_name>,
            "pane_id": <pane_id>
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that will stop the scan.
    request : dict
        A dictionary containing the STOP_SCAN parameters.

    Returns
    -------
    dict
        A dictionary with:
            "status": "STOP_SCAN_OK" if successful,
        or an error dictionary if parameters are missing or an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_stop_scan")
    logger.debug(f"handle_stop_scan: Received request: {request}")
    tool_name = request.get("tool")
    pane_id = request.get("pane_id")
    if not all([tool_name, pane_id]):
        logger.error("handle_stop_scan: Missing parameters")
        return {ERROR_KEY: "Missing parameters for STOP_SCAN"}
    try:
        ui_instance.stop_scan(pane_id)
        logger.debug("handle_stop_scan: Scan stopped successfully")
        return {"status": "STOP_SCAN_OK"}
    except Exception as e:
        logger.exception("handle_stop_scan: Exception occurred")
        return {ERROR_KEY: f"STOP_SCAN error: {e}"}


def handle_update_lock(ui_instance, request: dict) -> dict:
    """
     Handles the UPDATE_LOCK command by setting the lock status of a specified interface.

    Expected Format:
        {
            "action": "UPDATE_LOCK",
            "tool": <tool_name>,
            "iface": <interface>
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that manages interface locks.
    request : dict
        A dictionary containing the UPDATE_LOCK parameters.

    Returns
    -------
    dict
        A dictionary with:
            "status": "UPDATE_LOCK_OK" if the interface is locked successfully,
        or an error dictionary if parameters are missing or an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_update_lock")
    logger.debug(f"handle_update_lock: Received request: {request}")
    iface = request.get("iface")
    tool_name = request.get("tool")
    if not all([iface, tool_name]):
        logger.error("handle_update_lock: Missing parameters")
        return {ERROR_KEY: "Missing parameters for UPDATE_LOCK"}
    try:
        ui_instance.update_interface(iface, True)
        logger.debug(f"handle_update_lock: Interface {iface} locked")
        return {"status": "UPDATE_LOCK_OK"}
    except Exception as e:
        logger.exception("handle_update_lock: Exception occurred")
        return {ERROR_KEY: f"UPDATE_LOCK error: {e}"}


def handle_remove_lock(ui_instance, request: dict) -> dict:
    """
     Handles the REMOVE_LOCK command by unlocking a specified interface.

    Expected Format:
        {
            "action": "REMOVE_LOCK",
            "iface": <interface>
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that manages interface locks.
    request : dict
        A dictionary containing the REMOVE_LOCK parameters.

    Returns
    -------
    dict
        A dictionary with:
            "status": "REMOVE_LOCK_OK" if successful,
        or an error dictionary if the interface parameter is missing or an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_remove_lock")
    logger.debug(f"handle_remove_lock: Received request: {request}")
    iface = request.get("iface")
    if not iface:
        logger.error("handle_remove_lock: Missing iface parameter")
        return {ERROR_KEY: "Missing iface parameter for REMOVE_LOCK"}
    try:
        ui_instance.update_interface(iface, False)
        logger.debug(f"handle_remove_lock: Interface {iface} unlocked")
        return {"status": "REMOVE_LOCK_OK"}
    except Exception as e:
        logger.exception("handle_remove_lock: Exception occurred")
        return {ERROR_KEY: f"REMOVE_LOCK error: {e}"}


def handle_kill_ui(ui_instance, request: dict) -> dict:
    """
    Handles the KILL_UI command by terminating the UI session.

    Expected Format:
        {
            "action": "KILL_UI"
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that controls the UI session.
    request : dict
        A dictionary containing the KILL_UI command.

    Returns
    -------
    dict
        A dictionary with:
            "status": "KILL_UI_OK" if the UI session is killed successfully,
        or an error dictionary if an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_kill_ui")
    logger.debug(f"handle_kill_ui: Received request: {request}")
    try:
        session_name = ui_instance.session_data.session_name
        logger.debug(f"handle_kill_ui: Killing UI session: {session_name}")
        ui_instance.kill_ui()
        logger.debug("handle_kill_ui: Kill command executed successfully")
        return {"status": "KILL_UI_OK"}
    except Exception as e:
        logger.exception("handle_kill_ui: Exception occurred")
        return {ERROR_KEY: f"KILL_UI error: {e}"}


def handle_detach_ui(ui_instance, request: dict) -> dict:
    """
    Handles the DETACH_UI command by detaching the UI session.

    Expected Format:
        {
            "action": "DETACH_UI"
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that controls the UI session.
    request : dict
        A dictionary containing the DETACH_UI command.

    Returns
    -------
    dict
        A dictionary with:
            "status": "DETACH_UI_OK" if the UI session is detached successfully,
        or an error dictionary if an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_detach_ui")
    logger.debug(f"handle_detach_ui: Received request: {request}")
    try:
        session_name = ui_instance.session_data.session_name
        logger.debug(f"handle_detach_ui: Detaching UI session: {session_name}")
        ui_instance.detach_ui()
        logger.debug("handle_detach_ui: Detach command executed successfully")
        return {"status": "DETACH_UI_OK"}
    except Exception as e:
        logger.exception("handle_detach_ui: Exception occurred")
        return {ERROR_KEY: f"DETACH_UI error: {e}"}


def handle_debug_status(ui_instance, request: dict) -> dict:
    """
    Handles the DEBUG_STATUS command by retrieving a report of the current process status.

    Expected Format:
        {
            "action": "DEBUG_STATUS"
        }

    Parameters
    ----------
    ui_instance : object
        The UI manager instance that contains process tracking information.
    request : dict
        A dictionary containing the DEBUG_STATUS command.

    Returns
    -------
    dict
        A dictionary with:
            "status": "DEBUG_STATUS_OK" and "report": <status report string>,
        or an error dictionary if an exception occurs.
    """
    logger = logging.getLogger("ipc_proto:handle_debug_status")
    logger.debug("handle_debug_status: Called")
    from common.process_manager import process_manager
    report = process_manager.get_status_report()
    logger.debug(f"handle_debug_status: Report: {report}")
    return {"status": "DEBUG_STATUS_OK", "report": report}

def handle_ping(ui_instance, request: dict) -> dict:
    """
    Handles the PING command. Simply returns a confirmation that the IPC connection is active.

    Expected Format:
        {
            "action": "PING"
        }

    Returns
    -------
    dict
        A dictionary with:
            "status": "PING_OK" if successful.
    """
    logger = logging.getLogger("ipc_proto:handle_ping")
    logger.debug("handle_ping: Received ping request")
    return {"status": "PING_OK"}