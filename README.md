<div align="center">
  <img src="utils/ui/tmuxp/img.png" alt="Kalipyfi Logo">
</div>

## Installation
```bash
git clone https://github.com/chungoid/kalipyfi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## change path in kalipyfi (not .py) ##
## and optionally move to /usr/local/bin/ ##
SET YOUR DIRECTORY PATH
KALIPYFI_DIR="/fullpath/to/kalipyfi/"

## and then run:
sudo kalipyfi
```

## Usage

- Every tool has a config.yaml file located within that tools configs directory
- Define interfaces & cli cmd presets as shown below
- Database is stored in the parent directory of kalipyfi as .kalipyfi to remain separated from repository management
- Otherwise, simply explore menu options.
```yaml
interfaces:
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
  
presets:
  1: 
    description: sVC # description you'll see in menu
    options: # cli args as you'd set them if you were running the command
      -A: true
      --top-ports: 1000
```

## Adding Custom Tool Modules
Subclass the Tool Base Class:
Create your new tool by subclassing the Tool base class (found in tools/tools.py). This class handles configuration loading, directory setup, command building, and IPC communication. Override the required methods—especially the submenu() method—to define your tool’s custom user interface and functionality.

Implement a Custom Submenu:
Use or extend the submenu base class (similar to the existing HcxToolSubmenu) to build an interactive curses-based UI for your tool. This submenu can provide options specific to your tool while inheriting common navigation and display functionality. The custom submenu should be implemented as a callable (typically via the __call__ method) so that it can be easily integrated with the main UI.

Leverage Existing IPC Handlers:
Your tool can make use of the existing IPC handlers (located in ipc_protocol.py) to send and receive messages. This enables you to launch scans or other processes in dedicated panes, manage state, and interact with the UI manager without having to write your own inter-process communication logic.

Register Your Tool:
Simply decorate your tool class with the @register_tool decorator from utils/tool_registry.py. This adds your tool to the global tool registry. Once registered, the main menu (in main_menu.py) automatically imports and displays your custom tool as one of the available modules.

Customize as Needed:
With your tool registered and its submenu implemented, you can further customize the functionality by adding your own command-line options, logging, and IPC message formats. The modular design ensures that your tool integrates smoothly with the existing UI and process management features.

Example:
```bash
from tools.tools import Tool
from utils.tool_registry import register_tool
from your_submenu_module import YourToolSubmenu

@register_tool("yourtool")
class YourTool(Tool):
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

    def submenu(self, stdscr):
        """
        Launches your custom CLI interface.
        Implement your curses-based submenu here.
        """
        self.submenu(stdscr)

    def run(self):
        """
        Override this method if you need custom behavior when launching a scan or process.
        Otherwise, you can use the base functionality for IPC communication.
        """
        # Build your command and send it via IPC using run_to_ipc()
        pass

```
