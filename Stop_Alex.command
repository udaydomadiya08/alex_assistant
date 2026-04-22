#!/bin/bash
# 🛑 [ALEX STOP SCRIPT] - Complete Shutdown

echo "------------------------------------------------"
echo "  [ALEX] Shutting down all systems...           "
echo "------------------------------------------------"

# 1. Kill the main Python process GRACEFULLY first (15 = SIGTERM)
# This allows Alex to run her cleanup code and release the microphone.
echo ">> Requesting graceful shutdown (SIGTERM)..."
pkill -15 -f chatbot.py 2>/dev/null
sleep 1.0

# 2. Unload the service if it exists
launchctl unload ~/Library/LaunchAgents/com.alex.assistant.plist 2>/dev/null
launchctl stop com.alex.assistant 2>/dev/null
launchctl remove com.alex.assistant 2>/dev/null

# 3. Kill the shell recovery loops (Start_Alex scripts) - KILL is fine here
pkill -9 -f Start_Alex.command 2>/dev/null

# 4. Final cleanup: KILL anything still hanging
pkill -9 -f chatbot.py 2>/dev/null
pkill -9 afplay 2>/dev/null

echo "✅ Alex has been fully stopped."
echo "💡 The orange microphone dot should disappear now."
echo "------------------------------------------------"
sleep 2

