import errno
import fcntl
import logging
import os


class InterfaceLock:
    def __init__(self, iface, lock_dir="/var/lock"):
        self.iface = iface
        self.lock_file = os.path.join(lock_dir, f"{iface}.lock")
        self.fd = None
        self.logger = logging.getLogger("InterfaceLock")

    def is_locked(self) -> bool:
        """Return True if the interface is currently locked."""
        if os.path.exists(self.lock_file):
            return True
        else:
            return False

    def is_stale(self) -> bool:
        """Return True if the lock file contains a PID that is no longer running."""
        try:
            with open(self.lock_file, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    # os.kill(pid, 0) will raise an OSError if the PID is not running.
                    os.kill(pid, 0)
                    # Process is still running.
                    return False
        except (OSError, ValueError):
            # Either the file can't be read, the PID is invalid, or the process is dead.
            return True
        return True

    def acquire(self) -> bool:
        # If a lock file exists, check if it's stale.
        if os.path.exists(self.lock_file):
            if self.is_stale():
                self.logger.info(f"Stale lock detected for interface {self.iface}. Removing stale lock.")
                try:
                    os.remove(self.lock_file)
                except Exception as e:
                    self.logger.error(f"Error removing stale lock for {self.iface}: {e}")
                    return False
            else:
                self.logger.info(f"Interface {self.iface} is already locked.")
                return False

        try:
            self.fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Clear file contents and write our PID.
            os.ftruncate(self.fd, 0)
            os.write(self.fd, str(os.getpid()).encode())
            return True
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                self.logger.error(f"Interface {self.iface} is already locked (EAGAIN).")
            else:
                self.logger.error(f"Error acquiring lock for {self.iface}: {e}")
            return False

    def release(self) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
                os.remove(self.lock_file)
                self.fd = None
                self.logger.info(f"Stale lock removed for {self.iface}")
            except Exception as e:
                self.logger.error(f"Error releasing lock for {self.iface}: {e}")