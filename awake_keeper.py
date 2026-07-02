#!/usr/bin/env python3
import os
import sys
import time
import json
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import webbrowser

# Shared application state
STATE_FILE = os.path.expanduser("~/.gemini/antigravity/awake_keeper_state.json")
LOCK = threading.Lock()

DEFAULT_STATE = {
    "antigravity": {
        "timer": 18000,      # default 5 hours in seconds
        "duration": 18000,
        "trigger": "gui",
        "enabled": True,
        "mode": "duration",         # "duration" or "specific"
        "specific_time": "03:00",   # "HH:MM"
        "last_trigger": None,
        "last_status": "Idle"
    },
    "codex": {
        "timer": 18000,
        "duration": 18000,
        "trigger": "cli",
        "enabled": True,
        "mode": "duration",         # "duration" or "specific"
        "specific_time": "03:00",   # "HH:MM"
        "last_trigger": None,
        "last_status": "Idle"
    },
    "prompt_template": "ช่วยสรุปสั้นๆ หน่อยว่า commit ล่าสุด '{commit_message}' แก้ไขอะไรบ้าง",
    "logs": []
}

STATE = DEFAULT_STATE.copy()

def load_state():
    global STATE
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                # Merge saved state into default state to maintain schema
                for key in DEFAULT_STATE:
                    if key in saved:
                        if isinstance(DEFAULT_STATE[key], dict):
                            STATE[key].update(saved[key])
                        else:
                            STATE[key] = saved[key]
    except Exception as e:
        print(f"Error loading state: {e}")

def save_state():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(STATE, f, indent=2)
    except Exception as e:
        print(f"Error saving state: {e}")

def add_log(message, success=True, level="INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "time": timestamp,
        "message": message,
        "success": success,
        "level": level
    }
    STATE["logs"].insert(0, log_entry)
    # Keep only the last 100 logs
    STATE["logs"] = STATE["logs"][:100]
    save_state()

def get_latest_commit_message():
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s"],
            capture_output=True,
            text=True,
            check=True,
            cwd="/Volumes/C1TB/EB-CI/EBCI-Nexus"
        )
        return res.stdout.strip()
    except Exception as e:
        return "development updates and optimization"

def run_applescript(script_content):
    try:
        res = subprocess.run(
            ["osascript", "-e", script_content],
            capture_output=True,
            text=True,
            check=True
        )
        return True, res.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def trigger_antigravity(prompt):
    escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''
    set the clipboard to "{escaped_prompt}"
    tell application "System Events"
        if exists process "Antigravity" then
            tell application "Antigravity" to activate
            delay 1.5
            keystroke "v" using {{command down}}
            delay 0.5
            key code 36
            return "SUCCESS"
        else
            error "Antigravity app is not running"
        end if
    end tell
    '''
    return run_applescript(script)

def trigger_codex_gui(prompt):
    escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''
    set the clipboard to "{escaped_prompt}"
    tell application "System Events"
        if exists process "Codex" then
            tell application "Codex" to activate
            delay 1.5
            keystroke "v" using {{command down}}
            delay 0.5
            key code 36
            return "SUCCESS"
        else
            error "Codex app is not running"
        end if
    end tell
    '''
    return run_applescript(script)

def trigger_codex_cli(prompt):
    try:
        cli_path = "/Applications/Codex.app/Contents/Resources/codex"
        if not os.path.exists(cli_path):
            return False, f"Codex CLI not found at {cli_path}"
        
        cmd = [cli_path, "exec", "--skip-git-repo-check", "--ephemeral", prompt]
        res = subprocess.run(
            cmd,
            input="",
            capture_output=True,
            text=True,
            timeout=60,
            cwd="/Volumes/C1TB/EB-CI/EBCI-Nexus"
        )
        if res.returncode == 0:
            return True, "Executed via CLI successfully"
        else:
            return False, res.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "Codex CLI timeout after 60s"
    except Exception as e:
        return False, str(e)

