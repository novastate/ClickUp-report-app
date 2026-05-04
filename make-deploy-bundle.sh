#!/bin/bash
cd "$(dirname "$0")"

BUNDLE="deploy-bundle.zip"

# --- Git-state warning (informational, non-blocking) ---
if [ -d .git ]; then
    DIRTY=$(git status --porcelain 2>/dev/null)
    if [ -n "$DIRTY" ]; then
        echo "⚠️  Varning: arbetskatalogen har ouncommittade ändringar."
        echo "   Bundlen kommer att inkludera dessa, men de finns inte på GitHub."
        echo ""
    fi
    LAST_COMMIT=$(git log -1 --oneline 2>/dev/null)
    if [ -n "$LAST_COMMIT" ]; then
        echo "Senaste commit: $LAST_COMMIT"
    fi
fi

# --- Remove any previous bundle ---
rm -f "$BUNDLE"

# --- Build the bundle ---
echo "Bygger $BUNDLE..."
zip -rq "$BUNDLE" \
    src \
    templates \
    static \
    app.py \
    requirements.txt \
    start.sh \
    stop.sh \
    apply-deploy.sh \
    clickup-api-discovery.md \
    docs/features.md \
    .env.example \
    -x "*/__pycache__/*" \
       "*/.pytest_cache/*" \
       "*.pyc" \
       "*/.DS_Store" \
       ".DS_Store"

# --- Print result ---
SIZE=$(du -h "$BUNDLE" | awk '{print $1}')
COUNT=$(unzip -l "$BUNDLE" | tail -n1 | awk '{print $2}')
echo ""
echo "Bundle klar: $BUNDLE ($SIZE, $COUNT filer)"
echo ""
echo "Nästa steg:"
echo "  1. AirDrop $BUNDLE till live-Macen."
echo "  2. På live: flytta filen till projektmappen och kör ./apply-deploy.sh"
