#!/bin/bash
# 🛑 [ALEX STOP SCRIPT] - Complete Shutdown

echo "------------------------------------------------"
echo "  [ALEX] Shutting down all systems...           "
echo "------------------------------------------------"

# 1. Kill the LOOPS first so no restarts happen
# This stops Start_Alex.command from spawning a new chatbot.py while we are killing the old one.
echo ">> Stopping recovery loops..."
pkill -9 -f Start_Alex.command 2>/dev/null

# 2. Unload the service if it exists
if [ -f "$HOME/Library/LaunchAgents/com.alex.assistant.plist" ]; then
    echo ">> Unloading background service..."
    launchctl unload ~/Library/LaunchAgents/com.alex.assistant.plist 2>/dev/null
    launchctl stop com.alex.assistant 2>/dev/null
    launchctl remove com.alex.assistant 2>/dev/null
fi

# 3. Kill the main Python process GRACEFULLY first (15 = SIGTERM)
# This allows Alex to run her cleanup code and release the microphone.
echo ">> Requesting graceful hardware release (SIGTERM)..."
pkill -15 -f chatbot.py 2>/dev/null
sleep 1.2

# 4. Final cleanup: KILL anything still hanging
pkill -9 -f chatbot.py 2>/dev/null
pkill -9 afplay 2>/dev/null

echo "✅ [STOPPED] Alex is offline and microphone is released."
echo "------------------------------------------------"
sleep 2

