from pathlib import Path
from typing import List, Optional

def run_autobpf(tool,
                scan_interface: str,
                filter_path: Path,
                interfaces: List[str],
                extra_macs: Optional[List[str]] = None) -> bool:
    """
    Generate a BPF filter that excludes packets from all interfaces except the scanning interface.
    Also includes MAC addresses from non-scanning interfaces and any additional MAC addresses.

    Uses helper methods from the `tool` instance:
      - tool.get_all_iface_macs(iface)
      - tool.check_client_macs(interfaces)
      - tool.run_shell_command(cmd)
      - tool.logger for logging

    Returns:
        bool: True if the filter was generated and applied successfully; otherwise, False.
    """
    # Exclude the scanning interface.
    other_interfaces = [iface for iface in interfaces if iface != scan_interface]

    macs: List[str] = []
    for iface in other_interfaces:
        mac = tool.get_iface_macs(iface)
        if mac:
            macs.append(mac)
        else:
            tool.logger.warning(f"Warning: Could not retrieve MAC address for {iface}")

    # Include client MACs.
    client_macs = tool.get_associated_macs(other_interfaces)
    if client_macs:
        tool.logger.debug(f"Found client MACs: {client_macs}")
        macs.extend(client_macs)

    # Include any additional MAC addresses.
    if extra_macs:
        macs.extend(extra_macs)

    if not macs:
        tool.logger.warning(
            "No MAC addresses found; aborting BPF filter generation to avoid interfering with own connections.")
        return False

    # Build filter expression using grouped OR inside a NOT.
    clauses = [f"wlan addr2 {mac}" for mac in macs]
    filter_expr = "not (" + " or ".join(clauses) + ")"
    tool.logger.debug(f"Generated BPF filter expression: {filter_expr}")

    # Backup existing filter file if it exists.
    if filter_path.exists():
        backup_file = filter_path.with_suffix(".bak")
        try:
            filter_path.rename(backup_file)
            tool.logger.debug(f"BPF filter already exists, backed up to {backup_file}")
        except Exception as e:
            tool.logger.error(f"Error backing up existing filter file: {e}")
            return False

    # Pass the filter expression directly to hcxdumptool.
    try:
        cmd = f'hcxdumptool --bpfc="{filter_expr}" > {filter_path}'
        if tool.run_shell(cmd) is None:
            tool.logger.warning("hcxdumptool failed to compile the BPF filter")
            return False
    except Exception as e:
        tool.logger.error(f"Error generating BPF filter file: {e}")
        return False

    tool.logger.debug(f"BPF filter generated: {filter_path.resolve()}")
    return True
