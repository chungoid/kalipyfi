#!/usr/bin/env python3
import logging
import yaml
from pathlib import Path
from typing import Dict

def load_yaml_config(config_path: Path, logger: logging.Logger = None) -> Dict:
    """
    Loads a YAML configuration file and returns the contents as a dictionary.
    If the file doesn't exist or fails to load, logs an error and returns an empty dict.

    :param config_path: The path to the YAML configuration file.
    :param logger: An optional logger to use for logging messages.
    :return: The configuration as a dict, or {} on failure.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
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
        CURSES_MAIN_MENU, LOG_FILE, MAIN_UI_YAML_PATH, BG_YAML_PATH, DEFAULT_ASCII
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
        f"  BG_YAML_PATH: {BG_YAML_PATH}",
        f"  DEFAULT_ASCII: {DEFAULT_ASCII}"
    ]
    return "\n".join(output_lines)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
