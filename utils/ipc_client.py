import os
import socket
import threading
import time
import logging
from common.ipc_protocol import pack_message, unpack_message
from utils.helper import get_published_socket_path

class IPCClient:
    def __init__(self, socket_path: str = None):
        # If no socket path is provided, read the published socket path.
        if socket_path is None:
            socket_path = get_published_socket_path()
        self.socket_path = socket_path
        self.logger = logging.getLogger("IPCClient")

    def send(self, message: dict) -> dict:
        """
        Sends the given message (as a dict) to the IPC server and returns the response.
        Retries a few times on connection errors.
        """
        attempt = 0
        while attempt < 3:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:  # type: socket
                    client.connect(self.socket_path)
                    message_str = pack_message(message)
                    self.logger.debug(f"Sending message: {message_str}")
                    client.send(message_str.encode())

                    # read til no more data
                    response_bytes = b""
                    while True:
                        part = client.recv(4096)
                        if not part:
                            break
                        response_bytes += part

                    response_str = response_bytes.decode().strip()
                    self.logger.debug(f"Received response: {response_str}")
                    return unpack_message(response_str)
            except (ConnectionResetError, ConnectionRefusedError) as e:
                attempt += 1
                self.logger.warning(f"Connection error on attempt {attempt}: {e}")
                time.sleep(0.1)
            except Exception as e:
                self.logger.exception("Exception occurred during IPCClient.send", exc_info=e)
                return {"error": str(e)}
        return {"error": f"Failed after {attempt} attempts"}
