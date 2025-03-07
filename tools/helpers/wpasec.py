import logging
import os

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
    url = "https://wpa-sec.stanev.org/?api&upload=1"
    headers = {"Cookie": f"key={api_key}"}
    try:
        tool.logger.debug(f"Uploading {pcap_path} to WPA-SEC...")
        with pcap_path.open("rb") as f:
            files = {"file": f}
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()
        tool.logger.info(f"Upload successful: {response.text}")
        return True
    except requests.RequestException as e:
        tool.logger.error(f"Error uploading PCAP file: {e}")
        return False


def download_from_wpasec(tool, api_key: str, results_dir: str) -> str | None:
    """
    Downloads data from WPA-sec using the provided API key and saves it as 'founds.txt'
    in the specified results' directory.

    :param tool: The tool to download.
    :param api_key: The WPA-sec API key.
    :param results_dir: The results' directory.
    returns: The path to the downloaded PCAP file.
    """
    url = "https://wpa-sec.stanev.org/?api&dl=1"
    headers = {"Cookie": f"key={api_key}"}
    tool.logger.debug("Downloading founds from WPA-sec...")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an exception for 4xx/5xx responses.

        # Ensure the results directory exists.
        os.makedirs(results_dir, exist_ok=True)
        founds_path = os.path.join(results_dir, "founds.txt")

        with open(founds_path, "w") as f:
            f.write(response.text)

        tool.logger.info(f"Downloaded founds and saved to {founds_path}")
        return founds_path
    except Exception as e:
        tool.logger.exception(f"Error downloading from WPA-sec: {e}")
        return None

def get_wpasec_api_key(tool) -> str:
    """
    Returns the WPA-sec API key directly from configuration data.

    Expects the YAML configuration to have a structure like:
    user:
      wpasec-key: your_api_key_here
    Raises:
        ValueError: if the API key is not found.
    """
    api_key = tool.config_data.get("wpa-sec", {}).get("api_key")
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