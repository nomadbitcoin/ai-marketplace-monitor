#!/usr/bin/env python3
"""Clean Facebook Groups marketplace scraper - filters out non-sales posts."""

import sys
import logging
import time
import re
import json
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler
from rich import print as rprint

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("groups_scraper")

GROUP_URL = "https://www.facebook.com/groups/1042388317765111/"

print("\n" + "=" * 80)
print("FACEBOOK GROUPS SCRAPER - CLEAN VERSION")
print("=" * 80 + "\n")


def is_valid_sale_post(text: str, price: str) -> bool:
    """Filter out non-sale posts like stolen cars, fake prices, etc."""
    text_lower = text.lower()

    # Skip stolen car reports
    if "stolen" in text_lower:
        return False

    # Skip fake/placeholder prices
    if price in ["123", "456", "123456"]:
        return False

    # Must have a reasonable price
    if price:
        try:
            price_val = int(price)
            if price_val < 100 or price_val > 50000:  # Reasonable car price range
                return False
        except ValueError:
            return False

    # Skip if it's just noise/UI elements
    if text.count("Facebook") > 20:  # Too much UI noise
        return False

    return True


def extract_clean_listings(page, logger):
    """Extract car posts from group using JavaScript, with deduplication and filtering."""

    js_code = """
    () => {
        const listings = new Map();  // Use Map to deduplicate

        // Look for elements with prices (these are likely car posts)
        const allDivs = document.querySelectorAll('div');
        const pricePattern = /NZ?\\$\\s*[\\d,]+/;

        allDivs.forEach(div => {
            const text = div.textContent || '';

            // Must have a price and reasonable text length
            if (!pricePattern.test(text) || text.length < 100 || text.length > 3000) {
                return;
            }

            // Extract price
            let price = '';
            const priceMatches = text.match(/NZ?\\$\\s*([\\d,\\.]+)/i);
            if (priceMatches) {
                const priceStr = priceMatches[1].replace(/[,\\.]/g, '');
                price = priceStr;
            }

            // Look for a link in this div to get the post URL
            const links = div.querySelectorAll('a');
            let url = '';
            for (const link of links) {
                const href = link.getAttribute('href');
                if (href && (href.includes('/posts/') || href.includes('/permalink/') || href.includes('/user/'))) {
                    url = href.startsWith('http') ? href : `https://www.facebook.com${href}`;
                    break;
                }
            }

            // Extract title - look for car model patterns
            let title = '';
            const titlePatterns = [
                /(\\d{4}\\s+[A-Z][A-Z\\s]+(?:FIT|CIVIC|COROLLA|MAZDA|HONDA|TOYOTA|NISSAN|FORD)[A-Z\\s]*)/i,
                /([A-Z]{2,}\\s+[A-Z]{2,})/,  // Two+ caps words
            ];
            for (const pattern of titlePatterns) {
                const match = text.match(pattern);
                if (match) {
                    title = match[1].trim().substring(0, 100);
                    break;
                }
            }

            // Location
            let location = '';
            const locationMatch = text.match(/Auckland|AUCKLAND|Wellington|Christchurch/i);
            if (locationMatch) {
                location = locationMatch[0];
            }

            // Create a unique key (use price + first 50 chars of text)
            const uniqueKey = price + text.substring(0, 50);

            if (!listings.has(uniqueKey) && price) {
                listings.set(uniqueKey, {
                    title,
                    description: text,
                    url,
                    price,
                    location,
                });
            }
        });

        return Array.from(listings.values());
    }
    """

    try:
        raw_listings = page.evaluate(js_code)
        logger.info(f"Extracted {len(raw_listings)} unique marketplace listings")

        # Filter out non-sale posts
        valid_listings = []
        for listing in raw_listings:
            if is_valid_sale_post(listing.get('description', ''), listing.get('price', '')):
                valid_listings.append(listing)

        logger.info(f"Filtered to {len(valid_listings)} valid sale listings")
        return valid_listings

    except Exception as e:
        logger.error(f"Error extracting listings: {e}")
        import traceback
        traceback.print_exc()
        return []


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

    # Handle cookie consent
    try:
        allow_button = page.get_by_role(
            "button",
            name=re.compile(r"Allow all cookies|Allow cookies|Accept All", re.IGNORECASE),
        )
        if allow_button.is_visible(timeout=3000):
            allow_button.click()
            logger.info("✅ Accepted cookies")
            time.sleep(2)
    except Exception:
        pass

    # Scroll to load more listings
    logger.info("📜 Scrolling to load more listings...")
    for i in range(5):
        page.evaluate(f"window.scrollTo(0, {(i + 1) * 800})")
        time.sleep(2)

    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    # Click "See more" buttons
    try:
        see_more_pattern = re.compile(r"(See more|Ver mais)", re.IGNORECASE)
        see_more_buttons = page.get_by_text(see_more_pattern).all()
        clicked = 0
        for button in see_more_buttons[:10]:
            try:
                if button.is_visible(timeout=1000):
                    button.click()
                    clicked += 1
                    time.sleep(0.3)
            except:
                pass
        if clicked > 0:
            logger.info(f"✅ Clicked {clicked} 'See more' buttons")
            time.sleep(2)
    except:
        pass

    # Extract clean listings
    logger.info("\n🔍 Extracting marketplace listings...")
    listings = extract_clean_listings(page, logger)

    print("\n" + "=" * 80)
    print(f"FOUND {len(listings)} VALID CAR LISTINGS")
    print("=" * 80 + "\n")

    for idx, listing in enumerate(listings, 1):
        print(f"\n🚗 CAR #{idx}:")
        print(f"  📝 Title: {listing.get('title', '(not found)')}")
        print(f"  💰 Price: ${listing.get('price', '(not found)')}")
        print(f"  📍 Location: {listing.get('location', '(not found)')}")
        print(f"  🔗 URL: {listing.get('url', '(not found)')}")
        desc = listing.get('description', '')
        if desc:
            print(f"  📄 Description ({len(desc)} chars): {desc[:200]}...")

    # Show first complete listing
    if listings:
        print("\n" + "=" * 80)
        print("FIRST LISTING DETAILS:")
        print("=" * 80)
        print(json.dumps(listings[0], indent=2))

    logger.info("\n⏸️  Browser will remain open for 90 seconds...")
    time.sleep(90)

    logger.info("Closing browser...")
    browser.close()

print("\n" + "=" * 80)
print("DONE")
print("=" * 80 + "\n")
