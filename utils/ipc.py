# utils/ipc.py
import curses
import errno
import os
import sys
import time
import logging
import socket

# local
from common.ipc_protocol import (
    pack_message, unpack_message, handle_get_state, handle_get_scans,
    handle_send_scan, handle_swap_scan, handle_update_lock,
    handle_remove_lock, handle_stop_scan, handle_kill_ui, handle_detach_ui, handle_debug_status, handle_ping
)
from common.logging_setup import worker_configurer, get_log_queue
from common.process_manager import process_manager
from config.constants import IPC_CONSTANTS, RETRY_DELAY
from utils.helper import publish_socket_path, get_unique_socket_path, get_published_socket_path

# Unpack constants.
ACTION_KEY       = IPC_CONSTANTS["keys"]["ACTION_KEY"]
ERROR_KEY        = IPC_CONSTANTS["keys"]["ERROR_KEY"]
TOOL_KEY         = IPC_CONSTANTS["keys"]["TOOL_KEY"]
SCAN_PROFILE_KEY = IPC_CONSTANTS["keys"]["SCAN_PROFILE_KEY"]
COMMAND_KEY      = IPC_CONSTANTS["keys"]["COMMAND_KEY"]
TIMESTAMP_KEY    = IPC_CONSTANTS["keys"]["TIMESTAMP_KEY"]
STATUS_KEY       = IPC_CONSTANTS["keys"]["STATUS_KEY"]
RESULT_KEY       = IPC_CONSTANTS["keys"]["RESULT_KEY"]

GET_STATE     = IPC_CONSTANTS["actions"]["GET_STATE"]
PING          = IPC_CONSTANTS["actions"]["PING"]
GET_SCANS     = IPC_CONSTANTS["actions"]["GET_SCANS"]
SEND_SCAN     = IPC_CONSTANTS["actions"]["SEND_SCAN"]
SWAP_SCAN     = IPC_CONSTANTS["actions"]["SWAP_SCAN"]
STOP_SCAN     = IPC_CONSTANTS["actions"]["STOP_SCAN"]
UPDATE_LOCK   = IPC_CONSTANTS["actions"]["UPDATE_LOCK"]
REMOVE_LOCK   = IPC_CONSTANTS["actions"]["REMOVE_LOCK"]
KILL_UI       = IPC_CONSTANTS["actions"]["KILL_UI"]
DETACH_UI     = IPC_CONSTANTS["actions"]["DETACH_UI"]
DEBUG_STATUS  = IPC_CONSTANTS["actions"]["DEBUG_STATUS"]

def send_ipc_command(message: dict, socket_path: str = None) -> dict:
    logger = logging.getLogger("ipc:send_ipc_command")
    if socket_path is None:
        socket_path = get_published_socket_path()
    logger.debug(f"send_ipc_command: Using socket_path: {socket_path} for message: {message}")
    attempt = 0
    while attempt < 3:
        try:
            logger.debug(f"send_ipc_command: Attempt {attempt+1}: Creating client socket.")
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

def ipc_server(ui_instance, socket_path: str) -> None:
    logger = logging.getLogger("ipc:ipc_server")
    logger.debug(f"ipc_server: Using provided socket path: {socket_path}")

    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        logger.debug(f"ipc_server: Created server socket with fd: {server.fileno()}")
        server.bind(socket_path)
        logger.debug(f"ipc_server: Bound to socket path: {socket_path}")
        server.listen(10)
        logger.info(f"ipc_server: Listening for connections on {socket_path}...")
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            logger.exception(f"ipc_server: Address already in use: {socket_path}")
        else:
            logger.exception(f"ipc_server: Failed to bind or listen on {socket_path}")
        return

    while True:
        try:
            logger.debug("ipc_server: Waiting for incoming connection...")
            conn, _ = server.accept()
            logger.debug(f"ipc_server: Connection accepted, fd: {conn.fileno()}")
            try:
                data = conn.recv(1024).decode().strip()
                logger.debug(f"ipc_server: Data received: '{data}'")
                if not data:
                    logger.error("ipc_server: Received empty data, closing connection.")
                    conn.close()
                    continue
                request = unpack_message(data)
                logger.debug(f"ipc_server: Unpacked request: {request}")
                action = request.get("action", "UNKNOWN")
                logger.debug(f"ipc_server: Action determined: {action}")
                if action == GET_STATE:
                    response = handle_get_state(ui_instance, request)
                elif action == PING:
                    response = handle_ping(ui_instance, request)
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


def reconnect_ipc_socket():
    """
    Attempts to reconnect by re-reading the published socket path and trying to connect.
    Returns the new socket path if the connection succeeds; otherwise, returns None.
    """
    new_socket = get_published_socket_path()
    logging.debug(f"reconnect_ipc_socket: Read published socket path: {new_socket}")
    import socket, time
    timeout = 2  # seconds
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(new_socket)
            s.close()
            logging.debug("reconnect_ipc_socket: Successfully connected to IPC socket.")
            return new_socket
        except socket.error as e:
            logging.debug(f"reconnect_ipc_socket: Connection attempt failed: {e}")
            time.sleep(0.1)
    logging.error("reconnect_ipc_socket: Could not connect to IPC socket within timeout.")
    return None


def start_ipc_server(ui_instance, socket_path: str = None) -> None:
    from threading import Thread
    import socket
    import time
    logger = logging.getLogger("start_ipc_server()")

    if socket_path is None:
        socket_path = get_unique_socket_path()
        publish_socket_path(socket_path)
        logger.debug(f"start_ipc_server: Unique socket generated and published: {socket_path}")
    else:
        logger.debug(f"start_ipc_server: Using provided socket path: {socket_path}")

    thread = Thread(target=ipc_server, args=(ui_instance, socket_path), daemon=True)
    thread.start()
    logger.debug("start_ipc_server: IPC server thread started.")

    log_queue = get_log_queue()
    worker_configurer(log_queue)
    logger.debug("start_ipc_server: IPC process logging configured.")

    timeout = 1  # seconds
    start_time_val = time.time()
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(socket_path)
            s.close()
            logger.debug("start_ipc_server: Successfully connected to IPC socket.")
            break
        except socket.error as e:
            if time.time() - start_time_val > timeout:
                logger.error(f"start_ipc_server: Timeout waiting for socket connection on {socket_path}")
                break
            logger.debug(f"start_ipc_server: Socket connection attempt failed: {e}")
            time.sleep(0.1)
