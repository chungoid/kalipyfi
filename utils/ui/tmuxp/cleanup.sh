#!/bin/bash
# cleanup.sh

# nuke
if [ -f /tmp/kalipyfi.pid ]; then
    MAIN_PID=$(cat /tmp/kalipyfi.pid)
    MENU_PID=$(cat /tmp/kalipyfi.pid)
    echo "Killing main process group for PID: $MAIN_PID"
    tmux kill-session
    kill -TERM -"$MAIN_PID"
    kill -TERM -"$MENU_PID"
    tmux kill-session
else
    echo "No PID file found. You may need to manually kill the main process."
fi

echo "Cleanup complete."
