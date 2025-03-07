import logging
import os
import signal
import psutil
from common.models import ProcessData

############################################################################
##### import process_manager = ProcessManager() as your global manager #####
############################################################################

class ProcessManager:
    def __init__(self):
        self.processes = {}  # Keyed by PID

    def register_process(self, role: str, pid: int):
        proc_data = ProcessData(pid=pid, role=role)
        self.processes[pid] = proc_data
        logging.debug(f"Registered process: {proc_data}")

    @staticmethod
    def kill_process_tree(pid, sig=signal.SIGTERM, include_parent=True, timeout=10):
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        children = parent.children(recursive=True)
        for child in children:
            child.send_signal(sig)
        if include_parent:
            parent.send_signal(sig)
        gone, alive = psutil.wait_procs([parent] + children, timeout=timeout)
        if alive:
            for p in alive:
                p.kill()  # force kill if still alive

    def shutdown_all(self):
        logging.info("Initiating shutdown_all in ProcessManager.")
        logging.debug("Status before shutdown:\n" + self.get_status_report())

        for pid, proc_data in list(self.processes.items()):
            try:
                # Get the process group for this process
                pgid = os.getpgid(pid)
                logging.debug(f"Killing process group {pgid} for PID {pid} ({proc_data.role})")
                os.killpg(pgid, signal.SIGTERM)
            except Exception as e:
                logging.error(f"Error killing process group for PID {pid} ({proc_data.role}): {e}")

        # Optionally, call cleanup to remove dead entries
        self.cleanup()
        logging.info("Shutdown_all complete.")

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

# single global manager, import as needed
process_manager = ProcessManager()