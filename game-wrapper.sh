#!/bin/bash
echo "wrapper invoked $(date) args=$*" >> /tmp/wrapper-canary.log 2>&1
# Wrapper used as the Steam Launch Options target. Starts the Mantella
# backend, runs the actual launch command (passed as arguments), then
# cleans up the backend once the game/MO2 session exits.
export STEAM_COMPAT_DATA_PATH="/home/allan/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/4199706055"
/home/allan/Games/Mantella/start-mantella.sh
{
    echo "=== launch attempt $(date) ==="
    echo "args: $*"
    "$@"
    echo "exit code: $?"
} >> /home/allan/Games/Mantella/game-wrapper.log 2>&1
kill "$(cat /home/allan/Games/Mantella/mantella.pid 2>/dev/null)" 2>/dev/null
rm -f /home/allan/Games/Mantella/mantella.pid
