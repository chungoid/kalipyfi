#!/usr/bin/env python3
import sys
from pathlib import Path
project_base = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_base))


def main():
    cwd = Path(__file__).resolve().parent
    ascii_path = cwd / "ascii.txt"

    try:
        with open(ascii_path, "r") as f:
            print(f.read())
    except Exception as e:
        print(f"Error reading ascii.txt: {e}")

if __name__ == "__main__":
    main()
