#!/usr/bin/env python3
import sys
from rich.console import Console
from rich.panel import Panel
import pyfiglet
from pathlib import Path
project_base = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_base))

def main():
    console = Console()

    kalipyfi_art = pyfiglet.figlet_format("kalipyfi", font="slant")
    kalipyfi_panel = Panel(kalipyfi_art, style="bold cyan")



    # Clear the terminal screen (optional)
    console.clear()

    # Print the panels.
    console.print(kalipyfi_panel)

if __name__ == "__main__":
    main()