def perform_trigger(target):
    with LOCK:
        commit_msg = get_latest_commit_message()
        prompt = STATE["prompt_template"].replace("{commit_message}", commit_msg)
        
        results = []
        if target in ["antigravity", "both"]:
            if STATE["antigravity"]["enabled"]:
                STATE["antigravity"]["last_status"] = "Triggering..."
                success, output = trigger_antigravity(prompt)
                STATE["antigravity"]["last_trigger"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if success:
                    STATE["antigravity"]["last_status"] = "Success"
                    add_log(f"Antigravity triggered successfully using commit prompt: '{commit_msg}'", True, "SUCCESS")
                else:
                    STATE["antigravity"]["last_status"] = f"Failed: {output}"
                    add_log(f"Failed to trigger Antigravity: {output}", False, "ERROR")
                results.append(("antigravity", success, output))
            else:
                results.append(("antigravity", False, "Disabled"))

        if target in ["codex", "both"]:
            if STATE["codex"]["enabled"]:
                STATE["codex"]["last_status"] = "Triggering..."
                success, output = trigger_codex_gui(prompt)
                
                STATE["codex"]["last_trigger"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if success:
                    STATE["codex"]["last_status"] = "Success"
                    add_log(f"Codex triggered successfully using commit prompt: '{commit_msg}'", True, "SUCCESS")
                else:
                    STATE["codex"]["last_status"] = f"Failed: {output}"
                    add_log(f"Failed to trigger Codex: {output}", False, "ERROR")
                results.append(("codex", success, output))
            else:
                results.append(("codex", False, "Disabled"))
                
        save_state()
        return results

def add_hours_to_time_str(time_str, hours_to_add=5):
    try:
        parts = time_str.split(":")
        h = int(parts[0])
        m = int(parts[1])
        new_h = (h + hours_to_add) % 24
        return f"{new_h:02d}:{m:02d}"
    except Exception:
        return time_str

def get_seconds_until_time(target_time_str):
    try:
        parts = target_time_str.split(":")
        target_h = int(parts[0])
        target_m = int(parts[1])
        
        now = time.localtime()
        target_struct = time.struct_time((
            now.tm_year, now.tm_mon, now.tm_mday,
            target_h, target_m, 0,
            now.tm_wday, now.tm_yday, now.tm_isdst
        ))
        
        target_epoch = time.mktime(target_struct)
        now_epoch = time.time()
        
        if target_epoch <= now_epoch:
            # It's past this time today, so it refers to tomorrow
            target_epoch += 86400
            
        return int(target_epoch - now_epoch)
    except Exception as e:
        print(f"Error calculating seconds: {e}")
        return 0

# Background scheduler thread
def scheduler_loop():
    while True:
        time.sleep(1)
        with LOCK:
            now_time = time.strftime("%H:%M:%S")
            
            # Handle Antigravity countdown/specific time
            if STATE["antigravity"]["enabled"]:
                if STATE["antigravity"].get("mode", "duration") == "specific":
                    # Update timer dynamically for UI countdown
                    spec_t = STATE["antigravity"].get("specific_time", "03:00")
                    STATE["antigravity"]["timer"] = get_seconds_until_time(spec_t)
                    # Trigger exactly at the target HH:MM:00
                    if now_time == spec_t + ":00":
                        threading.Thread(target=perform_trigger, args=("antigravity",)).start()
                        # Auto-shift to next 5h cycle
                        next_t = add_hours_to_time_str(spec_t, 5)
                        STATE["antigravity"]["specific_time"] = next_t
                        add_log(f"Antigravity triggered. Next target auto-scheduled for {next_t}", True, "INFO")
                else:
                    # Duration mode (standard countdown)
                    if STATE["antigravity"]["timer"] > 0:
                        STATE["antigravity"]["timer"] -= 1
                    else:
                        threading.Thread(target=perform_trigger, args=("antigravity",)).start()
                        STATE["antigravity"]["timer"] = STATE["antigravity"]["duration"]
            
            # Handle Codex countdown/specific time
            if STATE["codex"]["enabled"]:
                if STATE["codex"].get("mode", "duration") == "specific":
                    # Update timer dynamically for UI countdown
                    spec_t = STATE["codex"].get("specific_time", "03:00")
                    STATE["codex"]["timer"] = get_seconds_until_time(spec_t)
                    # Trigger exactly at the target HH:MM:00
                    if now_time == spec_t + ":00":
                        threading.Thread(target=perform_trigger, args=("codex",)).start()
                        # Auto-shift to next 5h cycle
                        next_t = add_hours_to_time_str(spec_t, 5)
                        STATE["codex"]["specific_time"] = next_t
                        add_log(f"Codex triggered. Next target auto-scheduled for {next_t}", True, "INFO")
                else:
                    # Duration mode (standard countdown)
                    if STATE["codex"]["timer"] > 0:
                        STATE["codex"]["timer"] -= 1
                    else:
                        threading.Thread(target=perform_trigger, args=("codex",)).start()
                        STATE["codex"]["timer"] = STATE["codex"]["duration"]
            
            # Periodically save state (every 10 seconds or when values change)
            if int(time.time()) % 10 == 0:
                save_state()

# Embedded Single-Page App HTML
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>💫 Awake Keeper Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-glow-1: #0d1b2a;
            --bg-glow-2: #02050f;
            --card-bg: rgba(17, 25, 40, 0.85);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8f9fa;
            --text-secondary: #adb5bd;
            
            --color-antigravity: #00f2fe;
            --color-antigravity-dark: #4facfe;
            --color-codex: #a77bf9;
            --color-codex-dark: #fa423e;
            
            --glow-antigravity: 0 0 20px rgba(0, 242, 254, 0.4);
            --glow-codex: 0 0 20px rgba(167, 123, 249, 0.4);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at center, var(--bg-glow-1) 0%, var(--bg-glow-2) 100%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1rem;
            overflow-x: hidden;
        }

        header {
            text-align: center;
            margin-bottom: 2.5rem;
            animation: fadeInDown 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        h1 {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 30%, #a77bf9 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.8rem;
        }

        header p {
            color: var(--text-secondary);
            font-size: 1.1rem;
            font-weight: 300;
        }

        .dashboard {
            width: 100%;
            max-width: 1100px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 2rem;
            margin-bottom: 2rem;
            animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--card-border);
            border-radius: 28px;
            padding: 2.2rem;
            position: relative;
            overflow: hidden;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
        }

        .card.antigravity::before {
            background: linear-gradient(90deg, var(--color-antigravity), var(--color-antigravity-dark));
        }

        .card.codex::before {
            background: linear-gradient(90deg, var(--color-codex), var(--color-codex-dark));
        }

        .card:hover {
            transform: translateY(-8px);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .card.antigravity:hover {
            box-shadow: 0 20px 40px rgba(0, 242, 254, 0.1), 0 0 1px 1px rgba(0, 242, 254, 0.2);
        }

        .card.codex:hover {
            box-shadow: 0 20px 40px rgba(167, 123, 249, 0.1), 0 0 1px 1px rgba(167, 123, 249, 0.2);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.8rem;
        }

        .card-title {
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: -0.3px;
        }

        .switch-container {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 46px;
            height: 24px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #2c3e50;
            transition: .4s;
            border-radius: 34px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }

        input:checked + .slider {
            background-color: #2ecc71;
        }

        .card.antigravity input:checked + .slider {
            background-color: var(--color-antigravity-dark);
            box-shadow: 0 0 10px rgba(79, 254, 254, 0.4);
        }

        .card.codex input:checked + .slider {
            background-color: var(--color-codex);
            box-shadow: 0 0 10px rgba(167, 123, 249, 0.4);
        }

        input:checked + .slider:before {
            transform: translateX(22px);
        }

        .timer-display {
            text-align: center;
            margin-bottom: 2rem;
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }

        .time-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 3.4rem;
            font-weight: 700;
            letter-spacing: -1px;
            margin-bottom: 0.2rem;
        }

        .antigravity .time-value {
            color: var(--color-antigravity);
            text-shadow: var(--glow-antigravity);
        }

        .codex .time-value {
            color: var(--color-codex);
            text-shadow: var(--glow-codex);
        }

        .progress-bar-container {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 1.5rem;
        }

        .progress-bar {
            height: 100%;
            width: 0%;
            transition: width 1s linear;
        }

        .antigravity .progress-bar {
            background: linear-gradient(90deg, var(--color-antigravity), var(--color-antigravity-dark));
            box-shadow: var(--glow-antigravity);
        }

        .codex .progress-bar {
            background: linear-gradient(90deg, var(--color-codex), var(--color-codex-dark));
            box-shadow: var(--glow-codex);
        }

        .controls-group {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 18px;
            padding: 1.2rem;
            margin-bottom: 1.5rem;
        }

        .control-label {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 0.6rem;
            display: block;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .method-selector {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }

        .method-btn {
            flex: 1;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            color: var(--text-secondary);
            padding: 0.6rem;
            font-size: 0.9rem;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.3s;
        }

        .method-btn.active {
            color: #fff;
        }

        .antigravity .method-btn.active {
            background: rgba(0, 242, 254, 0.15);
            border-color: var(--color-antigravity);
            box-shadow: var(--glow-antigravity);
        }

        .codex .method-btn.active {
            background: rgba(167, 123, 249, 0.15);
            border-color: var(--color-codex);
            box-shadow: var(--glow-codex);
        }

        .input-row {
            display: flex;
            gap: 0.8rem;
        }

        .num-input-wrapper {
            flex: 1;
        }

        .num-input-wrapper label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            display: block;
            margin-bottom: 0.3rem;
        }

        .text-input, .num-input {
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: #fff;
            padding: 0.6rem 0.8rem;
            font-family: inherit;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.3s;
        }

        .text-input:focus, .num-input:focus {
            border-color: rgba(255, 255, 255, 0.3);
        }

        .btn-set {
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 10px;
            color: #fff;
            padding: 0 1rem;
            font-family: inherit;
            cursor: pointer;
            transition: background 0.3s;
            font-weight: 600;
        }

        .btn-set:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        .action-btns {
            display: flex;
            gap: 1rem;
        }

        .btn-trigger {
            flex: 1;
            border: none;
            border-radius: 14px;
            color: #fff;
            padding: 0.9rem 1.2rem;
            font-size: 1rem;
            font-weight: 600;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .antigravity .btn-trigger {
            background: linear-gradient(135deg, var(--color-antigravity), var(--color-antigravity-dark));
            box-shadow: var(--glow-antigravity);
        }

        .codex .btn-trigger {
            background: linear-gradient(135deg, var(--color-codex), var(--color-codex-dark));
            box-shadow: var(--glow-codex);
        }

        .btn-trigger:hover {
            filter: brightness(1.15);
            transform: scale(1.02);
        }

        .btn-trigger:active {
            transform: scale(0.98);
        }

        .logs-section {
            width: 100%;
            max-width: 1100px;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--card-border);
            border-radius: 28px;
            padding: 2.2rem;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
            animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.2s both;
        }

        .logs-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }

        .logs-title {
            font-size: 1.4rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }

        .prompt-template-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 1.2rem;
            margin-bottom: 1.5rem;
        }

        .logs-container {
            max-height: 300px;
            overflow-y: auto;
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.04);
            padding: 1rem;
        }

        .log-entry {
            display: flex;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            align-items: flex-start;
        }

        .log-entry:last-child {
            border-bottom: none;
        }

        .log-time {
            color: var(--text-secondary);
            margin-right: 1rem;
            flex-shrink: 0;
        }

        .log-level {
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.75rem;
            margin-right: 0.8rem;
            text-transform: uppercase;
            flex-shrink: 0;
        }

        .level-success {
            background: rgba(46, 204, 113, 0.15);
            color: #2ecc71;
            border: 1px solid rgba(46, 204, 113, 0.3);
        }

        .level-error {
            background: rgba(231, 76, 60, 0.15);
            color: #e74c3c;
            border: 1px solid rgba(231, 76, 60, 0.3);
        }

        .level-info {
            background: rgba(52, 152, 219, 0.15);
            color: #3498db;
            border: 1px solid rgba(52, 152, 219, 0.3);
        }

        .log-msg {
            color: var(--text-primary);
            word-break: break-word;
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.1);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        @keyframes fadeInDown {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>💫 Awake Keeper</h1>
        <p>Keep your coding agents refreshed and ready to use</p>
    </header>

    <main class="dashboard">
        <!-- ANTIGRAVITY CARD -->
        <section class="card antigravity">
            <div class="card-header">
                <h2 class="card-title">Antigravity</h2>
                <div class="switch-container">
                    <span style="font-size: 0.85rem; color: var(--text-secondary);">Active</span>
                    <label class="switch">
                        <input type="checkbox" id="ag-enabled" onchange="updateSettings('antigravity')">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            
            <div class="timer-display">
                <div class="time-value" id="ag-time">00:00:00</div>
                <div style="font-size: 0.85rem; color: var(--text-secondary);" id="ag-status">Status: Idle</div>
                <div id="ag-target-time-label" style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.2rem; display: none;">Target Time: <span id="ag-target-time" style="color: var(--color-antigravity); font-weight: 600;">03:00</span></div>
            </div>

            <div class="progress-bar-container">
                <div class="progress-bar" id="ag-progress"></div>
            </div>

            <div class="controls-group">
                <label class="control-label">Trigger Method</label>
                <div class="method-selector">
                    <button class="method-btn active" id="ag-method-gui">AppleScript GUI</button>
                </div>

                <label class="control-label">Timer Mode</label>
                <div class="method-selector">
                    <button class="method-btn" id="ag-mode-duration" onclick="setTimerMode('antigravity', 'duration')">Countdown</button>
                    <button class="method-btn" id="ag-mode-specific" onclick="setTimerMode('antigravity', 'specific')">Specific Time</button>
                </div>

                <div id="ag-duration-section" style="display: none;">
                    <label class="control-label">Quick Set Countdown</label>
                    <div class="input-row">
                        <div class="num-input-wrapper">
                            <label>Hours</label>
                            <input type="number" class="num-input" id="ag-set-hours" min="0" max="23" value="5">
                        </div>
                        <div class="num-input-wrapper">
                            <label>Mins</label>
                            <input type="number" class="num-input" id="ag-set-mins" min="0" max="59" value="0">
                        </div>
                        <button class="btn-set" onclick="setTimer('antigravity')">Set</button>
                    </div>
                </div>

                <div id="ag-specific-section" style="display: none;">
                    <label class="control-label">Specific Clock Time</label>
                    <div class="input-row">
                        <input type="time" class="text-input" id="ag-set-specific" value="03:00">
                        <button class="btn-set" onclick="add5Hours('antigravity')" style="background: rgba(255, 255, 255, 0.05); margin-right: 0.5rem;">+5h</button>
                        <button class="btn-set" onclick="saveSpecificTime('antigravity')">Save</button>
                    </div>
                </div>
            </div>

            <button class="btn-trigger" onclick="triggerNow('antigravity')">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
                Trigger Now
            </button>
        </section>

        <!-- CODEX CARD -->
        <section class="card codex">
            <div class="card-header">
                <h2 class="card-title">Codex</h2>
                <div class="switch-container">
                    <span style="font-size: 0.85rem; color: var(--text-secondary);">Active</span>
                    <label class="switch">
                        <input type="checkbox" id="cx-enabled" onchange="updateSettings('codex')">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>

            <div class="timer-display">
                <div class="time-value" id="cx-time">00:00:00</div>
                <div style="font-size: 0.85rem; color: var(--text-secondary);" id="cx-status">Status: Idle</div>
                <div id="cx-target-time-label" style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.2rem; display: none;">Target Time: <span id="cx-target-time" style="color: var(--color-codex); font-weight: 600;">03:00</span></div>
            </div>

            <div class="progress-bar-container">
                <div class="progress-bar" id="cx-progress"></div>
            </div>

            <div class="controls-group">
                <label class="control-label">Trigger Method</label>
                <div class="method-selector">
                    <button class="method-btn active" id="cx-method-gui">AppleScript GUI</button>
                </div>

                <label class="control-label">Timer Mode</label>
                <div class="method-selector">
                    <button class="method-btn" id="cx-mode-duration" onclick="setTimerMode('codex', 'duration')">Countdown</button>
                    <button class="method-btn" id="cx-mode-specific" onclick="setTimerMode('codex', 'specific')">Specific Time</button>
                </div>

                <div id="cx-duration-section" style="display: none;">
                    <label class="control-label">Quick Set Countdown</label>
                    <div class="input-row">
                        <div class="num-input-wrapper">
                            <label>Hours</label>
                            <input type="number" class="num-input" id="cx-set-hours" min="0" max="23" value="5">
                        </div>
                        <div class="num-input-wrapper">
                            <label>Mins</label>
                            <input type="number" class="num-input" id="cx-set-mins" min="0" max="59" value="0">
                        </div>
                        <button class="btn-set" onclick="setTimer('codex')">Set</button>
                    </div>
                </div>

                <div id="cx-specific-section" style="display: none;">
                    <label class="control-label">Specific Clock Time</label>
                    <div class="input-row">
                        <input type="time" class="text-input" id="cx-set-specific" value="03:00">
                        <button class="btn-set" onclick="add5Hours('codex')" style="background: rgba(255, 255, 255, 0.05); margin-right: 0.5rem;">+5h</button>
                        <button class="btn-set" onclick="saveSpecificTime('codex')">Save</button>
                    </div>
                </div>
            </div>

            <button class="btn-trigger" onclick="triggerNow('codex')">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
                Trigger Now
            </button>
        </section>
    </main>

    <!-- LOGS & CONFIG SECTION -->
    <section class="logs-section">
        <div class="prompt-template-card">
            <label class="control-label" style="margin-bottom: 0.8rem;">Prompt Template (Auto-resolves {commit_message})</label>
            <div class="input-row">
                <input type="text" class="text-input" id="prompt-template-input" placeholder="Enter prompt template...">
                <button class="btn-set" onclick="updatePromptTemplate()">Save Template</button>
            </div>
        </div>

        <div class="logs-header">
            <h2 class="logs-title">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M3 20v-8a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v8"/><path d="M3 12V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v6"/><path d="M13 20v-4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4"/><path d="M13 14V9a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v5"/></svg>
                Activity Log
            </h2>
        </div>
        <div class="logs-container" id="logs-list">
            <!-- Logs populated dynamically -->
        </div>
    </section>

    <script>
        function formatTime(seconds) {
            const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
            const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
            const s = (seconds % 60).toString().padStart(2, '0');
            return `${h}:${m}:${s}`;
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                // Update Antigravity
                document.getElementById('ag-time').innerText = formatTime(data.antigravity.timer);
                document.getElementById('ag-status').innerText = `Status: ${data.antigravity.last_status}`;
                document.getElementById('ag-enabled').checked = data.antigravity.enabled;
                const agPercent = (data.antigravity.timer / data.antigravity.duration) * 100;
                document.getElementById('ag-progress').style.width = `${100 - agPercent}%`;

                // Update Antigravity Mode UI
                const agMode = data.antigravity.mode || 'duration';
                if (agMode === 'duration') {
                    document.getElementById('ag-mode-duration').classList.add('active');
                    document.getElementById('ag-mode-specific').classList.remove('active');
                    document.getElementById('ag-duration-section').style.display = 'block';
                    document.getElementById('ag-specific-section').style.display = 'none';
                    document.getElementById('ag-target-time-label').style.display = 'none';
                } else {
                    document.getElementById('ag-mode-specific').classList.add('active');
                    document.getElementById('ag-mode-duration').classList.remove('active');
                    document.getElementById('ag-duration-section').style.display = 'none';
                    document.getElementById('ag-specific-section').style.display = 'block';
                    document.getElementById('ag-target-time-label').style.display = 'block';
                    document.getElementById('ag-target-time').innerText = data.antigravity.specific_time || '03:00';
                }
                if (document.activeElement !== document.getElementById('ag-set-specific')) {
                    document.getElementById('ag-set-specific').value = data.antigravity.specific_time || '03:00';
                }

                // Update Codex
                document.getElementById('cx-time').innerText = formatTime(data.codex.timer);
                document.getElementById('cx-status').innerText = `Status: ${data.codex.last_status}`;
                document.getElementById('cx-enabled').checked = data.codex.enabled;
                const cxPercent = (data.codex.timer / data.codex.duration) * 100;
                document.getElementById('cx-progress').style.width = `${100 - cxPercent}%`;

                // Update Codex Mode UI
                const cxModeState = data.codex.mode || 'duration';
                if (cxModeState === 'duration') {
                    document.getElementById('cx-mode-duration').classList.add('active');
                    document.getElementById('cx-mode-specific').classList.remove('active');
                    document.getElementById('cx-duration-section').style.display = 'block';
                    document.getElementById('cx-specific-section').style.display = 'none';
                    document.getElementById('cx-target-time-label').style.display = 'none';
                } else {
                    document.getElementById('cx-mode-specific').classList.add('active');
                    document.getElementById('cx-mode-duration').classList.remove('active');
                    document.getElementById('cx-duration-section').style.display = 'none';
                    document.getElementById('cx-specific-section').style.display = 'block';
                    document.getElementById('cx-target-time-label').style.display = 'block';
                    document.getElementById('cx-target-time').innerText = data.codex.specific_time || '03:00';
                }
                if (document.activeElement !== document.getElementById('cx-set-specific')) {
                    document.getElementById('cx-set-specific').value = data.codex.specific_time || '03:00';
                }



                // Update prompt template input if focused is not active
                if (document.activeElement !== document.getElementById('prompt-template-input')) {
                    document.getElementById('prompt-template-input').value = data.prompt_template;
                }

                // Update logs
                const logsList = document.getElementById('logs-list');
                logsList.innerHTML = '';
                if (data.logs.length === 0) {
                    logsList.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 1rem;">No events logged yet</div>';
                } else {
                    data.logs.forEach(log => {
                        const levelClass = log.level === 'SUCCESS' ? 'level-success' : (log.level === 'ERROR' ? 'level-error' : 'level-info');
                        const entry = document.createElement('div');
                        entry.className = 'log-entry';
                        entry.innerHTML = `
                            <span class="log-time">${log.time}</span>
                            <span class="log-level ${levelClass}">${log.level}</span>
                            <span class="log-msg">${log.message}</span>
                        `;
                        logsList.appendChild(entry);
                    });
                }
            } catch (err) {
                console.error("Error fetching status:", err);
            }
        }

        async function triggerNow(target) {
            try {
                const response = await fetch('/api/trigger', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target})
                });
                const result = await response.json();
                fetchStatus();
            } catch (err) {
                alert("Trigger failed: " + err);
            }
        }

        async function setTimer(target) {
            const hours = parseInt(document.getElementById(`${target === 'antigravity' ? 'ag' : 'cx'}-set-hours`).value) || 0;
            const mins = parseInt(document.getElementById(`${target === 'antigravity' ? 'ag' : 'cx'}-set-mins`).value) || 0;
            const totalSeconds = (hours * 3600) + (mins * 60);

            try {
                const response = await fetch('/api/timer-set', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target, seconds: totalSeconds})
                });
                fetchStatus();
            } catch (err) {
                alert("Set timer failed: " + err);
            }
        }

        async function updateSettings(target) {
            const payload = {};
            if (target === 'antigravity') {
                payload.antigravity = {
                    enabled: document.getElementById('ag-enabled').checked
                };
            } else if (target === 'codex') {
                payload.codex = {
                    enabled: document.getElementById('cx-enabled').checked
                };
            }

            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                fetchStatus();
            } catch (err) {
                console.error("Failed to update settings:", err);
            }
        }

        async function updatePromptTemplate() {
            const val = document.getElementById('prompt-template-input').value;
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({prompt_template: val})
                });
                fetchStatus();
                alert("Prompt template saved!");
            } catch (err) {
                alert("Failed to save template: " + err);
            }
        }

        async function setTimerMode(target, mode) {
            const payload = {};
            payload[target] = { mode: mode };
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                fetchStatus();
            } catch (err) {
                console.error("Failed to set timer mode:", err);
            }
        }

        async function saveSpecificTime(target) {
            const val = document.getElementById(`${target === 'antigravity' ? 'ag' : 'cx'}-set-specific`).value;
            const payload = {};
            payload[target] = { specific_time: val };
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                fetchStatus();
                alert("Specific time saved!");
            } catch (err) {
                alert("Failed to save specific time: " + err);
            }
        }

        async function add5Hours(target) {
            const input = document.getElementById(`${target === 'antigravity' ? 'ag' : 'cx'}-set-specific`);
            const val = input.value;
            if (!val) return;
            const parts = val.split(":");
            let h = parseInt(parts[0]);
            let m = parseInt(parts[1]);
            h = (h + 5) % 24;
            const newVal = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
            input.value = newVal;
            
            const payload = {};
            payload[target] = { specific_time: newVal };
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                fetchStatus();
            } catch (err) {
                console.error("Failed to add 5 hours:", err);
            }
        }

        // Poll status every second
        setInterval(fetchStatus, 1000);
        fetchStatus();
    </script>
