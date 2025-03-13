from dataclasses import dataclass, field, asdict
import time

@dataclass
class ProcessData:
    pid: int
    role: str  # e.g. "menu", "background", "ipc"
    started_at: float = time.time()

    def to_dict(self):
        return asdict(self)

@dataclass
class SessionData:
    session_name: str
    created_at: float = time.time()

    def to_dict(self):
        return asdict(self)

@dataclass
class InterfaceData:
    interface: str
    lock_status: bool

    def to_dict(self):
        return asdict(self)

@dataclass
class ScanData:
    tool: str # tool that sent the scan
    #scan_profile: str # entire scan profile dict
    window_name: str # tmux name for window the scan resides in
    pane_id: str # tmux pane id
    internal_name: str  # internal name for UI manager to use in menus
    interface: str # scan interface used
    lock_status: bool # interface lock status, currently not in use. would be in /var/lockfile
    cmd_str: str = "" # the scans cmd_dict (in string form) that was run
    preset_description: str = "" # specifically the description key from the scan profile
    timestamp: float = None # when the scan was started

    def to_dict(self):
        return asdict(self)