#!/bin/bash
clear
if [ -n "$LOG_FILE" ]; then
    exec tail -f "$LOG_FILE"
else
    echo "LOG_FILE not set; falling back to relative path."
    exec tail -f "$(dirname "$0")/../../logs/kalipifi.log"
fi
