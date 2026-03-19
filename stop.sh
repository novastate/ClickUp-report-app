#!/bin/bash
cd "$(dirname "$0")"

if [ ! -f .pid ]; then
    echo "Ingen app körs (ingen .pid-fil hittad)."
    exit 0
fi

PID=$(cat .pid)
if kill "$PID" 2>/dev/null; then
    echo "Stoppade appen (PID $PID)."
else
    echo "Processen (PID $PID) körde inte redan."
fi
rm -f .pid
