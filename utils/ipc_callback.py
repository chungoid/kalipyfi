import logging
import os
import socket
import threading

# local
from common.ipc_protocol import unpack_message


class CallbackListener:
    def __init__(self, callback_socket_path: str):
        self.callback_socket_path = callback_socket_path
        self.logger = logging.getLogger("CallbackListener")
        self._running = True
        self.callbacks = {}  # keys to callback function mapping
        try:
            os.unlink(self.callback_socket_path)
        except OSError:
            pass
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def register_callback(self, key: str, callback_function):
        """Register a callback function for a given key (e.g., tool name or scan ID)."""
        self.callbacks[key] = callback_function

    def unregister_callback(self, key: str):
        if key in self.callbacks:
            del self.callbacks[key]

    def _listen(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_sock:
            server_sock.bind(self.callback_socket_path)
            server_sock.listen(5)
            self.logger.info(f"Callback listener started on {self.callback_socket_path}")
            while self._running:
                try:
                    conn, _ = server_sock.accept()
                    with conn:
                        data = conn.recv(4096).decode().strip()
                        if data:
                            message = unpack_message(data)
                            self.logger.debug(f"Callback received: {message}")
                            # key from message to dispatch callback to
                            key = message.get("tool") or message.get("scan_id")
                            if key and key in self.callbacks:
                                self.callbacks[key](message)
                            else:
                                self.logger.warning("No callback registered for key: %s", key)
                except Exception as e:
                    self.logger.error(f"Error in callback listener: {e}")

    def stop(self):
        self._running = False

# shared callback socket path
SHARED_CALLBACK_SOCKET = "/tmp/ipc_callback_shared.sock"
# shared callback instance
shared_callback_listener = CallbackListener(SHARED_CALLBACK_SOCKET)

def get_shared_callback_socket():
    return SHARED_CALLBACK_SOCKET
