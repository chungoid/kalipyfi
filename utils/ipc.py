import socket
import time
import logging
import errno
from threading import Thread

# helpers from common/ipc_protocol.py
from common.ipc_protocol import (
    pack_message, unpack_message, handle_ping, handle_get_state,
    handle_ui_ready, handle_register_process, handle_get_scans,
    handle_send_scan, handle_swap_scan, handle_update_lock, handle_debug_status,
    handle_remove_lock, handle_stop_scan, handle_kill_ui, handle_detach_ui,
)
from utils.helper import publish_socket_path, get_unique_socket_path

# Unpack constants for convenience
from config.constants import IPC_CONSTANTS
PING = IPC_CONSTANTS["actions"]["PING"]
GET_STATE = IPC_CONSTANTS["actions"]["GET_STATE"]
UI_READY = IPC_CONSTANTS["actions"]["UI_READY"]
REGISTER_PROCESS = IPC_CONSTANTS["actions"]["REGISTER_PROCESS"]
GET_SCANS = IPC_CONSTANTS["actions"]["GET_SCANS"]
SEND_SCAN = IPC_CONSTANTS["actions"]["SEND_SCAN"]
SWAP_SCAN = IPC_CONSTANTS["actions"]["SWAP_SCAN"]
STOP_SCAN = IPC_CONSTANTS["actions"]["STOP_SCAN"]
UPDATE_LOCK = IPC_CONSTANTS["actions"]["UPDATE_LOCK"]
REMOVE_LOCK = IPC_CONSTANTS["actions"]["REMOVE_LOCK"]
KILL_UI = IPC_CONSTANTS["actions"]["KILL_UI"]
DETACH_UI = IPC_CONSTANTS["actions"]["DETACH_UI"]
DEBUG_STATUS = IPC_CONSTANTS["actions"]["DEBUG_STATUS"]


class IPCServer:
    def __init__(self, ui_instance, socket_path: str = None):
        self.ui_instance = ui_instance
        if socket_path is None:
            self.socket_path = get_unique_socket_path()
            publish_socket_path(self.socket_path)
        else:
            self.socket_path = socket_path
        self.logger = logging.getLogger("IPCServer")
        self._running = False
        self._server_socket = None

    def start(self):
        """Starts the IPC server in a new daemon thread."""
        self._running = True
        thread = Thread(target=self._serve, daemon=True)
        thread.start()
        self.logger.debug("IPCServer thread started.")
        self._wait_for_connection()

    def _wait_for_connection(self):
        """
        Waits briefly until a connection can be made to ensure that
        the server socket is ready.
        """
        timeout = 1  # seconds
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.connect(self.socket_path)
                test_sock.close()
                self.logger.debug("IPCServer: Connection verified.")
                return
            except socket.error as e:
                time.sleep(0.1)
        self.logger.error(f"IPCServer: Timeout waiting for connection on {self.socket_path}.")

    def _serve(self):
        """Main server loop that accepts and handles connections."""
        try:
            self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_socket.bind(self.socket_path)
            self._server_socket.listen(10)
            self.logger.info(f"IPCServer: Listening on {self.socket_path}...")
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                self.logger.exception(f"IPCServer: Address already in use: {self.socket_path}")
            else:
                self.logger.exception(f"IPCServer: Failed to bind or listen on {self.socket_path}")
            return

        while self._running:
            try:
                self.logger.debug("IPCServer: Waiting for incoming connection...")
                conn, _ = self._server_socket.accept()
                self.logger.debug(f"IPCServer: Connection accepted, fd: {conn.fileno()}")
                self._handle_connection(conn)
            except Exception as loop_e:
                self.logger.exception("IPCServer: Exception in main loop", exc_info=loop_e)

        self._server_socket.close()
        self.logger.info("IPCServer: Server stopped.")

    def _handle_connection(self, conn):
        """Handles an individual connection."""
        try:
            data = conn.recv(1024).decode().strip()
            self.logger.debug(f"IPCServer: Data received: '{data}'")
            if not data:
                self.logger.error("IPCServer: Received empty data, closing connection.")
                return
            request = unpack_message(data)
            self.logger.debug(f"IPCServer: Unpacked request: {request}")
            action = request.get("action", "UNKNOWN")
            self.logger.debug(f"IPCServer: Action determined: {action}")

            # Dispatch to the appropriate handler based on action
            if action == GET_STATE:
                response = handle_get_state(self.ui_instance, request)
            elif action == PING:
                response = handle_ping(self.ui_instance, request)
            elif action == UI_READY:
                response = handle_ui_ready(self.ui_instance, request)
            elif action == REGISTER_PROCESS:
                response = handle_register_process(self.ui_instance, request)
            elif action == DEBUG_STATUS:
                response = handle_debug_status(self.ui_instance, request)
            elif action == GET_SCANS:
                response = handle_get_scans(self.ui_instance, request)
            elif action == SEND_SCAN:
                response = handle_send_scan(self.ui_instance, request)
            elif action == SWAP_SCAN:
                response = handle_swap_scan(self.ui_instance, request)
            elif action == UPDATE_LOCK:
                response = handle_update_lock(self.ui_instance, request)
            elif action == REMOVE_LOCK:
                response = handle_remove_lock(self.ui_instance, request)
            elif action == STOP_SCAN:
                response = handle_stop_scan(self.ui_instance, request)
            elif action == KILL_UI:
                response = handle_kill_ui(self.ui_instance, request)
            elif action == DETACH_UI:
                response = handle_detach_ui(self.ui_instance, request)
            else:
                response = {IPC_CONSTANTS["keys"]["ERROR_KEY"]: "UNKNOWN_COMMAND"}
                self.logger.debug(f"IPCServer: Unknown command received: {data}")

            response_str = pack_message(response)
            self.logger.debug(f"IPCServer: Sending response string: {response_str}")
            conn.send(response_str.encode())
        except Exception as conn_e:
            self.logger.exception("IPCServer: Exception during connection processing", exc_info=conn_e)
        finally:
            try:
                conn.shutdown(socket.SHUT_WR)
            except Exception as e:
                self.logger.debug(f"IPCServer: Error during connection shutdown: {e}")
            conn.close()
            self.logger.debug("IPCServer: Connection closed.")


    def stop(self):
        """Stops the server gracefully."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        self.logger.info("IPCServer: Stopped.")