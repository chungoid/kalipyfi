import json
import time
import psutil
import logging

# local
from common.process_manager import process_manager
from config.constants import IPC_CONSTANTS

logger = logging.getLogger(__name__)


ERROR_KEY = IPC_CONSTANTS["keys"]["ERROR_KEY"]

def pack_message(message: dict) -> str:
    """
    Packs a dictionary into a JSON-formatted string.

    :param message: Dictionary containing the message to pack.
    :return: A JSON string representation of the message.
    :raises Exception: If the message cannot be serialized to JSON.
    """
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
    Unpacks a JSON-formatted string into a dictionary.

    :param message_str: The JSON string to unpack.
    :return: A dictionary representation of the message, or an error dictionary if unpacking fails.
    """
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
    """
    Registers a process via IPC.

    :param ui_instance: The UI manager instance (not used directly here).
    :param request: The request dictionary containing 'role' and 'pid'.
    :return: A dictionary with status "REGISTER_PROCESS_OK" if successful,
             otherwise an error dictionary.
    """
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
    """
    Checks if the UI is ready based on a readiness flag.

    :param ui_instance: The UI manager instance containing the readiness flag.
    :param request: The request dictionary (not used directly).
    :return: A dictionary with "status": "UI_READY_OK" if ready,
             or "status": "UI_NOT_READY" if not.
    """
    if getattr(ui_instance, "ready", False):
        logger.debug("UI is ready.")
        return {"status": "UI_READY_OK"}
    else:
        logger.debug("UI is not ready.")
        return {"status": "UI_NOT_READY"}

def handle_get_state(ui_instance, request: dict) -> dict:
    """
    Retrieves the current state of the UI.

    :param ui_instance: The UI manager instance containing state information.
    :param request: The request dictionary for the GET_STATE command.
    :return: A dictionary with "status": "OK" and the UI state under "state",
             or an error dictionary if an exception occurs.
    """
    logger.debug("handle_get_state: Called")
    try:
        state = {"active_scans": ui_instance.active_scans}
        logger.debug(f"handle_get_state: Returning state: {state}")
        return {"status": "OK", "state": state}
    except Exception as e:
        logger.exception("handle_get_state: Exception")
        logger.exception(e)
        return {ERROR_KEY: str(e)}

def handle_send_scan(ui_instance, request):
    tool_name = request.get("tool")
    cmd_dict = request.get("command")
    interface = request.get("interface", "unknown")
    preset_description = request.get("preset_description")
    timestamp = request.get("timestamp")
    callback_socket = request.get("callback_socket")

    if not all([tool_name, preset_description, cmd_dict]):
        logger.error("handle_send_scan: Missing required arguments.")
        return {"error": "MISSING_REQUIRED_ARGUMENTS"}

    # Allocate the scan pane in the UI.
    pane_id = ui_instance.allocate_scan_window(
        tool_name=tool_name,
        cmd_dict=cmd_dict,
        interface=interface,
        timestamp=timestamp,
        preset_description=preset_description,
        pane_pid=None,
        callback_socket=callback_socket
    )
    if not pane_id:
        logger.error("handle_send_scan: Failed to create scan pane.")
        return {"error": "FAILED_TO_CREATE_SCAN_PANE"}

    # Retrieve the process id stored in our active scans.
    pane_pid = ui_instance.active_scans[pane_id].pane_pid

    def wait_and_notify():
        try:
            logger.debug(f"Monitoring scan PID {pane_pid} with psutil.")
            # Poll until the process is no longer running.
            while True:
                try:
                    proc = psutil.Process(pane_pid)
                    if not proc.is_running():
                        break
                except psutil.NoSuchProcess:
                    break
                time.sleep(1)  # Poll every second.
            logger.debug(f"Scan PID {pane_pid} completed successfully (psutil detected termination).")
        except Exception as e:
            logger.error(f"Error monitoring scan PID {pane_pid}: {e}")

        # Notify the callback socket about scan completion.
        try:
            cb_socket = request.get("callback_socket")
            if cb_socket:
                from utils.ipc import notify_scan_complete
                notify_scan_complete(cb_socket, pane_id, pane_pid, tool_name)
                logger.debug(f"Sent SCAN_COMPLETE for PID {pane_pid} to socket {cb_socket}.")
            else:
                logger.warning("Callback socket missing; no SCAN_COMPLETE sent.")
        except Exception as e:
            logger.error(f"Error during callback notification: {e}")

    # Start the monitoring thread in a try/except block.
    try:
        from threading import Thread
        Thread(target=wait_and_notify, daemon=True).start()
    except Exception as e:
        logger.error(f"Error starting wait_and_notify thread: {e}")

    # Return a response so that IPCServer can later retrieve pane_pid.
    return {
        "status": "SEND_SCAN_OK",
        "pane_id": pane_id,
        "pane_pid": pane_pid
    }

def handle_get_scans(ui_instance, request: dict) -> dict:
    """
    Retrieves a list of active scans for a specified tool.

    Expected Format:
        {
            "action": "GET_SCANS",
            "tool": <tool_name>
        }

    :param ui_instance: The UI manager instance containing scan information.
    :param request: The request dictionary for the GET_SCANS command.
    :return: A dictionary with "status": "OK" and "scans": <list of scans> if successful,
             or an error dictionary if parameters are missing or an exception occurs.
    """
    logger.debug(f"handle_get_scans: Received request: {request}")
    tool_name = request.get("tool")
    if not tool_name:
        logger.error("handle_get_scans: Missing tool parameter")
        return {IPC_CONSTANTS["keys"]["ERROR_KEY"]: "Missing tool parameter for GET_SCANS"}

    matching_scans = []
    for pane_id, scan in ui_instance.active_scans.items():
        try:
            # log basic info about each scan object
            logger.debug(f"Processing scan from pane {pane_id}: type={type(scan)}, scan={scan}")
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
    Handles the SWAP_SCAN command by swapping a dedicated scan pane with the main scan pane.

    Expected Format:
        {
            "tool": <tool_name>,
            "pane_id": <pane_id>,
            "new_title": <new_title>
        }

    :param ui_instance: The UI manager instance that will process the swap.
    :param request: The request dictionary containing the swap parameters.
    :return: A dictionary with "status": "SWAP_SCAN_OK" if successful,
             or an error dictionary if parameters are missing or an exception occurs.
    """
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

    :param ui_instance: The UI manager instance responsible for stopping scans.
    :param request: The request dictionary for the STOP_SCAN command.
    :return: A dictionary with "status": "STOP_SCAN_OK" if the scan is stopped successfully,
             or an error dictionary if parameters are missing or an exception occurs.
    """
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

def handle_kill_window(ui_instance, request: dict) -> dict:
    """
    Handles the KILL_WINDOW action via IPC.

    Expected request format:
        {
            "action": "KILL_WINDOW",
            "pane_id": <pane_id>
        }
    where <pane_id> is a string representing the tmux pane ID for the background window to kill.

    :param ui_instance: The UIManager instance controlling the current session.
    :param request: A dictionary containing the IPC request. It must include the key 'pane_id'.
    :return: A dictionary with either:
             {"status": "KILL_WINDOW_OK"} if the window was successfully killed, or
             {<ERROR_KEY>: "Error message"} if an error occurred.
    """
    pane_id = request.get("pane_id")
    if not pane_id:
        return {IPC_CONSTANTS["keys"]["ERROR_KEY"]: "Missing pane_id"}
    try:
        ui_instance.kill_window(pane_id)
        return {"status": "KILL_WINDOW_OK"}
    except Exception as e:
        return {IPC_CONSTANTS["keys"]["ERROR_KEY"]: str(e)}

def handle_connect_network(ui_instance, request: dict) -> dict:
    """
    Handles the CONNECT_NETWORK command by launching the nmcli connection command.

    Expected Format:
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

    :param ui_instance: The UI manager instance that handles network connections.
    :param request: The request dictionary for the CONNECT_NETWORK command.
    :return: A dictionary with "status": "CONNECT_NETWORK_OK" and "pane_id": <pane_id> if successful,
             or an error dictionary if parameters are missing or an exception occurs.
    """
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
        # reuse the UI manager method to allocate a new window/pane
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

    :param ui_instance: The UI manager instance that manages interface locks.
    :param request: The request dictionary containing the interface and tool information.
    :return: A dictionary with "status": "UPDATE_LOCK_OK" if the interface is locked successfully,
             or an error dictionary if parameters are missing or an exception occurs.
    """
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

    :param ui_instance: The UI manager instance that manages interface locks.
    :param request: The request dictionary containing the interface to unlock.
    :return: A dictionary with "status": "REMOVE_LOCK_OK" if successful,
             or an error dictionary if the interface parameter is missing or an exception occurs.
    """
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

    :param ui_instance: The UI manager instance that controls the UI session.
    :param request: The request dictionary for the KILL_UI command.
    :return: A dictionary with "status": "KILL_UI_OK" if the UI session is terminated successfully,
             or an error dictionary if an exception occurs.
    """
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
    Handles the DETACH_UI command by detaching the UI session from the client.

    Expected Format:
        {
            "action": "DETACH_UI"
        }

    :param ui_instance: The UI manager instance that controls the UI session.
    :param request: The request dictionary for the DETACH_UI command.
    :return: A dictionary with "status": "DETACH_UI_OK" if the UI session is detached successfully,
             or an error dictionary if an exception occurs.
    """
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

    :param ui_instance: The UI manager instance that contains process tracking information.
    :param request: The request dictionary for the DEBUG_STATUS command.
    :return: A dictionary with "status": "DEBUG_STATUS_OK" and "report": <status report string>,
             or an error dictionary if an exception occurs.
    """
    logger.debug("handle_debug_status: Called")
    from common.process_manager import process_manager
    report = process_manager.get_status_report()
    logger.debug(f"handle_debug_status: Report: {report}")
    return {"status": "DEBUG_STATUS_OK", "report": report}

def handle_ping(ui_instance, request: dict) -> dict:
    """
    Handles the PING command to confirm that the IPC connection is active.

    Expected Format:
        {
            "action": "PING"
        }

    :param ui_instance: The UI manager instance (not used directly in this function).
    :param request: The request dictionary for the PING command.
    :return: A dictionary with "status": "PING_OK".
    """
    logger.debug("handle_ping: Received ping request")
    return {"status": "PING_OK"}