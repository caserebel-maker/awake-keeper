# Awake Keeper

A background keeper utility for macOS to automatically prevent rate-limit resets from timing out on Antigravity and Codex.

## Features
- **Zero-Dependency Python Server**: Serves a beautiful glassmorphic dark-mode control dashboard on port `3010`.
- **Flexible Modes**:
  - **Countdown Mode**: Sets a simple relative timer (e.g. 5 hours).
  - **Specific Time Mode**: Schedules triggers to fire exactly at a specific local clock time (e.g., 03:00 AM).
- **Auto-Looping**: Automatically schedules the next trigger 5 hours later once a trigger fires.
- **Mac Native App wrapper** (`Awake Keeper.app`) with custom icon.
- **Auto-launch on login** via a macOS Launch Agent.

## Setup & Installation

1. Clone this repository to your Mac:
   ```bash
   git clone https://github.com/caserebel-maker/awake-keeper.git
   cd awake-keeper
   ```

2. Run the Launch Agent installer. This will install the program locally, configure it to run in the background on startup, and add a double-clickable shortcut to your Desktop:
   ```bash
   bash install_launch_agent.sh
   ```

3. To build the native `/Applications/Awake Keeper.app` bundle:
   ```bash
   bash build_macos_app.sh
   ```

## Usage
- Open the dashboard by double-clicking the **Awake Keeper** shortcut on your Desktop.
- Set the target clock time or countdown duration.
- The background thread will automatically keep the agents active when the time is reached!
