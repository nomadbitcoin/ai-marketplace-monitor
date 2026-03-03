#!/usr/bin/env python3
"""Launch a persistent Chromium browser with CDP debugging port.

Starts a browser that stays open as a blocking process. Run this in a
dedicated terminal and leave it open. Other scripts connect via CDP.

Usage:
    # In a dedicated terminal — keep this open:
    .venv/bin/python launch_browser.py

    # Other scripts connect to it via:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")

The browser uses a persistent profile directory (data/.chromium_profile)
so your Facebook login is preserved across runs.

First run: Facebook will show a login page — log in manually once.
After that: session is saved in the profile and reused automatically.
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

DATA_DIR = Path(__file__).parent / "data"
CDP_INFO_FILE = DATA_DIR / ".browser_info.json"
# Persistent Chrome profile — cookies/session live here across runs
PROFILE_DIR = DATA_DIR / ".chromium_profile"

PORT = 9222
START_URL = "https://www.facebook.com/marketplace/"

DATA_DIR.mkdir(exist_ok=True)
PROFILE_DIR.mkdir(exist_ok=True)

# Kill any previous instance using the same port
if CDP_INFO_FILE.exists():
    try:
        old = json.loads(CDP_INFO_FILE.read_text())
        old_pid = old.get("pid")
        if old_pid and old_pid != os.getpid():
            try:
                os.kill(old_pid, signal.SIGTERM)
                print(f"[CLEANUP] Killed old browser process PID {old_pid}")
                time.sleep(2)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    CDP_INFO_FILE.unlink(missing_ok=True)

from patchright.sync_api import sync_playwright

# Find the saved Facebook session (cookies/localStorage)
SESSION_FILE = Path("/Users/nomadbitcoin/.ai-marketplace-monitor/facebook_session.json")

print("=" * 60)
print("LAUNCHING BROWSER")
print("=" * 60)
print(f"  Profile dir: {PROFILE_DIR}")
print(f"  CDP port:    {PORT}")
print(f"  Start URL:   {START_URL}")
if SESSION_FILE.exists():
    print(f"  Session:     {SESSION_FILE} ✓")
else:
    print(f"  Session:     NOT FOUND — you will need to log in manually")
print()
print("  Keep this terminal open. Press Ctrl+C to shut down.")
print("=" * 60)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        args=[
            f"--remote-debugging-port={PORT}",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
        ],
        viewport={"width": 1280, "height": 900},
        no_viewport=False,
    )

    # Inject saved Facebook session cookies into the persistent context
    if SESSION_FILE.exists():
        print(f"\n[OK] Loading Facebook session from {SESSION_FILE}")
        session_data = json.loads(SESSION_FILE.read_text())
        cookies = session_data.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)
            print(f"[OK] Injected {len(cookies)} cookies into browser")

    # Use existing page or open new one
    page = context.pages[0] if context.pages else context.new_page()

    # Write connection info for scraper scripts
    CDP_INFO_FILE.write_text(json.dumps({
        "cdp_port": PORT,
        "cdp_url": f"http://localhost:{PORT}",
        "pid": os.getpid(),
        "launched_at": time.time(),
        "profile_dir": str(PROFILE_DIR),
    }, indent=2))

    print(f"\n[NAV] Navigating to {START_URL} ...")
    page.goto(START_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    print(f"[OK]  Page loaded: {page.title()}")
    print(f"\n[READY] Browser is live at http://localhost:{PORT}")
    print("[READY] Scraper can now connect. Waiting...\n")

    def shutdown(sig=None, frame=None):
        print("\n[SHUTDOWN] Closing browser and cleaning up...")
        CDP_INFO_FILE.unlink(missing_ok=True)
        try:
            context.close()
        except Exception:
            pass
        print("[DONE] Browser closed.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Block forever — heartbeat every 5s
    while True:
        time.sleep(5)
        try:
            _ = page.title()
        except Exception:
            print("[WARN] Browser connection lost — shutting down.")
            break

    shutdown()
