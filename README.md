# Kalipyfi

Kalipyfi launches a tmux session via tmuxp yaml template that displays a main scan window up top
& a curses menu below. Once sent, scans will be in their own background windows until they're called to swap
or stop via their submenu. Swapped scans from the background will then appear in the main scan window above
the curses menu.

You can very easily expand off the Tool class and implement your own tool into the UI.

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

- Define your scans via tool specific config/config.yaml files.
- ex: /tools/hcxtool/configs/config.yaml
```yaml
interfaces:
  wlan:
  - description: hotspot # short desc. e.g. hotspot
    locked: true # optionally set to locked so tools ignore it (future)
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
    description: aggressive #short desc
    options: # append tool commandline options below. 
      autobpf: true # this one is an optional addition.
      -A: true
      -F: true
      --gpsd: true
      # tips: (autobpf: true) will protect the scan devices associated clients/ap's 
      # (e.g. your wlan0 hotspot, and its ssh clients or your home wifi) from a scan
      # interface interfering with friendly connections.
      #
      # tools have self.selected_interface which is set before sending scans.. omit interface from config
      # omit -w as well, hcxtool will create its own file and output to tools/hcxtools/results/
      # use option output_prefix if you want a custom prefix.. also, --gpsd: true will handle .nmea file creation
```

- every future tool will share a similar configuration scheme where you can define command-line options
and then configure an interface via submenus & then select scan profiles to run on the selected interface.

- if you'd like to make your own tool modules go for it.. enjoy.


