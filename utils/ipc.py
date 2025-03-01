# ipc.py
import socket
import os
import json
import time
from common.ipc_protocol import (
    pack_message,
    unpack_message,
    GET_STATE, GET_SCANS, SEND_SCAN, SWAP_SCAN,
    STOP_SCAN, UPDATE_LOCK, REMOVE_LOCK, KILL_UI, DETACH_UI,
    ERROR_KEY, handle_get_state, handle_send_scan
)
from config.constants import DEFAULT_SOCKET_PATH, RETRY_DELAY  # example constants


def send_ipc_command(message: dict, socket_path: str = DEFAULT_SOCKET_PATH) -> dict:
    """
    Sends a structured message (as dict) to the IPC server and returns the response as a dict.
    """
    attempt = 0
    while attempt < 50:
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(socket_path)
            message_str = pack_message(message)
            client.send(message_str.encode())
            response_str = client.recv(1024).decode().strip()
            client.close()
            return unpack_message(response_str)
        except (ConnectionResetError, ConnectionRefusedError) as e:
            attempt += 1
            time.sleep(RETRY_DELAY)
        except Exception as e:
            return {ERROR_KEY: str(e)}
    return {ERROR_KEY: f"Failed after {attempt} attempts"}


def ipc_server(ui_instance, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
    """
    Starts the IPC server, listens for connections, and processes messages.
    """
    if os.path.exists(socket_path):
        os.remove(socket_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)

    while True:
        try:
            conn, _ = server.accept()
            data = conn.recv(1024).decode().strip()
            request = unpack_message(data)
            action = request.get("action", "UNKNOWN")
            # Dispatch to the appropriate handler based on the action.
            if action == GET_STATE:
                response = handle_get_state(ui_instance, request)
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
            response_str = pack_message(response)
            conn.send(response_str.encode())
            conn.shutdown(socket.SHUT_WR)
            conn.close()
        except Exception as e:
            # Log error here if you have a common logger
            print(f"IPC server error: {e}")


def start_ipc_server(ui_instance, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
    """
    Starts the IPC server in a separate daemon thread.
    """
    import threading
    thread = threading.Thread(target=ipc_server, args=(ui_instance, socket_path), daemon=True)
    thread.start()
