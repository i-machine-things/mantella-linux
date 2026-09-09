#!/bin/bash
# Starts the Mantella backend in the background if it isn't already running.
# Uses a PID file rather than pgrep text-matching, since the launcher's own
# command line can contain this script's search text and cause false positives.
PIDFILE=/home/allan/Games/Mantella/mantella.pid

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    exit 0
fi

cd /home/allan/Games/Mantella
nohup ./MantellaEnv/bin/python main.py > /home/allan/Games/Mantella/mantella-run.log 2>&1 &
echo $! > "$PIDFILE"
disown
