import os
import sys

# 📂 [SETUP SERVICE] - Makes Alex portable by auto-linking paths
def setup_background_service():
    # 1. Get current absolute path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plist_template_path = os.path.join(current_dir, "com.alex.assistant.plist")
    target_plist_path = os.path.expanduser("~/Library/LaunchAgents/com.alex.assistant.plist")
    
    python_path = sys.executable # Path to the current virtualenv's python
    script_path = os.path.join(current_dir, "chatbot.py")
    log_path = os.path.join(current_dir, "alex_bg.log")

    print(f"🔧 [SETUP] Registering Alex at: {current_dir}")

    # 2. Basic plist content with dynamic paths
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.alex.assistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{current_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""

    # 3. Write to LaunchAgents
    try:
        with open(target_plist_path, "w") as f:
            f.write(plist_content)
        print(f"✅ [SUCCESS] LaunchAgent installed at {target_plist_path}")
    except Exception as e:
        print(f"❌ [ERROR] Could not write plist: {e}")

if __name__ == "__main__":
    setup_background_service()
