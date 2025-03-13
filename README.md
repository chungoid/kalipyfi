<div align="center">
  <img src="utils/ui/tmuxp/img.png" alt="Kalipyfi Logo">
</div>

## Installation
```bash
git clone https://github.com/chungoid/kalipyfi
cd kalipyfi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## change path in kalipyfi (not .py) ##
SET YOUR DIRECTORY PATH
KALIPYFI_DIR="/fullpath/to/kalipyfi/"

## run:
sudo kalipyfi
```

## Usage
### Current Tools:
- hcxtools 
  - perform wireless scans
  - database storage
  - export to map.html and view in web browser (if gpsd enabled)
  - upload/download via wpasec
  - define custom scan configs using cli args in config.yaml
- nmap 
  - perform network scans
  - automatic gateway parsing
  - automatic host parsing
  - define custom scan configs using cli args in config.yaml
- pyfyconnect 
  - manage network connections
  - automatic station parsing
  - connect from database 
  - manual connect

- Every tool has a config.yaml file located within that tools configs directory
- Define interfaces & cli cmd presets as shown below
- Database is stored in the parent directory of kalipyfi as .kalipyfi to remain separated from repository management
- Otherwise, simply explore menu options.
```yaml
interfaces: # example that goes in all tools configs/config.yaml
  wlan:
  - description: hotspot # short description
    locked: true # optionally set to locked so tools ignore it (defunct, likely removing)
    name: wlan0 # interface name 
  - description: monitor
    locked: false
    name: wlan1
  - description: client
    locked: true
    name: wlan2
  # and so on and so fourth.. add as many as you'd like
```
```yaml
presets: # example from tools/nmap/configs/config.yaml
  1: 
    description: sVC # description you'll see in menu
    options: # cli args as you'd set them if you were running the command
      -A: true
      --top-ports: 1000 
```
```yaml
presets: #example from tools/hcxtool/configs/config.yaml
  4:
    description: silent
    options:
      --attemptapmax: 0
      --disable_beacon: true
      --gpsd: true
      -F: true
      autobpf: true # example of custom tool arg.. see: tools/helpers/autobpf.py & tools/hcxtool.py
```

## Adding Custom Tool Modules
Subclass the Tool Base Class:
- Create your new tool by subclassing the Tool base class (found in tools/tools.py). This class handles configuration loading, directory setup, command building, and IPC communication. Override the required methods—especially the submenu() method—to define your tool’s custom user interface and functionality.

Implement a Custom Submenu:
- Use or extend the submenu base class (similar to the existing HcxToolSubmenu) to build an interactive curses-based UI for your tool. This submenu can provide options specific to your tool while inheriting common navigation and display functionality. The custom submenu should be implemented as a callable (typically via the __call__ method) so that it can be easily integrated with the main UI.

Leverage Existing IPC Handlers:
- Your tool can make use of the existing IPC handlers (located in ipc_protocol.py) to send and receive messages. This enables you to launch scans or other processes in dedicated panes, manage state, and interact with the UI manager without having to write your own inter-process communication logic.

