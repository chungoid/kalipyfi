# utils/ui/ui_manager.py
import os
import sys
import time
import signal
import jinja2
import libtmux
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

# local
from common.models import ScanData, InterfaceData, SessionData
from common.process_manager import process_manager
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
                        preset_description: str, command: str, interface: str,
                        lock_status: bool, timestamp: float, pane_pid: int) -> None:
        """
        Creates a ScanData object and updates the active_scans registry.

        :param window_name: The name of the window containing the scan.
        :param pane_id: The unique identifier of the pane.
        :param internal_name: The canonical internal name generated for the pane.
        :param tool_name: The name of the tool launching the scan.
        :param command: The executed command string.
        :param interface: The interface used for scanning.
        :param lock_status: The lock status of the interface.
        :param pane_pid: The unique process identifier for a task in the pane.
        :return: None
        """
        scan_data = ScanData(
            tool=tool_name,
            preset_description=preset_description,
            window_name=window_name,
            pane_id=pane_id,
            internal_name=internal_name,
            interface=interface,
            lock_status=lock_status,
            cmd_str=command,
            timestamp=timestamp,
            pane_pid=int(pane_pid) if pane_pid else None
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
        self.logger.debug(f"Launched scan command: {command} in pane {pane.get('pane_id')}")

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
        """
        Returns an existing tmux session with the specified name, or creates one if it does not exist.

        :param session_name: The name of the tmux session to retrieve or create.
        :return: A libtmux.Session object representing the tmux session.
        """
        session = self.get_session(session_name)
        self.logger.debug(f"get_or_create_session Found session: {session}")
        if session is None:
            session = self.create_session(session_name)
            self.logger.info(f"get_or_create_session found no session so creating session: {session}")
        return session


    def get_tool_window(self, tool_name: str) -> Optional[libtmux.Window]:
        """
        Retrieves the background window for a specified tool from the current tmux session.

        The expected window name is constructed as "bg_<tool_name>". The function logs all
        window names for debugging and returns the window if it is found.

        :param tool_name: The name of the tool whose background window is being searched.
        :return: A libtmux.Window object if a window with the expected name is found; otherwise, None.
        """
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

        :param: tool_name: The name of the tool the window is for.
        :return: The newly created libtmux.Window.
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

    def rename_pane(self, pane: libtmux.Pane, tool_name: str, preset_description: str) -> str:
        """
        Generates a canonical internal name for the pane.

        Note: tmuxp does not support renaming individual panes directly. This function
        generates an internal name for UI mapping purposes only.

        :param pane: The libtmux.Pane (unused in renaming, but provided for consistency).
        :param tool_name: The name of the tool.
        :param preset_description: The scan profile being used.
        :return: The generated canonical pane name as a string.
        """
        pane_title = f"{tool_name}_{preset_description}_{int(time.time())}"
        return pane_title

    def create_and_rename_pane(self, window: libtmux.Window, tool_name: str,
                               preset_description: str) -> Tuple[libtmux.Pane, str]:
        """
        Creates a new pane in the specified window and generates a canonical internal name for it.

        Note:
            tmuxp does not support renaming individual panes.

        :param window: The libtmux.Window to create the pane in.
        :param tool_name: The name of the tool initiating the scan.
        :param preset_description: The scan profile being used.
        :return: A tuple containing:
                 - The created libtmux.Pane.
                 - The generated internal name (str) for the pane.
        """
        pane = self.create_pane(window)
        internal_name = self.rename_pane(pane, tool_name, preset_description)
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

    def allocate_scan_window(self, tool_name: str, cmd_dict: dict, interface: str,
                             timestamp: float, preset_description: str, pane_pid: int, callback_socket: str) -> str:
        """
        Creates a dedicated window for a scan, launches the scan command in its single pane,
        and registers the scan with the UI manager.

        :param tool_name: The name of the tool initiating the scan.
        :param cmd_dict: A dictionary containing the command details to execute (with keys 'executable' and 'arguments').
        :param interface: The scan interface that will be used.
        :param timestamp: The timestamp indicating when the scan was started.
        :param preset_description: The description extracted from the preset configuration used to label the scan.
        :param pane_pid: The process id of the task running within the pane.
        :param callback_socket: The callback socket path for notifications.
        :return: The pane identifier where the scan command was launched.
        """
        # Create a unique window name using the tool name and timestamp.
        window_name = f"scan_{tool_name}_{int(timestamp)}"
        self.logger.info(f"Creating dedicated scan window: {window_name}")
        window = self.session.new_window(window_name=window_name, attach=False)

        # Use the first (and only) pane in the newly created window.
        pane = window.panes[0]

        # Build the canonical internal pane name using the provided interface and preset description.
        preset_desc = preset_description if preset_description else "unknown"
        pane_internal_name = f"{tool_name}_{interface}_{preset_desc}_{int(timestamp)}"

        # Convert the command dictionary to a string and send it to the pane.
        command = self.convert_cmd_dict_to_string(cmd_dict)
        pane.send_keys(command, enter=True)
        self.logger.debug(
            f"Launched scan in dedicated window '{window_name}' pane '{pane_internal_name}' with command: {command}"
        )

        # Retrieve the interface's lock status and register the scan.
        lock_status = self.get_lock_status(interface)
        pane_id = pane.get("pane_id")
        pane_pid = pane.get("pane_pid")
        if not pane_pid:
            pane_pid = subprocess.check_output(f"tmux list-panes -F '#{{pane_pid}}' -t {pane.get('pane_id')}",
                                               shell=True).decode().strip()
        self.logger.debug(f"Captured pane_pid: {pane_pid}")

        self._register_scan(window_name=window.get("window_name"), pane_id=pane_id, internal_name=pane_internal_name,
                            tool_name=tool_name, preset_description=preset_description, command=command,
                            interface=interface, lock_status=lock_status, timestamp=timestamp, pane_pid=pane_pid)

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

    def swap_scan(self, tool_name: str, dedicated_pane_id: str, new_title: str) -> None:
        """
        Swaps a dedicated scan pane (allocated in its own window) with the main scan pane
        in the main UI window, then toggles zoom on the new main scan pane so that it occupies
        the full display area, and finally re-focuses the main menu pane.

        This function performs the following steps:
          1. Verifies that the dedicated scan pane exists in the active scans.
          2. Identifies the current main scan pane in the main UI window (using a heuristic based on pane size).
          3. Uses tmux's swap-pane command to swap the dedicated scan pane with the main scan pane.
          4. Toggles zoom (via tmux resize-pane -Z) on the new main scan pane so that it fills the window.
          5. Re-selects the main menu pane so that focus remains on the menu.

        :param tool_name: The name of the tool associated with the scan.
        :param dedicated_pane_id: The pane ID of the dedicated scan pane to be swapped in.
        :param new_title: The new internal title to assign to the scan after swapping (e.g., "wlan1_passive").
        :return: None
        :raises KeyError: If no active scan is found for the given dedicated pane ID.
        """
        if dedicated_pane_id not in self.active_scans:
            self.logger.error(f"No active scan found for pane_id: {dedicated_pane_id}")
            raise KeyError(f"No active scan found for pane_id: {dedicated_pane_id}")

        scan_data = self.active_scans[dedicated_pane_id]
        old_title = scan_data.internal_name

        # identify the current main scan pane in the main UI window
        main_pane = self.get_main_scan_pane()
        if not main_pane:
            self.logger.error("Main scan pane not found; cannot swap scan pane.")
            return

        main_pane_id = main_pane.get("pane_id")
        self.logger.debug(f"Main scan pane identified: {main_pane_id}")

        # swap the dedicated scan pane with the main scan pane
        swap_cmd = f"tmux swap-pane -s {dedicated_pane_id} -t {main_pane_id}"
        self.logger.debug(f"Executing swap-pane command: {swap_cmd}")
        try:
            subprocess.run(swap_cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error executing swap-pane command: {e}")
            return

        # toggle zoom on the new main scan pane so that it occupies the full window area
        zoom_cmd = f"tmux resize-pane -Z -t {main_pane_id}"
        self.logger.debug(f"Executing zoom command: {zoom_cmd}")
        try:
            subprocess.run(zoom_cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error executing zoom command: {e}")
            return

        # update the internal scan data with the new title
        scan_data.internal_name = new_title
        self.logger.info(f"Swapped scan pane {dedicated_pane_id}: '{old_title}' -> '{new_title}'")

        # re-select the main menu pane so that focus remains on the menu
        main_menu_pane = self.get_main_menu_pane()
        if main_menu_pane:
            select_cmd = f"tmux select-pane -t {main_menu_pane.get('pane_id')}"
            self.logger.debug(f"Re-selecting main menu pane with command: {select_cmd}")
            try:
                subprocess.run(select_cmd, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error re-selecting main menu pane: {e}")


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

        :return: None
        """
        session_name = self.session_data.session_name
        self.logger.info(f"Detaching UI session: {session_name}")
        os.system(f"tmuxp detach-client -s {session_name}")

    def kill_ui(self) -> None:
        """
        Kills Kalipyfi UI and all process groups.

        :return: None
        """
        session_name = self.session_data.session_name
        self.logger.info(f"Killing UI session: {session_name}")

        # Log status before shutdown
        self.logger.debug("UI Manager status before shutdown:\n" + process_manager.get_status_report())

        # Shutdown all registered processes
        process_manager.shutdown_all()

        # Attempt to kill the tmux session via libtmux and subprocess
        try:
            self.session.kill_session()
            self.logger.debug("tmux session killed via libtmux.")
        except Exception as e:
            self.logger.exception("Error killing tmux session via libtmux: %s", e)

        try:
            import subprocess
            subprocess.run(f"tmux kill-session -t {session_name}", shell=True, check=True)
            self.logger.debug("tmux session killed via subprocess command.")
        except Exception as e:
            self.logger.exception("Error killing tmux session via command: %s", e)

        # kill the entire process group
        try:
            os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
            self.logger.debug("Killed entire process group.")
        except Exception as e:
            self.logger.exception("Error killing process group: %s", e)

        self.logger.info("UI shutdown complete. Exiting now.")
        sys.exit(0)

    #############################
    ##### STATE & DEBUGGING #####
    #############################

    def get_main_scan_pane(self) -> Optional[libtmux.Pane]:
        """
        Retrieves the main scan pane from the main UI window.

        In your current layout, the main UI window ("kalipyfi") always has its
        main scan pane at pane index "0". This function returns that pane.

        :return: Optional[libtmux.Pane]:
            Main scan viewing pane.
        """
        main_window = self.session.find_where({"window_name": "kalipyfi"})
        if not main_window:
            self.logger.error("Main UI window 'kalipyfi' not found.")
            return None

        for pane in main_window.panes:
            if pane.get("pane_index") == "0":
                self.logger.debug(f"Main scan pane identified: {pane.get('pane_id')}")
                return pane

        self.logger.error("Main scan pane with index '0' not found in main UI window.")
        return None


    def get_main_menu_pane(self) -> Optional[libtmux.Pane]:
        """
        Identifies the main menu pane in the main UI window.

        In our layout, the main menu pane is always at pane_index "1" in the "kalipyfi" window.

        :return: Optional[libtmux.Pane]:
            pane index "1" which should always be the main menu pane.
        """
        main_window = self.session.find_where({"window_name": "kalipyfi"})
        if not main_window:
            self.logger.error("Main UI window 'kalipyfi' not found.")
            return None

        for pane in main_window.panes:
            if pane.get("pane_index") == "1":
                return pane

        self.logger.error("Main menu pane with index '1' not found in main UI window.")
        return None


    def get_log_pane(self) -> Optional[libtmux.Pane]:
        """
        Identifies the log pane in the main UI window.

        In our layout, the log pane is always at pane_index "2" in the "kalipyfi" window.

        :return: Optional[libtmux.Pane]:
            The pane with index "2" in the "kalipyfi" window, or None if not found.
        """
        main_window = self.session.find_where({"window_name": "kalipyfi"})
        if not main_window:
            self.logger.error("Main UI window 'kalipyfi' not found.")
            return None

        for pane in main_window.panes:
            if pane.get("pane_index") == "2":
                return pane

        self.logger.error("Log pane with index '2' not found in main UI window.")
        return None


    def wait_for_tool_window_ready(self, tool_name: str, bg_yaml_path: Path, tmuxp_dir: Path,
                                   expected_panes: int = 4, timeout: int = 30,
                                   poll_interval: float = 0.5) -> libtmux.Window:
        """
        Waits until the specified tool's window is fully loaded and ready.

        This function checks for the existence of a tmux window for the given tool.
        If the window does not exist, it attempts to load it using the provided YAML configuration.
        Then, it repeatedly polls until the window has at least the expected number of panes
        and each pane has valid dimensions (height and width greater than zero).

        :param tool_name: The name of the tool whose window is being waited on.
        :param bg_yaml_path: The path to the background YAML configuration file used to load the window if needed.
        :param tmuxp_dir: The directory containing the tmuxp configurations.
        :param expected_panes: The minimum number of panes expected in the window (default is 4).
        :param timeout: The maximum time in seconds to wait for the window to be ready (default is 30).
        :param poll_interval: The interval in seconds between successive polls (default is 0.5).
        :return: The libtmux.Window object representing the ready window.
        :raises TimeoutError: If the window does not become ready within the specified timeout.
        """
        start_time = time.time()
        # check if window exists, if not, load it once
        window = self.get_tool_window(tool_name)
        if window is None:
            self.logger.info(f"Background window for '{tool_name}' not found. Attempting to load it.")
            self.load_background_window(tool_name, bg_yaml_path, tmuxp_dir)

        # poll til ready
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
        """
        debug logging, lists windows in self.session.windows

        :return: None
        """
        if not hasattr(self, "session") or self.session is None:
            return
        self.logger.debug("Current session windows:")
        for window in self.session.windows:
            self.logger.debug(f"Session Name: {self.session_name}")
            self.logger.debug(f"Window: name='{window.get('window_name')}', id='{window.get('window_id')}'")

    def get_ui_state(self) -> dict:
        """
        Returns a detailed dictionary representing the current UI state, including all windows and panes,
        active scans, and interface data.

        The returned dictionary contains the following keys:
        - "windows": A list of dictionaries, each representing a window with:
            - "window_id": The window's unique identifier.
            - "window_name": The window's name.
            - "panes": A list of dictionaries for each pane containing:
                - "pane_id": The pane's unique identifier.
                - "pane_index": The pane's index within the window.
                - "pane_height": The pane's height.
                - "pane_width": The pane's width.
                - "tmux_title": The pane title as reported by tmux.
                - "internal_title": The internal title from active scans, or "N/A" if not set.
        - "active_scans": A mapping of pane IDs to their ScanData (converted to dictionaries).
        - "interfaces": A mapping of interface names to their InterfaceData (converted to dictionaries).

        :return: A dictionary representing the current UI state.
        """
        state = {
            "windows": [],
            "active_scans": {pid: scan.to_dict() for pid, scan in self.active_scans.items()},
            "interfaces": {iface: data.to_dict() for iface, data in self.interfaces.items()}
        }

        # Iterate over all windows in the session.
        for window in self.session.windows:
            window_state = {
                "window_id": window.get("window_id"),
                "window_name": window.get("window_name"),
                "panes": []
            }
            for pane in window.panes:
                pane_id = pane.get("pane_id")
                # Retrieve tmuxp pane title via a shell command.
                title_cmd = f'tmuxp display-message -p "#{{pane_title}}" -t {pane_id}'
                result = subprocess.run(title_cmd, shell=True, capture_output=True, text=True)
                tmux_title = result.stdout.strip() if result.returncode == 0 else "N/A"
                # Get internal title from active scans if available.
                internal_title = self.active_scans.get(pane_id).internal_name if pane_id in self.active_scans else "N/A"
                pane_state = {
                    "pane_id": pane_id,
                    "pane_index": pane.get("pane_index"),
                    "pane_height": pane.get("pane_height"),
                    "pane_width": pane.get("pane_width"),
                    "tmux_title": tmux_title,
                    "internal_title": internal_title
                }
                window_state["panes"].append(pane_state)
            state["windows"].append(window_state)

        return state