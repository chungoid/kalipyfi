import curses

class HcxToolSubmenu:
    def __init__(self, tool):
        self.tool = tool

    def display(self, stdscr):
        stdscr.clear()
        stdscr.addstr(0, 0, f"Hcxtool Submenu - {self.tool.name}")
        stdscr.addstr(1, 0, "1. Launch")
        stdscr.addstr(2, 0, "2. Launch")
        stdscr.addstr(3, 0, "3. Utils")
        stdscr.addstr(4, 0, "4. Upload")
        stdscr.addstr(5, 0, "5. Parse")
        stdscr.addstr(6, 0, "0. Back")
        stdscr.refresh()

