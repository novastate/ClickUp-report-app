#!/bin/bash
cd "$(dirname "$0")"

if [ -f .pid ]; then
    echo "App verkar redan köra (PID $(cat .pid)). Kör ./stop.sh först."
    exit 1
fi

# Skapa venv om den inte finns
if [ ! -d .venv ]; then
    echo "Skapar virtuell miljö..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Startar Sprint Reporter..."
nohup .venv/bin/python app.py > app.log 2>&1 &
echo $! > .pid
echo "Appen körs på http://localhost:8000 (PID $(cat .pid))"
echo "Loggar skrivs till app.log"
