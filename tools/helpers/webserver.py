import subprocess
import threading


def start_webserver(directory, port=8000):
    """
    Starts a Python HTTP server in the specified directory on the given port,
    suppressing stdout and stderr.
    """
    def server():
        subprocess.run(
            ["python3", "-m", "http.server", str(port)],
            cwd=directory,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
