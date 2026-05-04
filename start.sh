#!/bin/bash
cd "$(dirname "$0")"

# --- Read PORT from .env (fallback 8000) ---
PORT=8000
if [ -f .env ]; then
    ENV_PORT=$(grep -E '^PORT=' .env | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
    if [ -n "$ENV_PORT" ]; then
        PORT=$ENV_PORT
    fi
fi
URL="http://localhost:$PORT"

# --- Already running? ---
if [ -f .pid ]; then
    PID=$(cat .pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Sprint Reporter kör redan på $URL (PID $PID). Loggar: app.log"
        exit 0
    else
        echo "Städade stale .pid (PID $PID körde inte)."
        rm -f .pid
    fi
fi

# --- Port sanity check ---
LISTENER=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -n +2 | head -n1)
if [ -n "$LISTENER" ]; then
    echo "Något annat lyssnar redan på port $PORT:"
    echo "  $LISTENER"
    echo "Avbryter start. Stoppa den processen eller ändra PORT i .env."
    exit 1
fi

# --- Create venv if missing ---
if [ ! -d .venv ]; then
    echo "Skapar virtuell miljö..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# --- Start the app ---
echo "Startar Sprint Reporter..."
nohup .venv/bin/python app.py > app.log 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > .pid

# --- Wait up to ~5s for /health to return 200 ---
ATTEMPTS=10
i=0
while [ "$i" -lt "$ATTEMPTS" ]; do
    if curl -s -f -o /dev/null "$URL/health"; then
        echo "Sprint Reporter körs på $URL (PID $NEW_PID). Loggar: app.log"
        exit 0
    fi
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        break
    fi
    sleep 0.5
    i=$((i + 1))
done

echo "Appen startade inte inom 5 sekunder. Senaste loggrader:"
tail -n 20 app.log
exit 1
