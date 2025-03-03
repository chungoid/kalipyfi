import logging
import yaml
from pathlib import Path


logger = logging.getLogger("tools/config_helper")

def set_config_key(config_path: Path, key_path: list, new_value) -> None:
    """
    Update the configuration YAML file at config_path by setting the nested key specified
    in key_path (a list of keys) to new_value.

    Args:
        config_path (Path): Path to the YAML config file.
        key_path (list): List of keys representing the nested path (e.g. ["wpa-sec", "api_key"]).
        new_value: The new value to set at that key.
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load configuration file {config_path}: {e}")
        raise

    # Navigate to the nested key
    sub_config = config
    for key in key_path[:-1]:
        if key not in sub_config or not isinstance(sub_config[key], dict):
            sub_config[key] = {}
        sub_config = sub_config[key]

    # Update the key.
    sub_config[key_path[-1]] = new_value

    try:
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Updated {'.'.join(key_path)} to {new_value} in {config_path}")
    except Exception as e:
        logger.error(f"Failed to write updated configuration to {config_path}: {e}")
        raise