</body>
</html>
"""

class KeepAwakeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with LOCK:
                response_data = STATE.copy()
                response_data["latest_commit"] = get_latest_commit_message()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            params = json.loads(post_data) if post_data else {}
        except Exception:
            params = {}

        if self.path == '/api/trigger':
            target = params.get('target', 'both')
            results = perform_trigger(target)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "results": results}).encode('utf-8'))

        elif self.path == '/api/timer-set':
            target = params.get('target')
            seconds = int(params.get('seconds', 18000))
            
            with LOCK:
                if target in ["antigravity", "codex"]:
                    STATE[target]["timer"] = seconds
                    if seconds > 0:
                        STATE[target]["duration"] = seconds
                    add_log(f"Set {target.capitalize()} timer to {seconds}s", True, "INFO")
                    save_state()
                    
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))

        elif self.path == '/api/settings':
            with LOCK:
                if "antigravity" in params:
                    STATE["antigravity"].update(params["antigravity"])
                if "codex" in params:
                    STATE["codex"].update(params["codex"])
                if "prompt_template" in params:
                    STATE["prompt_template"] = params["prompt_template"]
                add_log("Settings updated", True, "INFO")
                save_state()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=3010):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, KeepAwakeHandler)
    print(f"Awake Keeper running at http://localhost:{port}")
    add_log(f"Server started on port {port}", True, "INFO")
    
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass
        
    httpd.serve_forever()

if __name__ == '__main__':
    load_state()
    add_log("Awake Keeper service initialized", True, "INFO")
    
    sched_thread = threading.Thread(target=scheduler_loop, daemon=True)
    sched_thread.start()
    
    try:
        run_server(port=3010)
    except KeyboardInterrupt:
        print("\nShutting down Awake Keeper.")
        sys.exit(0)
