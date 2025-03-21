import os
import sys
import pickle
import logging
import socketserver
import time
from pathlib import Path

project_base = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_base))


def wait_for_new_socket_file(timeout=30, poll_interval=1):
    from utils.helper import get_published_socket_path
    published_file = "/tmp/ipc_socket_file"  # or CURRENT_SOCKET_FILE
    start_time = time.time()
    last_mtime = 0
    if os.path.exists(published_file):
        last_mtime = os.path.getmtime(published_file)
    while time.time() - start_time < timeout:
        if os.path.exists(published_file):
            new_mtime = os.path.getmtime(published_file)
            if new_mtime > last_mtime:
                return get_published_socket_path()
        time.sleep(poll_interval)
    return get_published_socket_path()

def send_logging_server_pid(retry_interval=3, max_retries=60):
    from utils.helper import ipc_ping, get_published_socket_path
    from utils.ipc_client import IPCClient

    # Wait until a new socket file is available
    socket_path = wait_for_new_socket_file(timeout=30, poll_interval=1)

    reg_logger = logging.getLogger("LoggingServerRegistration")
    reg_logger.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)-15s %(levelname)-8s %(message)s')
    stream_handler.setFormatter(formatter)
    reg_logger.addHandler(stream_handler)

    reg_logger.info("Starting registration process with socket: %s", socket_path)

    # Wait until the IPC server is up
    for i in range(max_retries):
        if ipc_ping(socket_path):
            reg_logger.debug(f"IPC server is reachable on attempt {i + 1}.")
            break
        else:
            reg_logger.debug(f"Waiting for IPC server (attempt {i + 1})...")
            time.sleep(retry_interval)
    else:
        reg_logger.error("IPC server did not respond to ping after multiple attempts.")
        return False

    pid = os.getpid()
    message = {"action": "REGISTER_PROCESS", "role": "logging_server", "pid": pid}
    client = IPCClient(socket_path)
    for attempt in range(max_retries):
        response = client.send(message)
        reg_logger.debug(f"Attempt {attempt + 1}, response: {response}")
        if response.get("status") == "REGISTER_PROCESS_OK":
            reg_logger.info(f"Logging server registration succeeded on attempt {attempt + 1}.")
            return True
        time.sleep(retry_interval)
    reg_logger.error("Failed to register logging server after multiple attempts.")
    return False

def start_ipc_registration_thread():
    import threading
    thread = threading.Thread(target=send_logging_server_pid, daemon=True)
    thread.start()
    return thread


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = int.from_bytes(chunk, byteorder='big')
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk += self.connection.recv(slen - len(chunk))
            obj = pickle.loads(chunk)
            record = logging.makeLogRecord(obj)
            logger = logging.getLogger(record.name)
            logger.handle(record)

class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def run_logging_server(host: str = 'localhost', port: int = 9020):
    from config.constants import LOG_DIR, LOG_FILE
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(name)-15s %(levelname)-8s %(message)s',
        handlers=[
            logging.FileHandler(str(LOG_FILE)),
            logging.StreamHandler()
        ]
    )

    logging.info(f"Logging initialized, writing logs to {LOG_FILE}")

    # Start the background thread to register the logging server over IPC.
    start_ipc_registration_thread()

    server = LogRecordSocketReceiver((host, port), LogRecordStreamHandler) # type: ignore
    logging.info(f"Logging server running on {host}:{port}")
    server.serve_forever()


if __name__ == '__main__':
    run_logging_server()

