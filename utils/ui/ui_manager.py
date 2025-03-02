# utils/ui/ui_manager.py
import os
import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
import libtmux
import jinja2

from common.models import ScanData, InterfaceData, SessionData
from config.constants import BG_YAML_PATH

class UIManager:
    def __init__(self, session_name: str = "kalipyfi") -> None:
        """
        Initializes the UIManager by connecting to a tmux server and ensuring
        a tmux session with the given session_name exists.

        :param session_name: The name of the tmux session to use/create.
        """
        self.logger = logging.getLogger("UIManager")
        self.server = libtmux.Server()
        self.session = self.get_or_create_session(session_name)
        self.session_data = SessionData(session_name=self.session.get("session_name"))
        # Active scans: map pane_id -> ScanData
        self.active_scans: Dict[str, ScanData] = {}
        # Tool Interfaces: map interface name -> InterfaceData
        self.interfaces: Dict[str, InterfaceData] = {}

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
        Retrieves an existing tmux session by name.

        :param session_name: The name of the tmux session.
        :return: The libtmux.Session if found, otherwise None.
        """
        return self.server.find_where({"session_name": session_name})

    def create_session(self, session_name: str) -> libtmux.Session:
        """
        Creates a new tmux session with the given name.

        :param session_name: The desired session name.
        :return: The newly created libtmux.Session.
        """
        self.logger.info(f"Creating new session: {session_name}")
        return self.server.new_session(session_name=session_name, attach=False)

    def get_or_create_session(self, session_name: str) -> libtmux.Session:
        """
        Retrieves the session if it exists, or creates a new one if not.

        :param session_name: The name of the session.
        :return: A libtmux.Session object.
        """
        session = self.get_session(session_name)
        if session is None:
            session = self.create_session(session_name)
        return session

    def get_tool_window(self, tool_name: str) -> Optional[libtmux.Window]:
        """
        Retrieves the background window for a given tool.

        :param tool_name: The tool's name.
        :return: The libtmux.Window if found, otherwise None.
        """
        window_name = f"bg_{tool_name}"
        return self.session.find_where({"window_name": window_name})

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

    def get_or_create_tool_window(self, tool_name: str, background_yaml_path: Path,
                                  ui_dir: Path) -> libtmux.Window:
        """
        Retrieves the background window for a tool. If it doesn't exist,
        loads it using the background tmuxp YAML template.

        :param tool_name: Name of the tool.
        :param background_yaml_path: Path to the YAML template for background windows.
        :param ui_dir: The UI directory to be injected into the template.
        :return: A libtmux.Window for the tool.
        """
        window = self.get_tool_window(tool_name)
        if window is None:
            self.load_background_window(tool_name, background_yaml_path, ui_dir)
            window = self.get_tool_window(tool_name)
            if window is None:
                self.logger.error(f"Failed to create background window for {tool_name}.")
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

        Note: tmux does not support renaming individual panes directly. This function
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
            tmux does not support renaming individual panes.

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

    def load_background_window(self, tool_name: str, background_yaml_path: Path,
                               ui_dir: Path) -> None:
        """
        Loads the background window for the given tool using a tmuxp YAML template.
        Renders the template with provided path variables and tool-specific variables,
        writes the rendered YAML to a temporary file, and loads it via tmuxp.

        :param tool_name: The name of the tool.
        :param background_yaml_path: Path to the YAML template for background windows.
        :param ui_dir: The UI directory to be injected into the template.
        :return: None
        """
        self.logger.info(f"Loading background window for tool: {tool_name}")
        with open(background_yaml_path, "r") as f:
            template_str = f.read()

        template = jinja2.Template(template_str)
        rendered_yaml = template.render(UI_DIR=str(ui_dir.resolve()), tool_name=tool_name)

        tmp_yaml = Path(f"/tmp/bg_{tool_name}.yaml")
        with open(tmp_yaml, "w") as f:
            f.write(rendered_yaml)

        os.system(f"tmuxp load {tmp_yaml}")

    def allocate_scan_pane(self, tool_name: str, scan_profile: str, cmd_dict: dict,
                           background_yaml_path: Path, ui_dir: Path) -> str:
        """
        Allocates a new pane within the tool's background window (loaded from a YAML template),
        launches the scan command in that pane, and updates the active scan registry.

        :param tool_name: The name of the tool (str).
        :param scan_profile: The scan profile to use (str).
        :param cmd_dict: A dictionary containing the scan command details; expected keys are
                         'executable' (str) and 'arguments' (List[str]). Additionally, it should include an
                         "interface" key indicating the scanning interface.
        :param background_yaml_path: A Path to the YAML template for background windows.
        :param ui_dir: A Path representing the UI directory to be injected into the YAML template.
        :return: The pane_id (str) of the allocated pane.
        """
        window = self.get_or_create_tool_window(tool_name, background_yaml_path, ui_dir)
        pane = self.create_pane(window)
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
        Detaches the UI session by invoking the tmux detach-client command.
        This leaves the session running in the background.
        After detaching, exit the process.
        """
        session_name = self.session_data.session_name
        self.logger.info(f"Detaching UI session: {session_name}")
        os.system(f"tmux detach-client -s {session_name}")
        sys.exit(0)

    def kill_ui(self) -> None:
        """
        Kills the UI session and all associated windows.
        After killing the session, exit the process.
        """
        session_name = self.session_data.session_name
        self.logger.info(f"Killing UI session: {session_name}")
        self.session.kill_session()
        sys.exit(0)


    #############################
    ##### STATE & DEBUGGING #####
    #############################
    def get_ui_state(self) -> dict:
        """
        Returns the current UI state as a dictionary containing active scans and interfaces.

        :return: A dict with keys 'active_scans' and 'interfaces'.
        """
        return {
            "active_scans": {pid: scan.to_dict() for pid, scan in self.active_scans.items()},
            "interfaces": {iface: data.to_dict() for iface, data in self.interfaces.items()}
        }
