#!/bin/bash
clear

# Calculate project root by going up 4 directories from the location of this script.
project_root="$(dirname "$(dirname "$(dirname "$(dirname "$0")")")")"
cd "$project_root" || { echo "Failed to change directory to project root"; exit 1; }

# Assign and export PYTHONPATH from the project root.
PYTHONPATH="$(pwd)"
export PYTHONPATH

# Debug output: print project root and PYTHONPATH.
echo "Project Root: $project_root"
echo "PYTHONPATH: $PYTHONPATH"

# Execute the main_menu.py script, which is at utils/ui/main_menu.py relative to project root.
exec python utils/ui/main_menu.py

