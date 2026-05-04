#!/bin/bash
cd "$(dirname "$0")"

BUNDLE="deploy-bundle.zip"

# --- Verify bundle exists ---
if [ ! -f "$BUNDLE" ]; then
    echo "Hittar inte $BUNDLE i den här mappen."
    echo "Lägg zip-filen här först (drag-och-släpp från Downloads)."
    exit 1
fi

echo "=== Sprint Reporter: applying deploy ==="
echo ""

# --- Pre-deploy DB backup ---
if [ -f sprint_data.db ]; then
    BACKUP="sprint_data.db.before-deploy-$(date +%Y%m%d-%H%M%S)"
    cp sprint_data.db "$BACKUP"
    echo "DB-backup: $BACKUP"
fi

# --- Capture pre-unzip requirements.txt hash ---
OLD_REQ_HASH=""
if [ -f requirements.txt ]; then
    OLD_REQ_HASH=$(shasum requirements.txt | awk '{print $1}')
fi

# --- Stop the app ---
echo ""
echo "Stoppar appen..."
./stop.sh

# --- Unpack the bundle ---
echo ""
echo "Packar upp $BUNDLE..."
unzip -oq "$BUNDLE"

# --- Restore execute bits ---
chmod +x start.sh stop.sh apply-deploy.sh 2>/dev/null

# --- Conditional pip install ---
NEW_REQ_HASH=""
if [ -f requirements.txt ]; then
    NEW_REQ_HASH=$(shasum requirements.txt | awk '{print $1}')
fi
if [ "$OLD_REQ_HASH" != "$NEW_REQ_HASH" ]; then
    echo ""
    echo "requirements.txt har ändrats — installerar dependencies..."
    if [ -d .venv ]; then
        .venv/bin/pip install -r requirements.txt
    else
        echo "Ingen .venv — start.sh skapar en ny och installerar."
    fi
fi

# --- Start the app ---
echo ""
echo "Startar appen..."
./start.sh
START_EXIT=$?

echo ""
if [ "$START_EXIT" = "0" ]; then
    echo "=== Deploy klar ==="
else
    echo "=== Deploy klar, men start.sh misslyckades. Se app.log. ==="
    exit "$START_EXIT"
fi
