import logging
import yaml
from pathlib import Path


logger = logging.getLogger("tools/config_helper")

def update_yaml_value(config_path: Path, key_path: list, new_value) -> None:
    """
    Updates the YAML configuration file at the specified config_path by setting the
    nested key defined by key_path to new_value.

    Parameters
    ----------
    config_path : Path
        The path to the YAML configuration file.
    key_path : list
        A list of keys representing the nested path to the desired value.
        For example, ["wpa-sec", "api_key"].
    new_value :
        The new value to set at the specified key path.

    Returns
    -------
    None

    Raises
    ------
    Exception
        If there is an error reading from or writing to the configuration file.
    """
    try:
        with config_path.open("r") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load configuration file {config_path}: {e}")
        raise

    sub_config = config
    for key in key_path[:-1]:
        if key not in sub_config or not isinstance(sub_config[key], dict):
            sub_config[key] = {}
        sub_config = sub_config[key]

    sub_config[key_path[-1]] = new_value

    try:
        with config_path.open("w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Updated {'.'.join(key_path)} to {new_value} in {config_path}")
    except Exception as e:
        logger.error(f"Failed to write updated configuration to {config_path}: {e}")
        raise
