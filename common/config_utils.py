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
        logger.debug(f"Loaded config data: {loaded_data}")
        return loaded_data
    except Exception as e:
        logger.critical(f"Failed to load config: {config_path}: {e}")
        return {}