Register Your Tool:
- Simply decorate your tool class with the @register_tool decorator from utils/tool_registry.py. This adds your tool to the global tool registry. Once registered, the main menu (in main_menu.py) automatically imports and displays your custom tool as one of the available modules (don't forget to import your tool in utils/ui/main_menu.py) in the main menu.

Customize as Needed:
- With your tool registered and its submenu implemented, you can further customize the functionality by creating your own command-line options and utilize them in config.yaml (example: autobpf in hcxtool, and its helper in tools/helpers.py), logging, and IPC message formats. The modular design ensures that your tool integrates smoothly with the existing UI and process management features.

- Define your tools path in config/constants.py:
```bash
TOOL_PATHS = {
    "hcxtool": TOOLS_DIR / "hcxtool",
    "pyfyconnect": TOOLS_DIR / "pyfyconnect",
    "nmap": TOOLS_DIR / "nmap",
    "yourtool": TOOLS_DIR / "yourtool",
}
```
- Import your tool in utils/ui/main_menu.py:
```bash
# import all tool modules so they load via decorators
from utils.tool_registry import tool_registry
from tools.hcxtool import hcxtool
from tools.pyfyconnect import pyfyconnect
from tools.nmap import nmap
from tools.yourtool import yourtool 
```
- Example Class Template For yourtool:
```bash
from abc import ABC
from tools.tools import Tool
from utils.tool_registry import register_tool
from your_submenu_module import YourToolSubmenu

@register_tool("yourtool")
class YourTool(Tool, ABC):
    def __init__(self, base_dir, config_file=None, interfaces=None, presets=None):
        super().__init__(
            name="yourtool",
            description="Your custom tool description",
            base_dir=base_dir,
            config_file=config_file,
            interfaces=interfaces,
            settings=presets
        )
        self.logger = logging.getLogger(self.name)
        self.submenu = YourToolSubmenu(self)

    def submenu(self, stdscr) -> None:
      """
      Launches your custom submenu (interactive UI) using curses.
      """
      self.submenu_instance(stdscr)
        
    def build_command(self) -> list:
      """
      Write custom command building logic for your cli tool here.     
      """
      return cmd

    def run(self) -> None:
        """
        Override this method with custom behavior and a call to run_to_ipc() (from tools/tools.py)
        """
        # process your build_command
        self.logger.debug("Building scan command.")
        try:
            cmd_list = self.build_command()
            if not cmd_list:
                self.logger.critical("Error: build_command() returned an empty command.")
                return
                
            # convert command to dict before sending to IPC    
            cmd_dict = self.cmd_to_dict(cmd_list)
        
            # send built and processed command to the IPC server
            response = self.run_to_ipc(cmd_dict)
```
- Example Submenu Template For yourtool:
```bash
# Import the base submenu class
from tools.submenu import BaseSubmenu
import curses

class YourToolSubmenu(BaseSubmenu):
    def __init__(self, tool_instance):
        # Call the base constructor passing in the tool instance.
        super().__init__(tool_instance)
        self.logger = logging.getLogger("YourToolSubmenu")
        self.logger.debug("YourToolSubmenu initialized.")

    def pre_launch_hook(self, parent_win) -> bool:
        """
        Optional hook executed before launching a scan.
        For example, prompt the user to select a target or set custom options.
        
        Parameters
        ----------
        parent_win : curses window
            The window where the prompt is displayed.
        
        Returns
        -------
        bool
            True if the user successfully selects an option, False otherwise.
        """
        # Retrieve available options from the tool (e.g. networks, interfaces)
        options = self.tool.get_available_options()
        if not options:
            parent_win.clear()
            parent_win.addstr(0, 0, "No options available!")
            parent_win.refresh()
            parent_win.getch()
            return False

        # Build a menu list using the retrieved options.
        menu_items = [f"{key}: {value}" for key, value in options.items()]
        selection = self.draw_paginated_menu(parent_win, "Select an Option", menu_items)
        if selection == "back":
            return False
        try:
            # Parse the selection and update the tool's state.
            key, value = selection.split(":", 1)
            self.tool.selected_option = value.strip()
            self.logger.debug("Selected option: %s", self.tool.selected_option)
            return True
        except Exception as e:
            self.logger.error("Error parsing selection: %s", e)
            return False

    def __call__(self, stdscr) -> None:
        """
        The entry point for the submenu interface.
        This method is automatically called when your tool's submenu is invoked.
        It initializes the curses screen, resets any state variables,
        and displays the main menu options.

        Parameters
        ----------
        stdscr : curses window
            The primary curses window provided by curses.wrapper.
        """
        # Hide the cursor and clear the screen.
        curses.curs_set(0)
        stdscr.clear()

        # Reset or initialize any tool-specific state.
        self.tool.reset_state()
        self.tool.reload_config()
        self.tool.update_available_options()

        # (Optional) Create a debug window or reserve a section for logging.
        max_y, max_x = stdscr.getmaxyx()
        menu_height = max_y - 4  # Reserve bottom 4 lines for debugging
        submenu_win = stdscr.derwin(menu_height, max_x, 0, 0)
        submenu_win.keypad(True)
        submenu_win.clear()
        submenu_win.refresh()

        # Define the main menu options for your tool.
        menu_items = ["Launch Scan", "View Scans", "Settings", "Back"]
        numbered_menu = [f"[{i + 1}] {item}" for i, item in enumerate(menu_items[:-1])]
        numbered_menu.append("[0] Back")

        # Main loop: draw the menu and process user input.
        while True:
            menu_win = self.draw_menu(submenu_win, f"{self.tool.name}", numbered_menu)
            key = menu_win.getch()
            try:
                ch = chr(key)
            except Exception:
                continue

            if ch == "1":
                # Launch a scan after running the pre-launch hook if needed.
                if self.pre_launch_hook(submenu_win):
                    self.launch_scan(submenu_win)
            elif ch == "2":
                self.view_scans(submenu_win)
            elif ch == "3":
                self.settings_menu(submenu_win)
            elif ch == "0" or key == 27:
                break

            submenu_win.clear()
            submenu_win.refresh()
```
- Define new IPC keys or actions in config/constants.py:
```bash
IPC_CONSTANTS = {
    "keys": {
        "ACTION_KEY": "action",
        "TOOL_KEY": "tool",
        "SCAN_PROFILE_KEY": "scan_profile",
        "COMMAND_KEY": "command",
        "TIMESTAMP_KEY": "timestamp",
        "STATUS_KEY": "status",
        "RESULT_KEY": "result",
        "ERROR_KEY": "error",
        "EXAMPLE_ONE": "EXAMPLE_ONE", # like this
    },
    "actions": {
        "PING": "PING",
        "GET_STATE": "GET_STATE",
        "REGISTER_PROCESS": "REGISTER_PROCESS",
        "UI_READY": "UI_READY",
        "GET_SCANS": "GET_SCANS",
        "SEND_SCAN": "SEND_SCAN",
        "SWAP_SCAN": "SWAP_SCAN",
        "STOP_SCAN": "STOP_SCAN",
        "CONNECT_NETWORK": "CONNECT_NETWORK",
        "UPDATE_LOCK": "UPDATE_LOCK",
        "REMOVE_LOCK": "REMOVE_LOCK",
        "KILL_UI": "KILL_UI",
        "DETACH_UI": "DETACH_UI",
        "DEBUG_STATUS": "DEBUG_STATUS",
        "EXAMPLE_TWO": "EXAMPLE_TWO", # like this
    }
```
- Create Custom Handler in common/ipc_protocol.py
```bash 
def handle_example_one(ui_instance, request: dict) -> dict:
    """
     Handles the EXAMPLE_TWO command by calling examplefunction.

    Expected Format:
        {
            "action": "EXAMPLE_TWO",
            "timestamp": time.time()",
            "tool": <tool_name>,
            "example_one": # whatever you want
        }
    """
    try:
        ui_instance.examplefunction(params)
        logger.debug("handle_example_two: Example returned successfully")
        return {"status": "EXAMPLE_TWO_OK"}
    except Exception as e:
        logger.exception("handle_stop_scan: Exception occurred")
        return {ERROR_KEY: f"EXAMPLE_TWO error: {e}"}
```
- Add Your Custom Handler in utils/ipc.py:
```bash
# add your new action to the unpacked constants
from config.constants import IPC_CONSTANTS
PING = IPC_CONSTANTS["actions"]["PING"]
GET_STATE = IPC_CONSTANTS["actions"]["GET_STATE"]
UI_READY = IPC_CONSTANTS["actions"]["UI_READY"]
...
...
EXAMPLE_TWO = IPC_CONSTANTS["actions"]["EXAMPLE_TWO"]

# add your action to _handle_connections()
      elif action == EXAMPLE_TWO:
        response = handle_example_two(self.ui_instance, request)
```
- Use Your Action in yourtool:
```bash
def yourtool_function() -> Optional[Dict]:
    # import client
    client = IPCClient()
    
    # custom function logic here
    ...
    ...
        # define message dict 
        ipc_message = {
            # ensure EXAMPLE_TWO handler expects values in ipc_message dict
            "action": "EXAMPLE_TWO", # optional
            "timestamp": time.time() # optional
            "tool": self.name # optional
            "example_one": # optional key in handler
        }
        self.logger.debug("Sending IPC scan command: %s", ipc_message)

        # response will always be json
        response = client.send(ipc_message)
        return response # optional
```