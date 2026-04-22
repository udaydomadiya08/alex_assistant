#!/bin/bash
# Clear screen and navigate to project folder dynamically
clear
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 🛡️ [PORTABILITY] Auto-register the background service to this location
echo "🔧 [SETUP] Linking Alex to this location..."
./.venv/bin/python3 setup_service.py

# Prevent duplicates: Kill any old versions before starting
pkill -9 -f chatbot.py 2>/dev/null

# Visual header
echo "------------------------------------------------"
echo "  [ALEX 24/7] Launching Bulletproof Mode...     "
echo "  Location: $DIR"
echo "------------------------------------------------"

# 🛡️ [SHELL RECOVERY LOOP]
# Even if Python crashes, this loop will restart it in 5 seconds
while true; do
    echo "[$(date +%T)] Starting Assistant..."
    PYTHONUNBUFFERED=1 ./.venv/bin/python3 chatbot.py 2>&1 | tee alex_debug.log
    
    echo "🔥 [CRITICAL] Alex process terminated. Relaunching in 5s..."
    pkill -9 -f chatbot.py 2>/dev/null
    sleep 5
done
