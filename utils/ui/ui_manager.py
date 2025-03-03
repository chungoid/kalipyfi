# utils/ui/ui_manager.py
import os
import signal
import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
import libtmux
import jinja2

from common.models import ScanData, InterfaceData, SessionData
from config.constants import TMUXP_DIR


class UIManager:
    def __init__(self, session_name: str = "kalipyfi") -> None:
        """
        Initializes the UIManager by connecting to a tmuxp server and ensuring
        a tmuxp session with the given session_name exists.

        :param session_name: The name of the tmuxp session to use/create.
        """
        self.logger = logging.getLogger("UIManager")
        self.server = libtmux.Server()
        self.session = self.get_or_create_session(session_name)
        self.session_data = SessionData(session_name=self.session.get("session_name"))
        # Active scans: map pane_id -> ScanData
        self.active_scans: Dict[str, ScanData] = {}
        # Tool Interfaces: map interface name -> InterfaceData
        self.interfaces: Dict[str, InterfaceData] = {}
        # Paths to TMUXP configs
        self.session_name = session_name
        self.tmuxp_dir = TMUXP_DIR



    def _register_scan(self, window_name: str, pane_id: str, internal_name: str, tool_name: str,
                         scan_profile: str, command: str, interface: str,
                         lock_status: bool) -> None:
        """
        Creates a ScanData object and updates the active_scans registry.

        :param window_name: The name of the window containing the scan.
        :param pane_id: The unique identifier of the pane.
        :param internal_name: The canonical internal name generated for the pane.
        :param tool_name: The name of the tool launching the scan.
        :param scan_profile: The scan profile used.
        :param command: The executed command string.
        :param interface: The interface used for scanning.
        :param lock_status: The lock status of the interface.
        :return: None
        """
        scan_data = ScanData(
            tool=tool_name,
            scan_profile=scan_profile,
            window_name=window_name,
            pane_id=pane_id,
            internal_name=internal_name,
            interface=interface,
            lock_status=lock_status,
            cmd_str=command
        )
        self.active_scans[pane_id] = scan_data
        self.logger.debug(f"Registered scan: {scan_data}")


    def _launch_command_in_pane(self, pane: libtmux.Pane, cmd_dict: dict) -> str:
        """
        Converts the command dictionary into a command string and sends it to the pane.

        :param pane: The libtmux.Pane where the command will be launched.
        :param cmd_dict: Dictionary with keys 'executable' (str) and 'arguments' (List[str]).
        :return: The command string that was launched.
        """
        command = self.convert_cmd_dict_to_string(cmd_dict)
        pane.send_keys(command, enter=True)
        self.logger.info(f"Launched scan command: {command} in pane {pane.get('pane_id')}")
        return command


    def _find_pane_by_id(self, pane_id: str) -> Optional[libtmux.Pane]:
        """
        Locates a pane by its pane_id within the current session.

        :param pane_id: The unique identifier of the pane.
        :return: The matching libtmux.Pane if found, otherwise None.
        """
        for window in self.session.windows:
            for pane in window.panes:
                if pane.get("pane_id") == pane_id:
                    return pane
        return None


    def get_session(self, session_name: str) -> Optional[libtmux.Session]:
        """
        Retrieves an existing tmuxp session by name.

        :param session_name: The name of the tmuxp session.
        :return: The libtmux.Session if found, otherwise None.
        """
        return self.server.find_where({"session_name": session_name})


    def create_session(self, session_name: str) -> libtmux.Session:
        """
        Creates a new tmuxp session with the given name.

        :param session_name: The desired session name.
        :return: The newly created libtmux.Session.
        """
        self.logger.info(f"Creating new session: {session_name}")
        return self.server.new_session(session_name=session_name, attach=False)


    def get_or_create_session(self, session_name: str) -> libtmux.Session:
        session = self.get_session(session_name)
        self.logger.debug(f"get_or_create_session Found session: {session}")
        if session is None:
            session = self.create_session(session_name)
            self.logger.info(f"get_or_create_session found no session so creating session: {session}")
        self.debug_list_windows()
        return session

    def get_tool_window(self, tool_name: str) -> Optional[libtmux.Window]:
        expected_window_name = f"bg_{tool_name}"
        self.logger.debug(
            f"Searching for window with expected name: '{expected_window_name}' in session '{self.session_name}'")
        # List all windows for debugging.
        all_window_names = [window.get("window_name") for window in self.session.windows]
        self.logger.debug(f"Current windows in session '{self.session_name}': {all_window_names}")
        window = self.session.find_where({"window_name": expected_window_name})
        if window:
            self.logger.debug(f"Found window '{expected_window_name}'.")
        else:
            self.logger.debug(f"Window '{expected_window_name}' not found.")
        return window

    def create_tool_window(self, tool_name: str) -> libtmux.Window:
        """
        Creates a new background window for a given tool using direct libtmux commands.
        This function is a fallback method and is generally not recommended for primary use.
        For the preferred behavior—creating a window based on a YAML-defined layout—use
        get_or_create_tool_window(), which invokes load_background_window().

        :param tool_name: The tool's name.
        :return: The newly created libtmux.Window.
        """
        window_name = f"bg_{tool_name}"
        self.logger.info(f"Creating new window for tool: {tool_name}")
        return self.session.new_window(window_name=window_name, attach=False)

    def get_or_create_tool_window(self, tool_name: str) -> libtmux.Window:
        """
        Retrieves the background window for the given tool if it exists;
        otherwise, creates a new background window for the tool.
        """
        window = self.get_tool_window(tool_name)
        if window is None:
            self.logger.info(f"No background window for '{tool_name}' found. Creating one.")
            window = self.create_background_window(tool_name)
        else:
            self.logger.info(f"Background window for '{tool_name}' already exists.")
        return window

    def create_pane(self, window: libtmux.Window) -> libtmux.Pane:
        """
        Creates a new pane in the given window.

        :param window: The libtmux.Window in which to create a new pane.
        :return: The newly created libtmux.Pane.
        """
        return window.split_window(attach=False)

    def rename_pane(self, pane: libtmux.Pane, tool_name: str, scan_profile: str) -> str:
        """
        Generates a canonical internal name for the pane.

        Note: tmuxp does not support renaming individual panes directly. This function
        generates an internal name for UI mapping purposes only.

        :param pane: The libtmux.Pane (unused in renaming, but provided for consistency).
        :param tool_name: The name of the tool.
        :param scan_profile: The scan profile being used.
        :return: The generated canonical pane name as a string.
        """
        pane_title = f"{tool_name}_{scan_profile}_{int(time.time())}"
        return pane_title

    def create_and_rename_pane(self, window: libtmux.Window, tool_name: str,
                               scan_profile: str) -> Tuple[libtmux.Pane, str]:
        """
        Creates a new pane in the specified window and generates a canonical internal name for it.

        Note:
            tmuxp does not support renaming individual panes.

        :param window: The libtmux.Window to create the pane in.
        :param tool_name: The name of the tool initiating the scan.
        :param scan_profile: The scan profile being used.
        :return: A tuple containing:
                 - The created libtmux.Pane.
                 - The generated internal name (str) for the pane.
        """
        pane = self.create_pane(window)
        internal_name = self.rename_pane(pane, tool_name, scan_profile)
        return pane, internal_name

    def create_background_window(self, tool_name: str) -> libtmux.Window:
        """
        Creates and returns a new background window for the given tool in the current session.
        The window will be named 'bg_<tool_name>'.
        """
        window_name = f"bg_{tool_name}"
        self.logger.info(f"Creating background window '{window_name}' in session '{self.session_name}'.")
        try:
            window = self.session.new_window(window_name=window_name, attach=False)
            self.logger.info(f"Background window '{window_name}' created successfully.")
            return window
        except Exception as e:
            self.logger.exception(f"Error creating background window '{window_name}': {e}")
            raise

    def load_background_window(self, tool_name: str, bg_yaml_path: Path, ui_dir: Path) -> None:
        self.logger.info(f"Loading background window for tool: {tool_name}")
        self.logger.info(f"Using bg_yaml_path: {bg_yaml_path}")
        try:
            with open(bg_yaml_path, "r", encoding="utf-8") as f:
                template_str = f.read()
            template = jinja2.Template(template_str)
            rendered_yaml = template.render(
                TMUXP_DIR=str(ui_dir.resolve()),
                tool_name=tool_name,
                session_name="kalipyfi"  # Ensure it uses your main session.
            )
            self.logger.debug("Rendered YAML:\n" + rendered_yaml)

            tmp_yaml = Path(f"/tmp/bg_{tool_name}.yaml")
            with open(tmp_yaml, "w", encoding="utf-8") as f:
                f.write(rendered_yaml)

            # Launch tmuxp load in detached, non-interactive mode.
            cmd = f"tmuxp load --append {tmp_yaml} < /dev/null"
            self.logger.info(f"Executing command: {cmd}")
            proc = subprocess.Popen(cmd, shell=True, executable="/bin/bash",
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            self.logger.debug("tmuxp load stdout: " + stdout.decode("utf-8"))
            self.logger.debug("tmuxp load stderr: " + stderr.decode("utf-8"))
            self.logger.info(
                f"tmuxp load command issued for background window '{tool_name}', return code: {proc.returncode}")
        except Exception as e:
            self.logger.exception(f"Error loading background window for {tool_name}: {e}")

    def allocate_scan_pane(self, tool_name: str, scan_profile: str, cmd_dict: dict) -> str:
        # Ensure the background window exists:
        window = self.get_or_create_tool_window(tool_name)
        # Create a new pane in that window:
        pane = window.split_window(attach=False)
        pane_internal_name = self.rename_pane(pane, tool_name, scan_profile)
        command = self.convert_cmd_dict_to_string(cmd_dict)
        pane.send_keys(command, enter=True)
        self.logger.info(f"Launched scan in pane '{pane_internal_name}' with command: {command}")

        interface = cmd_dict.get("interface", "unknown")
        lock_status = self.get_lock_status(interface)
        pane_id = pane.get("pane_id")
        self._register_scan(window.get("window_name"), pane_id, pane_internal_name, tool_name, scan_profile, command,
                            interface, lock_status)
        return pane_id

    def update_interface(self, interface: str, lock_status: bool) -> None:
        """
        Updates or creates an entry in the interface registry.

        :param interface: The interface to update.
        :param lock_status: True if the interface should be locked; otherwise False.
        :return: None
        """
        self.interfaces[interface] = InterfaceData(interface=interface, lock_status=lock_status)
        self.logger.info(f"Interface {interface} updated to lock status: {lock_status}")

    @staticmethod
    def convert_cmd_dict_to_string(cmd_dict: dict) -> str:
        """
        Converts a command dictionary with keys 'executable' and 'arguments'
        into a command string.

        :param cmd_dict: The command dictionary to convert.
        :return: A command string (str).
        """
        executable = cmd_dict.get("executable", "")
        arguments = cmd_dict.get("arguments", [])
        return " ".join([executable] + arguments)

    ############################
    ##### USER INTERACTION #####
    ############################

    def swap_scan(self, tool_name: str, pane_id: str, new_title: str) -> None:
        """
        Updates the title (internal name) of a scan pane in the UI manager.

        Expected Format:
            {
                "tool": <tool_name>,
                "pane_id": <pane_id>,
                "new_title": <new_title>
            }

        Parameters
        ----------
        tool_name : str
            The name of the tool associated with the scan.
        pane_id : str
            The unique identifier of the pane whose title is to be updated.
        new_title : str
            The new title to assign to the scan pane for internal tracking.

        Returns
        -------
        None

        Raises
        ------
        KeyError
            If no active scan is found for the given pane_id.
        """
        # retrieve the active scan data from the UIManager's registry
        if pane_id not in self.active_scans:
            self.logger.error(f"No active scan found for pane_id: {pane_id}")
            raise KeyError(f"No active scan found for pane_id: {pane_id}")

        # verify the pane still exists
        pane = self._find_pane_by_id(pane_id)
        if not pane:
            self.logger.warning(f"Pane {pane_id} is not currently found; updating internal record only.")

        # update the internal name of the scan data
        scan_data = self.active_scans[pane_id]
        old_title = scan_data.internal_name
        scan_data.internal_name = new_title
        self.logger.info(f"Swapped scan title for pane {pane_id}: '{old_title}' -> '{new_title}'")


    def get_lock_status(self, interface: str) -> bool:
        """
        Retrieves the lock status for the given interface.

        :param interface: The interface to check.
        :return: True if the interface is locked, otherwise False.
        """
        iface_data = self.interfaces.get(interface)
        return iface_data.lock_status if iface_data else False


    def stop_scan(self, pane_id: str) -> None:
        """
        Stops the scan running in the specified pane and removes it from the active scans registry.

        :param pane_id: The pane ID (str) to stop.
        :return: None
        """
        scan_data = self.active_scans.get(pane_id)
        if scan_data:
            window = self.session.find_where({"window_name": scan_data.window_name})
            if window:
                pane = self._find_pane_by_id(pane_id)
                if pane:
                    pane.send_keys("C-c")  # Send Ctrl+C to stop the command.
                    self.logger.info(f"Stopped scan in pane {pane_id} (window: {scan_data.window_name}).")
            del self.active_scans[pane_id]


    def detach_ui(self) -> None:
        """
        Detaches the UI session by invoking the tmuxp detach-client command.
        This leaves the session running in the background.
        After detaching, exit the process.
        """
        session_name = self.session_data.session_name
        self.logger.info(f"Detaching UI session: {session_name}")
        os.system(f"tmuxp detach-client -s {session_name}")


    def kill_ui(self) -> None:
        session_name = self.session_data.session_name
        self.logger.info(f"Killing UI session: {session_name}")
        self.session.kill_session()
        try:
            # Kill all processes in the current process group.
            os.killpg(os.getpgrp(), signal.SIGTERM)
        except Exception as e:
            self.logger.exception("Error killing process group: %s", e)
        sys.exit(0)

    #############################
    ##### STATE & DEBUGGING #####
    #############################

    def wait_for_tool_window_ready(self, tool_name: str, bg_yaml_path: Path, tmuxp_dir: Path,
                                   expected_panes: int = 4, timeout: int = 30,
                                   poll_interval: float = 0.5) -> libtmux.Window:
        start_time = time.time()
        # First, check if the window exists. If not, load it once.
        window = self.get_tool_window(tool_name)
        if window is None:
            self.logger.info(f"Background window for '{tool_name}' not found. Attempting to load it.")
            self.load_background_window(tool_name, bg_yaml_path, tmuxp_dir)

        # Now poll until the window is ready.
        iteration = 0
        while time.time() - start_time < timeout:
            iteration += 1
            window = self.get_tool_window(tool_name)
            if window:
                panes = window.panes
                self.logger.debug(f"Window '{tool_name}' has {len(panes)} pane(s).")
                if len(panes) >= expected_panes:
                    valid = all(int(pane["pane_height"]) > 0 and int(pane["pane_width"]) > 0 for pane in panes)
                    if valid:
                        self.logger.info(f"Window '{tool_name}' is ready with {len(panes)} panes.")
                        return window
                    else:
                        if iteration % 5 == 0:
                            self.logger.debug(f"Window '{tool_name}' found but has invalid pane dimensions.")
                else:
                    if iteration % 5 == 0:
                        self.logger.debug(
                            f"Window '{tool_name}' found but only has {len(panes)} pane(s) (expected at least {expected_panes}).")
            else:
                if iteration % 5 == 0:
                    self.logger.debug(f"Window '{tool_name}' still not found.")
            time.sleep(poll_interval)

        self.logger.error(f"Timeout waiting for window '{tool_name}' to be ready.")
        raise TimeoutError(f"Timeout waiting for window '{tool_name}' with {expected_panes} panes.")

    def debug_list_windows(self) -> None:
        if not hasattr(self, "session") or self.session is None:
            self.logger.debug("No session available to list windows.")
            return
        self.logger.debug("Current session windows:")
        for window in self.session.windows:
            self.logger.debug(f"Session Name: {self.session_name}")
            self.logger.debug(f"Window: name='{window.get('window_name')}', id='{window.get('window_id')}'")

    def get_ui_state(self) -> dict:
        """
        Returns the current UI state as a dictionary containing active scans and interfaces.

        :return: A dict with keys 'active_scans' and 'interfaces'.
        """
        return {
            "active_scans": {pid: scan.to_dict() for pid, scan in self.active_scans.items()},
            "interfaces": {iface: data.to_dict() for iface, data in self.interfaces.items()}
        }