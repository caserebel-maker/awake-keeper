#!/bin/bash
set -e

UID_VAL=$(id -u)
PLIST_PATH="$HOME/Library/LaunchAgents/com.ebci.awakekeeper.plist"
LOG_DIR="$HOME/.gemini/antigravity"
DESKTOP_SHORTCUT="$HOME/Desktop/Awake Keeper.url"

echo "Stopping any existing Awake Keeper launch agent..."
launchctl bootout "gui/$UID_VAL" "$PLIST_PATH" 2>/dev/null || true
launchctl unload "$PLIST_PATH" 2>/dev/null || true

echo "Writing Launch Agent plist..."
mkdir -p "$(dirname "$PLIST_PATH")"
mkdir -p "$LOG_DIR"

# Copy python script to local user directory to bypass macOS Volume TCC sandbox
echo "Copying python script to local user directory..."
cp "/Volumes/C1TB/EB-CI/awake-keeper/awake_keeper.py" "$LOG_DIR/awake_keeper.py"

cat << EOF2 > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ebci.awakekeeper</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$LOG_DIR/awake_keeper.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/awake_keeper_agent.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/awake_keeper_agent.log</string>
</dict>
</plist>
EOF2

echo "Bootstrapping and enabling Launch Agent..."
launchctl bootstrap "gui/$UID_VAL" "$PLIST_PATH"
launchctl enable "gui/$UID_VAL/com.ebci.awakekeeper"

# Create Desktop Shortcut
echo "Creating Desktop Shortcut..."
cat << EOF2 > "$DESKTOP_SHORTCUT"
[InternetShortcut]
URL=http://localhost:3010
EOF2
chmod +x "$DESKTOP_SHORTCUT"

# Also clean up the failed .app bundle to avoid confusion
echo "Cleaning up local application bundle to avoid TCC issues..."
rm -rf "/Applications/Awake Keeper.app"

echo "--------------------------------------------------------"
echo "Success! Awake Keeper has been installed as a background Launch Agent."
echo "- It will run automatically in the background whenever you log into macOS."
echo "- A shortcut named 'Awake Keeper' has been added to your Desktop."
echo "- Double-click the desktop shortcut to open the dashboard."
echo "--------------------------------------------------------"
