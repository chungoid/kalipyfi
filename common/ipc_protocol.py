import json
import logging
import time

# local
from common.process_manager import process_manager
from config.constants import IPC_CONSTANTS


ERROR_KEY = IPC_CONSTANTS["keys"]["ERROR_KEY"]

def pack_message(message: dict) -> str:
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

def handle_register_process(ui_instance, request: dict) -> dict:
    role = request.get("role")
    pid = request.get("pid")
    if role and pid:
        process_manager.register_process(role, pid)
        logging.debug(f"Registered process via IPC: role={role}, pid={pid}")
        return {"status": "REGISTER_PROCESS_OK"}
    else:
        logging.error("REGISTER_PROCESS missing 'role' or 'pid'")
        return {"error": "Missing role or pid"}

def handle_ui_ready(ui_instance, request: dict) -> dict:
    logger = logging.getLogger("ipc_proto:handle_ui_ready")
    # Check a flag on the UI instance indicating readiness.
    if getattr(ui_instance, "ready", False):
        logger.debug("UI is ready.")
        return {"status": "UI_READY_OK"}
    else:
        logger.debug("UI is not ready.")
        return {"status": "UI_NOT_READY"}

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
        logger.exception(e)
        return {ERROR_KEY: str(e)}

def handle_send_scan(ui_instance, request: dict) -> dict:
    """
    Handles the SEND_SCAN command by allocating a new scan window and launching the scan command.

    def allocate_scan_window(self, tool_name: str, cmd_dict: dict, interface: str,
                             timestamp: float, preset_description: str) -> str:
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
    #scan_profile = request.get("scan_profile")       # selected profile from 'preset'
    cmd_dict = request.get("command")                # built command to be run in tmux
    interface = request.get("interface", "unknown")
    preset_description = request.get("preset_description")
    timestamp = request.get("timestamp")
    if not all([tool_name, preset_description, cmd_dict]):
        logger.error("handle_send_scan: Missing parameters")
        return {ERROR_KEY: "Missing parameters for SEND_SCAN"}
    try:
        pane_id = ui_instance.allocate_scan_window(tool_name, cmd_dict, interface, timestamp, preset_description)
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
        return {IPC_CONSTANTS["keys"]["ERROR_KEY"]: "Missing tool parameter for GET_SCANS"}

    matching_scans = []
    for pane_id, scan in ui_instance.active_scans.items():
        try:
            # Log basic info about each scan object.
            logger.debug(f"Processing scan from pane {pane_id}: type={type(scan)}, scan={scan}")
            # Make sure scan has a 'tool' attribute.
            if not hasattr(scan, "tool"):
                logger.error(f"Scan in pane {pane_id} has no 'tool' attribute: {scan}")
                continue

            if scan.tool.lower() == tool_name.lower():
                scan_dict = scan.to_dict()
                matching_scans.append(scan_dict)
                logger.debug(f"Added scan: {scan_dict}")
            else:
                logger.debug(f"Scan from pane {pane_id} does not match tool '{tool_name}'. Found tool: '{scan.tool}'")
        except Exception as e:
            logger.exception(f"Error processing scan from pane {pane_id}: {e}")

    logger.debug(f"handle_get_scans: Total matching scans: {len(matching_scans)}")
    return {"status": "OK", "scans": matching_scans}


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


def handle_connect_network(ui_instance, request: dict) -> dict:
    """
    Handles the CONNECT_NETWORK command by launching the nmcli connection command.

    Expected request format:
      {
         "action": "CONNECT_NETWORK",
         "tool": <tool_name>,
         "network": <SSID>,
         "command": {
             "executable": "nmcli",
             "arguments": ["device", "wifi", "connect", <SSID>, "ifname", <interface>, ...]
         },
         "interface": <interface>,
         "timestamp": <timestamp>
      }

    The handler launches the command in a dedicated window/pane and returns a response
    with the pane_id if successful.
    """
    logger = logging.getLogger("ipc_proto:handle_connect_network")
    logger.debug("handle_connect_network: Received request: %s", request)

    tool_name = request.get("tool")
    network = request.get("network")
    cmd_dict = request.get("command")
    interface = request.get("interface", "unknown")
    timestamp = request.get("timestamp", time.time())

    if not all([tool_name, network, cmd_dict]):
        logger.error("handle_connect_network: Missing parameters")
        return {ERROR_KEY: "Missing parameters for CONNECT_NETWORK"}

    try:
        # Reuse the UI manager method to allocate a new window/pane.
        pane_id = ui_instance.allocate_scan_window(tool_name, network, cmd_dict, interface, timestamp)
        if pane_id:
            logger.debug("handle_connect_network: Successfully allocated pane: %s", pane_id)
            return {"status": "CONNECT_NETWORK_OK", "pane_id": pane_id}
        else:
            logger.error("handle_connect_network: Failed to allocate connection pane")
            return {ERROR_KEY: "Failed to allocate connection pane"}
    except Exception as e:
        logger.exception("handle_connect_network: Exception occurred")
        return {ERROR_KEY: str(e)}


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