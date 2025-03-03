import logging
import os
import signal
import psutil
from common.models import ProcessData

class ProcessManager:
    def __init__(self):
        self.processes = {}  # Keyed by PID

    def register_process(self, role: str, pid: int):
        proc_data = ProcessData(pid=pid, role=role)
        self.processes[pid] = proc_data
        logging.debug(f"Registered process: {proc_data}")

    def shutdown_all(self):
        for pid, proc_data in list(self.processes.items()):
            try:
                logging.debug(f"Terminating process {pid} ({proc_data.role})")
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                logging.error(f"Error killing process {pid}: {e}")

    def debug_status(self):
        """Logs the status of each registered process."""
        for pid, proc_data in list(self.processes.items()):
            try:
                p = psutil.Process(pid)
                status = p.status()
                pgid = os.getpgid(pid)
                logging.debug(f"Process {pid} ({proc_data.role}): Status = {status}, PGID = {pgid}")
            except psutil.NoSuchProcess:
                logging.debug(f"Process {pid} ({proc_data.role}) is no longer running.")
            except Exception as e:
                logging.error(f"Error checking process {pid}: {e}")

    def cleanup(self):
        """Removes processes from the registry that are no longer running."""
        removed = []
        for pid in list(self.processes.keys()):
            if not psutil.pid_exists(pid):
                removed.append(pid)
                del self.processes[pid]
        if removed:
            logging.debug(f"Cleaned up non-existing processes: {removed}")

    def get_status_report(self) -> str:
        """Returns a formatted string report of all registered processes."""
        report_lines = []
        for pid, proc_data in self.processes.items():
            try:
                p = psutil.Process(pid)
                status = p.status()
                pgid = os.getpgid(pid)
                report_lines.append(f"PID {pid} ({proc_data.role}): Status = {status}, PGID = {pgid}")
            except psutil.NoSuchProcess:
                report_lines.append(f"PID {pid} ({proc_data.role}): Not running")
        return "\n".join(report_lines)

# Instantiate a single global manager (or import as needed)
process_manager = ProcessManager()