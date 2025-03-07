import subprocess
import threading


def start_webserver(directory, port=8000):
    """
    Starts a Python HTTP server in the specified directory on the given port.
    This is run in a separate thread so that it doesn't block the main program.
    """
    def server():
        subprocess.run(["python3", "-m", "http.server", str(port)], cwd=directory)
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    print(f"Serving {directory} on port {port}...")