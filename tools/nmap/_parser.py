import json
from pathlib import Path


def parse_network_results(gnmap_path: Path) -> (dict, str):
    """
    Parses the provided .gnmap file and extracts network-level data and host entries.
    Returns a tuple:
      - A dictionary with keys: router_ip, router_hostname.
      - A JSON blob (string) representing the list of hosts (each a dict with 'ip' and 'hostname').
    """
    network_data = {}
    hosts = []
    with open(gnmap_path, "r") as f:
        lines = f.readlines()

    router_ip = None
    router_hostname = None
    for line in lines:
        if line.startswith("Host:"):
            # Example: "Host: 192.168.1.1 (Router.lan)	Status: Up"
            parts = line.split()
            if len(parts) >= 2:
                host_ip = parts[1]
                hostname = ""
                if len(parts) >= 3 and parts[2].startswith("(") and parts[2].endswith(")"):
                    hostname = parts[2][1:-1]
                hosts.append({"ip": host_ip, "hostname": hostname})
                if router_ip is None:
                    router_ip = host_ip
                    router_hostname = hostname

    network_data["router_ip"] = router_ip
    network_data["router_hostname"] = router_hostname
    hosts_json = json.dumps(hosts)
    return network_data, hosts_json

