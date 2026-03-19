#!/usr/bin/env python3
"""Interactive login helper — saves Facebook session for use by the monitor.

Opens a visible browser on the Facebook login page. Log in manually,
complete any 2FA prompts, then press Enter here to save the session.

The saved session is reused by monitor_marketplace.py on every cron run
so you only need to log in once (or when the session expires).

Usage:
    .venv/bin/python login_session.py
"""

import json
import sys
from pathlib import Path

SESSION_FILE = Path("/Users/nomadbitcoin/.ai-marketplace-monitor/facebook_session.json")
LOGIN_URL = "https://www.facebook.com/login"

SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

from patchright.sync_api import sync_playwright

print("=" * 55)
print("FACEBOOK LOGIN — SESSION SAVER")
print("=" * 55)
print()
print("  1. A browser window will open on the Facebook login page.")
print("  2. Log in and complete any 2FA prompts.")
print("  3. Once you are fully logged in, come back here and")
print("     press Enter to save your session.")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()

    print(f"  Opening {LOGIN_URL} ...")
    page.goto(LOGIN_URL, timeout=30000)
    print()
    print("  Browser is open. Log in now.")
    print()

    input("  >>> Press Enter AFTER you are fully logged in and 2FA is done: ")
    print()

    # Save full storage state (cookies + localStorage)
    state = context.storage_state()
    SESSION_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    n_cookies = len(state.get("cookies", []))
    print(f"  [OK] Session saved to {SESSION_FILE}")
    print(f"       {n_cookies} cookies stored.")
    print()

    browser.close()

print("  Done. The monitor will use this session automatically.")
print("=" * 55)
