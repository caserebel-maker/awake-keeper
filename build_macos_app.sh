#!/bin/bash
set -e

APP_NAME="Awake Keeper"
APP_DIR="/Applications/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MAC_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "Creating macOS App Bundle structure..."
mkdir -p "$MAC_DIR"
mkdir -p "$RESOURCES_DIR"

# Copy Icon from Antigravity if it exists
if [ -f "/Applications/Antigravity.app/Contents/Resources/icon.icns" ]; then
    echo "Copying icon from Antigravity..."
    cp "/Applications/Antigravity.app/Contents/Resources/icon.icns" "$RESOURCES_DIR/icon.icns"
elif [ -f "/Applications/Codex.app/Contents/Resources/icon.icns" ]; then
    echo "Copying icon from Codex..."
    cp "/Applications/Codex.app/Contents/Resources/icon.icns" "$RESOURCES_DIR/icon.icns"
fi

# Write Info.plist
echo "Writing Info.plist..."
cat << EOF_PLIST > "$CONTENTS_DIR/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Awake Keeper</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.ebci.awakekeeper</string>
    <key>CFBundleName</key>
    <string>Awake Keeper</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.10</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF_PLIST

# Write executable launcher script
echo "Writing launcher script..."
cat << 'EOF2' > "$MAC_DIR/Awake Keeper"
#!/bin/bash

# Port checking helper
if /usr/sbin/lsof -i tcp:3010 -t >/dev/null; then
    echo "Awake Keeper is already running. Opening browser..."
    /usr/bin/open http://localhost:3010
else
    echo "Starting Awake Keeper server..."
    # Ensure local directory and script are synced
    mkdir -p ~/.gemini/antigravity
    cp /Volumes/C1TB/EB-CI/awake-keeper/awake_keeper.py ~/.gemini/antigravity/awake_keeper.py
    
    # Launch keeper script from local user directory in background to bypass TCC sandbox
    /usr/bin/python3 /Users/pondm1/.gemini/antigravity/awake_keeper.py > ~/.gemini/antigravity/awake_keeper_run.log 2>&1 &
    
    # Wait for startup and open browser
    sleep 1.5
    /usr/bin/open http://localhost:3010
fi
EOF2

chmod +x "$MAC_DIR/Awake Keeper"

echo "Success! Awake Keeper has been installed as a native app at: /Applications/Awake Keeper.app"
