# ipc.py
import logging
import socket
import os
import time
from common.ipc_protocol import (
    pack_message, unpack_message, handle_get_state, handle_get_scans,
    handle_send_scan, handle_swap_scan, handle_update_lock,
    handle_remove_lock, handle_stop_scan, handle_kill_ui, handle_detach_ui, handle_debug_status
)
from common.logging_setup import worker_configurer, get_log_queue
from config.constants import IPC_CONSTANTS, DEFAULT_SOCKET_PATH, RETRY_DELAY

ACTION_KEY       = IPC_CONSTANTS["keys"]["ACTION_KEY"]
ERROR_KEY        = IPC_CONSTANTS["keys"]["ERROR_KEY"]
TOOL_KEY         = IPC_CONSTANTS["keys"]["TOOL_KEY"]
SCAN_PROFILE_KEY = IPC_CONSTANTS["keys"]["SCAN_PROFILE_KEY"]
COMMAND_KEY      = IPC_CONSTANTS["keys"]["COMMAND_KEY"]
TIMESTAMP_KEY    = IPC_CONSTANTS["keys"]["TIMESTAMP_KEY"]
STATUS_KEY       = IPC_CONSTANTS["keys"]["STATUS_KEY"]
RESULT_KEY       = IPC_CONSTANTS["keys"]["RESULT_KEY"]

GET_STATE     = IPC_CONSTANTS["actions"]["GET_STATE"]
GET_SCANS     = IPC_CONSTANTS["actions"]["GET_SCANS"]
SEND_SCAN     = IPC_CONSTANTS["actions"]["SEND_SCAN"]
SWAP_SCAN     = IPC_CONSTANTS["actions"]["SWAP_SCAN"]
STOP_SCAN     = IPC_CONSTANTS["actions"]["STOP_SCAN"]
UPDATE_LOCK   = IPC_CONSTANTS["actions"]["UPDATE_LOCK"]
REMOVE_LOCK   = IPC_CONSTANTS["actions"]["REMOVE_LOCK"]
KILL_UI       = IPC_CONSTANTS["actions"]["KILL_UI"]
DETACH_UI     = IPC_CONSTANTS["actions"]["DETACH_UI"]
DEBUG_STATUS = IPC_CONSTANTS["actions"]["DEBUG_STATUS"]


def send_ipc_command(message: dict, socket_path: str = DEFAULT_SOCKET_PATH) -> dict:
    """
    Sends a structured message (as dict) to the IPC server and returns the response as a dict.
    Extensive debugging is added.
    """
    logger = logging.getLogger("ipc:send_ipc_command")
    logger.debug(f"send_ipc_command: Called with message: {message} and socket_path: {socket_path}")
    attempt = 0
    while attempt < 3:
        try:
            logger.debug(f"send_ipc_command: Attempt {attempt+1}: Creating socket.")
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            logger.debug("send_ipc_command: Attempting to connect...")
            client.connect(socket_path)
            message_str = pack_message(message)
            logger.debug(f"send_ipc_command: Sending message string: {message_str}")
            client.send(message_str.encode())
            response_bytes = client.recv(1024)
            response_str = response_bytes.decode().strip()
            logger.debug(f"send_ipc_command: Received response string: {response_str}")
            client.close()
            unpacked = unpack_message(response_str)
            logger.debug(f"send_ipc_command: Unpacked response: {unpacked}")
            return unpacked
        except (ConnectionResetError, ConnectionRefusedError) as e:
            attempt += 1
            logger.warning(f"send_ipc_command: Connection error on attempt {attempt}: {e}. Retrying in {RETRY_DELAY} seconds.")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.exception("send_ipc_command: Exception occurred")
            return {ERROR_KEY: str(e)}
    logger.error(f"send_ipc_command: Failed after {attempt} attempts")
    return {ERROR_KEY: f"Failed after {attempt} attempts"}


def ipc_server(ui_instance, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
    logger = logging.getLogger("ipc:ipc_server")
    logger.debug(f"ipc_server: Starting with socket_path: {socket_path}")

    if os.path.exists(socket_path):
        logger.debug(f"ipc_server: Removing existing socket at {socket_path}")
        os.remove(socket_path)

    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(socket_path)
        server.listen(10)
        logger.info("ipc_server: Listening for connections...")
    except Exception as e:
        logger.exception(f"ipc_server: Failed to bind or listen on {socket_path}")
        return

    while True:
        try:
            logger.debug("ipc_server: Waiting for incoming connection...")
            conn, _ = server.accept()
            logger.debug("ipc_server: Connection accepted.")

            try:
                data = conn.recv(1024).decode().strip()
                if not data:
                    logger.error("ipc_server: Received empty data, closing connection.")
                    conn.close()
                    continue

                logger.debug(f"ipc_server: Raw data received: {data}")
                request = unpack_message(data)
                logger.debug(f"ipc_server: Unpacked request: {request}")

                action = request.get("action", "UNKNOWN")
                logger.debug(f"ipc_server: Action determined: {action}")

                if action == GET_STATE:
                    response = handle_get_state(ui_instance, request)
                elif action == DEBUG_STATUS:
                    response = handle_debug_status(ui_instance, request)
                elif action == GET_SCANS:
                    response = handle_get_scans(ui_instance, request)
                elif action == SEND_SCAN:
                    response = handle_send_scan(ui_instance, request)
                elif action == SWAP_SCAN:
                    response = handle_swap_scan(ui_instance, request)
                elif action == UPDATE_LOCK:
                    response = handle_update_lock(ui_instance, request)
                elif action == REMOVE_LOCK:
                    response = handle_remove_lock(ui_instance, request)
                elif action == STOP_SCAN:
                    response = handle_stop_scan(ui_instance, request)
                elif action == KILL_UI:
                    response = handle_kill_ui(ui_instance, request)
                elif action == DETACH_UI:
                    response = handle_detach_ui(ui_instance, request)
                else:
                    response = {ERROR_KEY: "UNKNOWN_COMMAND"}
                    logger.debug(f"ipc_server: Received unknown command: {data}")

                logger.debug(f"ipc_server: Response generated: {response}")
                response_str = pack_message(response)
                logger.debug(f"ipc_server: Sending response string: {response_str}")
                conn.send(response_str.encode())
            except Exception as conn_e:
                logger.exception("ipc_server: Exception during connection processing")
            finally:
                try:
                    conn.shutdown(socket.SHUT_WR)
                except Exception as e:
                    logger.debug(f"ipc_server: Error during connection shutdown: {e}")
                conn.close()
                logger.debug("ipc_server: Connection closed.")
        except Exception as loop_e:
            logger.exception("ipc_server: Exception in main loop")


def start_ipc_server(ui_instance, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
    from threading import Thread
    thread = Thread(target=ipc_server, args=(ui_instance, socket_path), daemon=True)
    thread.start()

    log_queue = get_log_queue()
    worker_configurer(log_queue)
    logging.getLogger("start_ipc_server()").debug("IPC process logging configured")

    # Wait until we can actually connect
    timeout = 1
    start_time = time.time()
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(socket_path)
            s.close()
            break
        except socket.error:
            if time.time() - start_time > timeout:
                break
            time.sleep(0.1)


