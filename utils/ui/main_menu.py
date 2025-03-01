# menu.py
import curses

def curses_menu(stdscr):
    # Hide the cursor and clear the screen.
    curses.curs_set(0)
    stdscr.clear()

    menu_items = ["Option 1: Hello", "Option 2: Refresh", "Option 3: Exit"]
    current_row = 0

    def print_menu():
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        for idx, item in enumerate(menu_items):
            x = width // 2 - len(item) // 2
            y = height // 2 - len(menu_items) // 2 + idx
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(y, x, item)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(y, x, item)
        stdscr.refresh()

    print_menu()

    while True:
        key = stdscr.getch()
        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(menu_items) - 1:
            current_row += 1
        elif key in [curses.KEY_ENTER, 10, 13]:
            # For demonstration, if Exit is selected, break.
            if current_row == len(menu_items) - 1:
                break
            else:
                stdscr.addstr(0, 0, f"You selected {menu_items[current_row]}!")
                stdscr.refresh()
                curses.napms(1000)
        print_menu()

if __name__ == "__main__":
    curses.wrapper(curses_menu)
