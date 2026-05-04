#!/bin/bash
cd "$(dirname "$0")"

# --- Read PORT from .env (fallback 8000) — same as start.sh ---
PORT=8000
if [ -f .env ]; then
    ENV_PORT=$(grep -E '^PORT=' .env | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
    if [ -n "$ENV_PORT" ]; then
        PORT=$ENV_PORT
    fi
fi

# --- Helper: wait until a PID dies, escalate to SIGKILL after timeout ---
wait_for_death() {
    local pid="$1"
    local attempts=10
    local i=0
    while [ "$i" -lt "$attempts" ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
        i=$((i + 1))
    done
    kill -9 "$pid" 2>/dev/null || true
    sleep 0.5
    return 1   # had to SIGKILL
}

KILLED_MAIN=""
ESCALATED_MAIN=0

# --- Step 1: handle .pid (supervisor process) ---
if [ -f .pid ]; then
    PID=$(cat .pid)
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        echo "Städade stale .pid (PID $PID körde inte)."
        rm -f .pid
    else
        kill "$PID"
        if wait_for_death "$PID"; then
            :
        else
            ESCALATED_MAIN=1
        fi
        rm -f .pid
        KILLED_MAIN="$PID"
    fi
fi

# --- Step 2: port backstop — catch orphan workers ---
ORPHAN_PIDS=$(lsof -ti:"$PORT" 2>/dev/null)
KILLED_ORPHANS=""
if [ -n "$ORPHAN_PIDS" ]; then
    # shellcheck disable=SC2086
    kill $ORPHAN_PIDS 2>/dev/null || true
    for pid in $ORPHAN_PIDS; do
        wait_for_death "$pid" >/dev/null
    done
    KILLED_ORPHANS=$(echo "$ORPHAN_PIDS" | tr '\n' ',' | sed 's/,$//')
fi

# --- Step 3: report ---
if [ -n "$KILLED_MAIN" ] && [ -n "$KILLED_ORPHANS" ]; then
    if [ "$ESCALATED_MAIN" = "1" ]; then
        echo "Stoppade Sprint Reporter med SIGKILL (PID $KILLED_MAIN). Städade även orphan(s) på port $PORT (PID $KILLED_ORPHANS)."
    else
        echo "Stoppade Sprint Reporter (PID $KILLED_MAIN). Städade även orphan(s) på port $PORT (PID $KILLED_ORPHANS)."
    fi
elif [ -n "$KILLED_MAIN" ]; then
    if [ "$ESCALATED_MAIN" = "1" ]; then
        echo "Stoppade Sprint Reporter med SIGKILL (PID $KILLED_MAIN)."
    else
        echo "Stoppade Sprint Reporter (PID $KILLED_MAIN)."
    fi
elif [ -n "$KILLED_ORPHANS" ]; then
    echo "Städade orphan-process(er) på port $PORT (PID $KILLED_ORPHANS)."
else
    echo "Sprint Reporter kör inte."
fi
