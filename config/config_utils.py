#!/usr/bin/env python3
import os
import sys
import yaml
import time
import socket
import logging
from pathlib import Path
from typing import Dict
project_base = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_base))


def wait_for_logging_server(host='localhost', port=9020, timeout=30):
    """
    Helper to check for logging server on startup.

    :param host:
    :param port:
    :param timeout:
    :return:
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = s.connect_ex((host, port))
            if result == 0:
                s.close()
                return True
        finally:
            s.close()
        time.sleep(0.5)
    return False

def register_processes_via_ipc(socket_path, tmuxp_pid):
    """
    Register processes from kalipyfi.py main function with IPC server.

    :param socket_path:
    :param tmuxp_pid:
    :return:
    """

    from utils.ipc_client import IPCClient
    client = IPCClient(socket_path)

    # register the main process
    main_registration = {
        "action": "REGISTER_PROCESS",
        "role": "main",
        "pid": os.getpid()
    }
    main_response = client.send(main_registration)
    logging.info(f"Main process registration response: {main_response}")

    # register the tmuxp process
    tmuxp_registration = {
        "action": "REGISTER_PROCESS",
        "role": "tmuxp",
        "pid": tmuxp_pid
    }
    tmuxp_response = client.send(tmuxp_registration)
    logging.info(f"tmuxp process registration response: {tmuxp_response}")

def load_yaml_config(config_path: Path, logger: logging.Logger = None) -> Dict:
    """
    Loads a YAML configuration file and returns the contents as a dictionary.
    If the file doesn't exist or fails to load, logs an error and returns an empty dict.

    :param config_path: The path to the YAML configuration file.
    :param logger: An optional logger to use for logging messages.
    :return: The configuration as a dict, or {} on failure.
    """
    if logger is None:
        logger = logging.getLogger("config_utils:load_yaml_config")
    if not config_path.exists():
        logger.critical(f"Config file NOT FOUND at {config_path}")
        return {}
    try:
        with open(config_path, "r") as f:
            loaded_data = yaml.safe_load(f) or {}
        logger.info(f"Successfully loaded config: {config_path}")
        return loaded_data
    except Exception as e:
        logger.critical(f"Failed to load config: {config_path}: {e}")
        return {}

def test_config_paths() -> str:
    """
    Assembles the default directory and file paths defined in config/constants.py
    into a string for debugging purposes.

    :return: A formatted string containing all configuration paths.
    """
    from config.constants import (
        BASE_DIR, CONFIG_DIR, LOG_DIR, UI_DIR, TOOLS_DIR,
        CURSES_MAIN_MENU, LOG_FILE, MAIN_UI_YAML_PATH, DEFAULT_ASCII
    )

    output_lines = [
        "Default Directories:",
        f"  BASE_DIR: {BASE_DIR}",
        f"  CONFIG_DIR: {CONFIG_DIR}",
        f"  LOG_DIR: {LOG_DIR}",
        f"  UI_DIR: {UI_DIR}",
        f"  TOOLS_DIR: {TOOLS_DIR}",
        "",
        "Default Files:",
        f"  CURSES_MAIN_MENU: {CURSES_MAIN_MENU}",
        f"  LOG_FILE: {LOG_FILE}",
        f"  MAIN_UI_YAML_PATH: {MAIN_UI_YAML_PATH}",
        f"  DEFAULT_ASCII: {DEFAULT_ASCII}"
    ]
    return "\n".join(output_lines)


def configure_socket_logging(host: str = 'localhost', port: int = 9020) -> None:
    """
    Configures logging to send log records to a logging server via a SocketHandler.

    :param host: The logging server host.
    :param port: The logging server port.
    :return: None
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    socket_handler = logging.handlers.SocketHandler(host, port)
    logger.addHandler(socket_handler)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
