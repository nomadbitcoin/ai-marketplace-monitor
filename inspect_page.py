#!/usr/bin/env python3
"""Inspect page and save HTML/element info for debugging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace
from ai_marketplace_monitor.utils import amm_home

TARGET_URL = "https://www.facebook.com/marketplace/item/1569242467518413/"

print(f"Opening {TARGET_URL}")
print("Browser will stay open for 30 seconds so you can inspect it...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    marketplace = FacebookMarketplace("facebook", browser, logger=None)

    # Load session
    storage_state_path = amm_home / "facebook_session.json"
    if storage_state_path.exists():
        marketplace.config = type('obj', (object,), {
            'login_wait_time': 0,
            'monitor_config': None
        })()
        marketplace.login()

    if marketplace.page:
        marketplace.page.goto(TARGET_URL, timeout=30000)
        marketplace.page.wait_for_load_state("domcontentloaded")
        marketplace.page.wait_for_timeout(3000)

        # Save HTML
        html = marketplace.page.content()
        with open("/tmp/facebook_listing.html", "w") as f:
            f.write(html)
        print("✅ Saved HTML to /tmp/facebook_listing.html")

        # Extract and print key elements
        print("\n" + "="*80)
        print("ELEMENTS FOUND:")
        print("="*80)

        # H1s
        h1s = marketplace.page.query_selector_all("h1")
        print(f"\n📌 H1 elements ({len(h1s)}):")
        for i, h1 in enumerate(h1s):
            print(f"  [{i}] {(h1.text_content() or '').strip()[:80]}")

        # Sellers
        sellers = marketplace.page.query_selector_all("a[href*='marketplace/profile']")
        print(f"\n📌 Seller links ({len(sellers)}):")
        for i, sel in enumerate(sellers[:5]):
            print(f"  [{i}] {(sel.text_content() or '').strip()[:80]}")

        # All spans (to find price/location)
        spans = marketplace.page.query_selector_all("span")
        print(f"\n📌 Spans with $ or NZ$ ({len([s for s in spans if '$' in (s.text_content() or '')])} of {len(spans)}):")
        for i, span in enumerate(spans):
            text = (span.text_content() or '').strip()
            if '$' in text and len(text) < 50:
                print(f"  [{i}] {text}")

        print("\n" + "="*80)
        print("Browser staying open for 30 seconds for inspection...")
        print("="*80 + "\n")

        marketplace.page.wait_for_timeout(30000)

    browser.close()

print("\n✅ Done - check /tmp/facebook_listing.html for full page source")
