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
        self.logger.debug("Initializing callback listener")
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
        self.logger.debug("Registered callback function for key {}".format(key))

    def unregister_callback(self, key: str):
        if key in self.callbacks:
            del self.callbacks[key]

    def _listen(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_sock:
            try:
                server_sock.bind(self.callback_socket_path)
            except Exception as e:
                self.logger.error("Failed to bind callback socket: %s", e)
                return
            server_sock.listen(5)
            self.logger.info(f"Callback listener started on {self.callback_socket_path}")
            while self._running:
                try:
                    self.logger.debug("Waiting for a new connection on callback socket...")
                    conn, addr = server_sock.accept()
                    self.logger.debug("Accepted connection from %s", addr)
                    with conn:
                        data = conn.recv(4096).decode().strip()
                        self.logger.debug("Raw data received: '%s'", data)
                        if data:
                            message = unpack_message(data)
                            self.logger.debug("Unpacked callback message: %s", message)
                            # key from message to dispatch callback to
                            key = message.get("tool") or message.get("scan_id")
                            if key:
                                self.logger.debug("Dispatching callback for key: %s", key)
                            else:
                                self.logger.warning("Received message without 'tool' or 'scan_id': %s", message)
                            if key and key in self.callbacks:
                                try:
                                    self.callbacks[key](message)
                                    self.logger.debug("Callback for key %s executed successfully", key)
                                except Exception as callback_e:
                                    self.logger.error("Error in callback for key %s: %s", key, callback_e)
                            else:
                                self.logger.warning("No callback registered for key: %s", key)
                        else:
                            self.logger.warning("Received empty data on callback socket")
                except Exception as e:
                    self.logger.error("Error in callback listener loop: %s", e)

    def stop(self):
        self._running = False

# shared callback socket path
SHARED_CALLBACK_SOCKET = "/tmp/ipc_callback_shared.sock"
# shared callback instance
shared_callback_listener = CallbackListener(SHARED_CALLBACK_SOCKET)

def get_shared_callback_socket():
    return SHARED_CALLBACK_SOCKET
