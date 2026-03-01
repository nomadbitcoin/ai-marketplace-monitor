#!/usr/bin/env python3
"""Debug script to work on a single listing interactively."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler
from rich import print as rprint

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.DEBUG)],
)
logger = logging.getLogger("debug")

# URL to debug
TARGET_URL = "https://www.facebook.com/marketplace/item/1569242467518413/"

print("\n" + "="*80)
print(f"DEBUGGING: {TARGET_URL}")
print("="*80 + "\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    marketplace = FacebookMarketplace("facebook", browser, logger=logger)

    # Load session
    storage_state_path = amm_home / "facebook_session.json"
    if storage_state_path.exists():
        marketplace.config = type('obj', (object,), {
            'login_wait_time': 0,
            'monitor_config': None
        })()
        marketplace.login()

    if marketplace.page:
        print("Navigating to listing...")
        marketplace.page.goto(TARGET_URL, timeout=30000)
        marketplace.page.wait_for_load_state("domcontentloaded")
        marketplace.page.wait_for_timeout(2000)

        print("\n" + "="*80)
        print("EXTRACTING DATA")
        print("="*80 + "\n")

        # Extract title from H1
        print("🔍 Looking for TITLE (H1 elements)...")
        h1_elements = marketplace.page.query_selector_all("h1")
        print(f"Found {len(h1_elements)} H1 elements:")
        for i, h1 in enumerate(h1_elements):
            text = (h1.text_content() or "").strip()
            print(f"  H1[{i}]: '{text[:100]}'")

        # Extract price
        print("\n🔍 Looking for PRICE (elements with $)...")
        # Try multiple strategies
        try:
            # Strategy 1: Look for span/div with $ symbol
            price_elements = marketplace.page.query_selector_all("span:has-text('$'), div:has-text('$')")
            print(f"Found {len(price_elements)} elements containing '$':")
            for i, elem in enumerate(price_elements[:5]):
                text = (elem.text_content() or "").strip()
                if len(text) < 50:  # Avoid long text blocks
                    print(f"  Price[{i}]: '{text}'")
        except Exception as e:
            print(f"  Error: {e}")

        # Extract location
        print("\n🔍 Looking for LOCATION...")
        # Look for common location patterns
        try:
            location_elements = marketplace.page.query_selector_all("span:has-text('Auckland'), span:has-text('New Zealand')")
            print(f"Found {len(location_elements)} location elements:")
            for i, elem in enumerate(location_elements[:3]):
                text = (elem.text_content() or "").strip()
                print(f"  Location[{i}]: '{text}'")
        except Exception as e:
            print(f"  Error: {e}")

        # Extract seller
        print("\n🔍 Looking for SELLER...")
        seller_links = marketplace.page.query_selector_all("a[href*='marketplace/profile']")
        print(f"Found {len(seller_links)} seller profile links:")
        for i, link in enumerate(seller_links):
            text = (link.text_content() or "").strip()
            href = link.get_attribute("href")
            print(f"  Seller[{i}]: '{text}' (href: {href[:60]}...)")

        # Extract description
        print("\n🔍 Looking for DESCRIPTION...")
        # Look for large text blocks
        try:
            # Try different selectors
            desc_selectors = [
                "div[dir='auto'] span",
                "span[dir='auto']",
                "div[role='main'] span",
            ]
            for selector in desc_selectors:
                elements = marketplace.page.query_selector_all(selector)
                print(f"\nSelector '{selector}': Found {len(elements)} elements")
                for i, elem in enumerate(elements[:10]):
                    text = (elem.text_content() or "").strip()
                    if len(text) > 50:  # Only show substantial text
                        print(f"  [{i}] ({len(text)} chars): {text[:100]}...")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n" + "="*80)
        print("Browser will stay open for inspection.")
        print("Press Ctrl+C in terminal when done.")
        print("="*80 + "\n")

        try:
            while True:
                marketplace.page.wait_for_timeout(1000)
        except KeyboardInterrupt:
            print("\n\nClosing browser...")

    browser.close()

print("\n" + "="*80)
print("DONE")
print("="*80 + "\n")
