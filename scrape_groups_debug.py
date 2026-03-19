#!/usr/bin/env python3
"""Debug Facebook Groups page structure."""

import sys
import logging
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("debug")

GROUP_URL = "https://www.facebook.com/groups/1042388317765111/"

print("\n" + "=" * 80)
print("FACEBOOK GROUPS DEBUG - INSPECTING PAGE STRUCTURE")
print("=" * 80 + "\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    storage_state_path = amm_home / "facebook_session.json"
    context_options = {}
    if storage_state_path.exists():
        context_options["storage_state"] = str(storage_state_path)
        logger.info("✅ Loading saved Facebook session")

    context = browser.new_context(**context_options)
    page = context.new_page()

    logger.info(f"📍 Navigating to group: {GROUP_URL}")
    page.goto(GROUP_URL, timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)

    # Click see more buttons
    try:
        see_more_pattern = re.compile(r"(See more|Ver mais)", re.IGNORECASE)
        see_more_buttons = page.get_by_text(see_more_pattern).all()
        for button in see_more_buttons[:3]:  # Click first 3
            try:
                if button.is_visible(timeout=1000):
                    button.click()
                    logger.info("Clicked 'See more'")
                    time.sleep(1)
            except:
                pass
    except:
        pass

    time.sleep(2)

    print("\n" + "=" * 80)
    print("INSPECTING PAGE STRUCTURE")
    print("=" * 80 + "\n")

    # Find articles
    articles = page.query_selector_all("div[role='article']")
    print(f"Found {len(articles)} article elements\n")

    if articles:
        print("=" * 80)
        print("FIRST ARTICLE ANALYSIS")
        print("=" * 80 + "\n")

        first = articles[0]

        # Get all text
        full_text = first.text_content() or ""
        print(f"📄 Total text length: {len(full_text)} characters")
        print(f"📄 First 500 chars:\n{full_text[:500]}\n")

        # Count elements
        all_divs = first.query_selector_all("div")
        all_spans = first.query_selector_all("span")
        all_links = first.query_selector_all("a")
        print(f"📊 Element counts:")
        print(f"   - DIVs: {len(all_divs)}")
        print(f"   - SPANs: {len(all_spans)}")
        print(f"   - Links: {len(all_links)}\n")

        # Show first few links
        print("🔗 First 5 links:")
        for i, link in enumerate(all_links[:5]):
            href = link.get_attribute("href") or ""
            text = (link.text_content() or "").strip()[:50]
            print(f"   [{i}] {href[:80]}  |  Text: {text}")
        print()

        # Show spans with dir=auto
        dir_auto = first.query_selector_all("div[dir='auto'], span[dir='auto']")
        print(f"📝 Elements with dir='auto': {len(dir_auto)}")
        for i, elem in enumerate(dir_auto[:10]):
            text = (elem.text_content() or "").strip()
            if len(text) > 20:
                print(f"   [{i}] {text[:100]}")
        print()

        # Dump HTML structure (first 1000 chars)
        html = first.inner_html()[:1000]
        print("🔍 HTML structure (first 1000 chars):")
        print(html)
        print()

    logger.info("\n⏸️  Browser will remain open for 120 seconds for manual inspection...")
    logger.info("Use this time to inspect the page structure in the browser DevTools")
    time.sleep(120)

    logger.info("Closing browser...")
    browser.close()

print("\n" + "=" * 80)
print("DONE")
print("=" * 80 + "\n")
