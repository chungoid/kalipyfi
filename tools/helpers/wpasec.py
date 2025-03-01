import logging
import requests
from pathlib import Path

def upload_to_wpasec(tool, pcap_path: Path, api_key: str) -> bool:
    """
    Uploads the given PCAP file to WPA-sec using the provided API key.
    Returns True if successful, False otherwise.
    :param tool: The tool to upload.
    :param pcap_path: The path to the PCAP file to upload.
    :param api_key: The WPA-sec API key.
    :returns: True if successful, False otherwise.
    """
    url = "https://wpa-sec.stanev.org/?api&upload"
    headers = {"Cookie": f"key={api_key}"}
    try:
        tool.logging.debug(f"Uploading {pcap_path} to WPA-SEC...")
        with pcap_path.open("rb") as f:
            files = {"file": f}
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()
        tool.logging.info(f"Upload successful: {response.text}")
        return True
    except requests.RequestException as e:
        tool.logging.error(f"Error uploading PCAP file: {e}")
        return False


def get_wpasec_api_key(tool) -> str:
    """
    Returns the WPA-sec API key directly from configuration data.

    Expects the YAML configuration to have a structure like:
    user:
      wpasec-key: your_api_key_here
    Raises:
        ValueError: if the API key is not found.
    """
    api_key = tool.config_data.get("user", {}).get("wpasec-key")
    if not api_key:
        raise ValueError("WPA-sec API key not found in configuration.")
    return api_key


def list_pcapng_files(tool, results_dir: Path) -> list:
    """
    List all PCAP files in the given tools results directory.
    :param tool:
    :param results_dir:
    :return: list of PCAP files
    """
    return sorted([f.name for f in results_dir.glob("*.pcapng") if f.is_file()])