import curses
import logging

from config.constants import TOOL_PATHS
from utils import ipc
from utils.tool_registry import tool_registry
from tools.hcxtool import hcxtool

####################################################
##### ensure you import each tools module here #####
##### e.g. (from tools.hcxtool import hcxtool) #####
##### they load via tool_registry / decorators #####
####################################################


logging.basicConfig(level=logging.DEBUG)

def draw_menu(stdscr, title, menu_items):
    h, w = stdscr.getmaxyx()
    box_height = len(menu_items) + 4
    box_width = max(len(title), *(len(item) for item in menu_items)) + 4
    start_y = (h - box_height) // 2
    start_x = (w - box_width) // 2
    win = curses.newwin(box_height, box_width, start_y, start_x)
    win.keypad(True)
    win.box()
    win.addstr(1, (box_width - len(title)) // 2, title, curses.A_BOLD)
    for idx, item in enumerate(menu_items):
        win.addstr(2 + idx, 2, item)
    win.refresh()
    stdscr.refresh()


def exit_menu(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    menu_items = ["[1] Detach", "[2] Kill", "[0] Back"]
    title = "Exit Menu"
    draw_menu(stdscr, title, menu_items)
    while True:
        key = stdscr.getch()
        try:
            ch = chr(key)
        except Exception:
            continue
        if ch == "1":
            # Send detach command via IPC.
            message = {"action": "DETACH_UI"}
            response = ipc.send_ipc_command(message)
            stdscr.clear()
            stdscr.addstr(0, 0, "Detach command sent. Detaching UI...")
            stdscr.refresh()
            curses.napms(1500)
            # Exit the UI after detach.
            exit(0)
        elif ch == "2":
            # Send kill command via IPC.
            message = {"action": "KILL_UI"}
            response = ipc.send_ipc_command(message)
            stdscr.clear()
            stdscr.addstr(0, 0, "Kill command sent. Killing UI...")
            stdscr.refresh()
            curses.napms(1500)
            # Exit the UI after kill.
            exit(0)
        elif ch == "0" or key == 27:
            # Return to main menu.
            break


def tools_menu(stdscr):
    curses.curs_set(0)
    tool_names = tool_registry.get_tool_names()
    if not tool_names:
        tool_names = ["No tools registered"]
    # Build menu: number tools 1..n, and add "[0] Back" as the last option.
    menu_items = [f"[{idx}] {name}" for idx, name in enumerate(tool_names, start=1)]
    menu_items.append("[0] Back")
    title = "Tools Menu"
    stdscr.clear()
    stdscr.refresh()
    draw_menu(stdscr, title, menu_items)

    while True:
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
            continue
        try:
            char = chr(key)
        except Exception:
            continue
        if char.isdigit():
            if char == "0":
                break
            else:
                num = int(char)
                if 1 <= num <= len(tool_names):
                    selected_tool = tool_names[num - 1]
                    stdscr.clear()
                    stdscr.addstr(0, 0, f"Selected tool: {selected_tool}", curses.A_BOLD)
                    stdscr.refresh()
                    curses.napms(1500)
                    try:
                        tool_path = TOOL_PATHS.get(selected_tool)
                        if not tool_path:
                            raise ValueError(f"No base_dir defined for {selected_tool} in TOOL_PATHS")
                        tool_instance = tool_registry.instantiate_tool(selected_tool, base_dir=str(tool_path))
                        tool_instance.submenu(stdscr)
                        # After the tool submenu exits, clear the screen.
                        stdscr.clear()
                        stdscr.refresh()
                    except Exception as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Error launching tool {selected_tool}: {e}", curses.A_BOLD)
                        stdscr.refresh()
                        stdscr.getch()
                    break
        elif key == 27:
            break


def main_menu(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    stdscr.refresh()
    # Increase delay to allow tmux pane to settle.
    curses.napms(300)  # 300 milliseconds delay; adjust as needed.

    menu_items = ["[1] Tools", "[0] Exit"]
    title = "Main Menu"
    draw_menu(stdscr, title, menu_items)

    while True:
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
            continue
        try:
            char = chr(key)
        except Exception:
            continue
        if char == "1":
            tools_menu(stdscr)
            # After returning from a submenu, clear and redraw the main menu.
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)
        elif char == "0":
            exit_menu(stdscr)
            # After the exit menu, if the user chose Back, redraw the main menu.
            stdscr.clear()
            stdscr.refresh()
            draw_menu(stdscr, title, menu_items)


if __name__ == "__main__":
    curses.wrapper(main_menu)