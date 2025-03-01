import sys
from dataclasses import dataclass, field, asdict
import time

@dataclass
class InterfaceData:
    interface: str
    lock_status: bool

    def to_dict(self):
        return asdict(self)

@dataclass
class ScanData:
    tool: str
    scan_profile: str
    window_name: str
    pane_id: str
    internal_name: str  # Added internal name for UI display purposes.
    interface: str
    lock_status: bool
    cmd_str: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return asdict(self)