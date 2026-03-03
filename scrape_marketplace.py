#!/usr/bin/env python3
"""Scrape Facebook Marketplace search results by connecting to a running browser.

Prerequisites:
    1. Launch browser first:  python launch_browser.py
    2. Then run this script:  python scrape_marketplace.py <URL>

Usage:
    python scrape_marketplace.py "https://www.facebook.com/marketplace/auckland/search?minPrice=1235&maxPrice=1550&query=wof&exact=false"
    python scrape_marketplace.py --port 9222 --output data/results.csv "<URL>"
    python scrape_marketplace.py --include-distant "<URL>"

The script:
    1. Connects to the running browser via CDP
    2. Navigates to the marketplace URL
    3. Scrolls down until all primary results are loaded
    4. Stops at "Resultados mais distantes" (distant results section)
    5. Extracts all listing data (price, title, location, URL, image)
    6. Saves to CSV
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import selectors — edit selectors.py when Facebook changes layout
from fb_selectors import (
    COOKIE_BUTTON_PATTERNS,
    DISTANT_RESULTS_TEXT,
    DISTANT_RESULTS_TEXT_EN,
    LISTING_LINK,
    LOADING_INDICATOR,
    LOCATION_SPAN_STYLE,
    ORIGINAL_PRICE_CLASS,
    PRICE_SPAN_STYLE,
    TITLE_CONTAINER_CLASS,
    TITLE_SPAN_STYLE,
    VIRTUALIZED_ATTR,
    VIRTUALIZED_VALUE,
)

from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("marketplace_scraper")
console = Console()

DATA_DIR = Path(__file__).parent / "data"
CDP_INFO_FILE = DATA_DIR / ".browser_info.json"


def get_cdp_url(port=None):
    """Get CDP URL from info file or port argument."""
    if port:
        return f"http://localhost:{port}"

    if CDP_INFO_FILE.exists():
        info = json.loads(CDP_INFO_FILE.read_text())
        return info.get("cdp_url", "http://localhost:9222")

    return "http://localhost:9222"


# JavaScript to extract listings — uses selectors from Python config
def build_extract_js():
    """Load extract_listings.js and inject selector values via string replacement."""
    js_path = Path(__file__).parent / "extract_listings.js"
    js = js_path.read_text()
    return (js
        .replace("__LISTING_LINK__", LISTING_LINK)
        .replace("__PRICE_SPAN_STYLE__", PRICE_SPAN_STYLE)
        .replace("__ORIGINAL_PRICE_CLASS__", ORIGINAL_PRICE_CLASS)
        .replace("__TITLE_CONTAINER_CLASS__", TITLE_CONTAINER_CLASS)
        .replace("__TITLE_SPAN_STYLE__", TITLE_SPAN_STYLE)
        .replace("__LOCATION_SPAN_STYLE__", LOCATION_SPAN_STYLE)
        .replace("__DISTANT_RESULTS_TEXT__", DISTANT_RESULTS_TEXT)
        .replace("__DISTANT_RESULTS_TEXT_EN__", DISTANT_RESULTS_TEXT_EN)
    )




def build_check_distant_js():
    """JS to check if the 'distant results' section is visible on page."""
    return f"""
    () => {{
        const allSpans = document.querySelectorAll('span');
        for (const span of allSpans) {{
            const text = (span.textContent || '').trim();
            if (text.includes('{DISTANT_RESULTS_TEXT}') || text.includes('{DISTANT_RESULTS_TEXT_EN}')) {{
                return true;
            }}
        }}
        return false;
    }}
    """


def build_count_listings_js():
    """JS to count current listing links on page."""
    return f"""
    () => document.querySelectorAll('{LISTING_LINK}').length
    """


def build_check_loading_js():
    """JS to check if loading spinners are visible."""
    return f"""
    () => {{
        const loaders = document.querySelectorAll('{LOADING_INDICATOR}');
        return loaders.length > 0;
    }}
    """


def build_check_virtualized_js():
    """JS to count virtualized (not-yet-rendered) items."""
    return f"""
    () => {{
        const items = document.querySelectorAll('[{VIRTUALIZED_ATTR}="{VIRTUALIZED_VALUE}"]');
        return items.length;
    }}
    """


def scroll_and_load(page, include_distant=False, max_scrolls=100, scroll_pause=2.0):
    """Scroll down the page to load all results.

    Stops when:
        - The "distant results" section appears (unless include_distant=True)
        - No new results load after several scroll attempts
        - max_scrolls is reached
    """
    check_distant_js = build_check_distant_js()
    count_js = build_count_listings_js()
    check_loading_js = build_check_loading_js()

    prev_count = 0
    no_change_count = 0
    max_no_change = 5  # Stop after 5 scrolls with no new results
    primary_count = None  # Count of listings when distant section first appeared

    for scroll_num in range(1, max_scrolls + 1):
        # Check for distant results section
        if not include_distant:
            has_distant = page.evaluate(check_distant_js)
            if has_distant:
                primary_count = page.evaluate(count_js)
                logger.info(f"[STOP] Found 'distant results' section at scroll #{scroll_num} ({primary_count} primary listings)")
                break

        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(scroll_pause)

        # Wait for loading spinners to disappear
        for _ in range(10):
            is_loading = page.evaluate(check_loading_js)
            if not is_loading:
                break
            time.sleep(0.5)

        # Count current listings
        current_count = page.evaluate(count_js)
        logger.info(f"  Scroll #{scroll_num}: {current_count} listings loaded")

        if current_count == prev_count:
            no_change_count += 1
            if no_change_count >= max_no_change:
                logger.info(f"[STOP] No new results after {max_no_change} scrolls")
                break
        else:
            no_change_count = 0

        prev_count = current_count

    # Scroll back through the page to de-virtualize items
    logger.info("[DEVIRT] Scrolling back through page to render all items...")
    page_height = page.evaluate("document.body.scrollHeight")
    viewport_height = page.evaluate("window.innerHeight")
    scroll_step = viewport_height * 0.8

    pos = 0
    while pos < page_height:
        page.evaluate(f"window.scrollTo(0, {pos})")
        time.sleep(0.3)
        pos += scroll_step

    # Final scroll to bottom and wait for all items to render
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(3)

    final_count = page.evaluate(count_js)
    logger.info(f"[DONE] Total listings after scroll: {final_count}")
    return primary_count if primary_count is not None else final_count


# ============================================================================
# POST-SCRAPE FILTERS
# Edit this list to exclude listings whose title contains any of these words.
# Case-insensitive. Applied before saving.
# ============================================================================
TITLE_EXCLUDE_KEYWORDS = [
    "boat",
    "trailer",
    "motor and trailer",
]


def apply_filters(listings):
    """Filter out listings based on title keywords."""
    excluded = []
    kept = []
    for listing in listings:
        title = (listing.get("title") or "").lower()
        matched = [kw for kw in TITLE_EXCLUDE_KEYWORDS if kw in title]
        if matched:
            excluded.append((listing, matched))
        else:
            kept.append(listing)

    if excluded:
        logger.info(f"[FILTER] Excluded {len(excluded)} listings:")
        for l, kws in excluded:
            logger.info(f"  - '{l.get('title') or '(no title)'}' matched: {kws}")

    return kept


def extract_listings(page, primary_count=None):
    """Extract listing data from the page.

    primary_count: if set, only return the first N listings (those before
    the 'distant results' section). If None, return all listings.
    """
    extract_js = build_extract_js()
    listings = page.evaluate(extract_js)

    if primary_count is not None:
        listings = listings[:primary_count]

    return listings


def save_to_json(listings, output_path):
    """Save listings to JSON — used to track results page before individual scraping."""
    output_path.parent.mkdir(exist_ok=True)
    ts = datetime.now().isoformat()
    payload = {
        "scraped_at": ts,
        "total": len(listings),
        "listings": [
            {
                "listing_id": l.get("listing_id", ""),
                "title": l.get("title", ""),
                "price": l.get("price", ""),
                "original_price": l.get("original_price", ""),
                "location": l.get("location", ""),
                "mileage": l.get("mileage", ""),
                "url": l.get("url", ""),
                "image": l.get("image", ""),
                "is_distant": l.get("is_distant", False),
                "scraped_at": ts,
            }
            for l in listings
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return output_path


def save_to_csv(listings, output_path):
    """Save listings to CSV file."""
    output_path.parent.mkdir(exist_ok=True)

    fieldnames = [
        "timestamp", "listing_id", "title", "price", "original_price",
        "location", "mileage", "url", "image", "is_distant",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for listing in listings:
            writer.writerow({
                "timestamp": datetime.now().isoformat(),
                "listing_id": listing.get("listing_id", ""),
                "title": listing.get("title", ""),
                "price": listing.get("price", ""),
                "original_price": listing.get("original_price", ""),
                "location": listing.get("location", ""),
                "mileage": listing.get("mileage", ""),
                "url": listing.get("url", ""),
                "image": listing.get("image", ""),
                "is_distant": listing.get("is_distant", False),
            })

    return output_path


def display_results(listings):
    """Display results in a rich table."""
    table = Table(title=f"Marketplace Results ({len(listings)} listings)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Price", style="green", width=12)
    table.add_column("Title", width=35)
    table.add_column("Location", width=25)
    table.add_column("ID", style="dim", width=16)
    table.add_column("Distant", width=8)

    for i, listing in enumerate(listings, 1):
        price = f"NZ${listing.get('price', '?')}"
        orig = listing.get("original_price", "")
        if orig:
            price += f" ([dim strike]${orig}[/])"

        table.add_row(
            str(i),
            price,
            listing.get("title", "") or "(no title)",
            listing.get("location", "") or "(unknown)",
            listing.get("listing_id", ""),
            "yes" if listing.get("is_distant") else "",
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Scrape Facebook Marketplace results")
    parser.add_argument("url", help="Marketplace search URL")
    parser.add_argument("--port", type=int, default=None, help="CDP port (default: from .browser_info.json or 9222)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV file path")
    parser.add_argument("--include-distant", action="store_true", help="Include distant results too")
    parser.add_argument("--max-scrolls", type=int, default=100, help="Max scroll attempts (default: 100)")
    parser.add_argument("--scroll-pause", type=float, default=2.0, help="Pause between scrolls in seconds")
    parser.add_argument("--standalone", action="store_true",
                        help="Run with own browser (don't connect to launch_browser.py)")
    args = parser.parse_args()

    # Default output filename based on URL
    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DATA_DIR / f"marketplace_{ts}.json"

    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        if args.standalone:
            # Launch own browser
            logger.info("[STANDALONE] Launching own browser...")
            from ai_marketplace_monitor.utils import amm_home
            browser = p.chromium.launch(headless=False)
            context_opts = {"viewport": {"width": 1920, "height": 1080}}
            session_path = amm_home / "facebook_session.json"
            if session_path.exists():
                context_opts["storage_state"] = str(session_path)
                logger.info("[OK] Loaded Facebook session")
            context = browser.new_context(**context_opts)
            page = context.new_page()
        else:
            # Connect to the browser launched by launch_browser.py via CDP
            cdp_url = get_cdp_url(args.port)
            logger.info(f"[CDP] Connecting to browser at {cdp_url}...")
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception as e:
                logger.error(f"[ERROR] Could not connect: {e}")
                logger.error("  Make sure launch_browser.py is running first!")
                sys.exit(1)

            # connect_over_cdp with a persistent context browser returns
            # contexts[0] as the persistent context — open a new tab in it.
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                logger.info(f"[OK] Connected to existing context ({len(context.pages)} open tabs)")
            else:
                # Fallback: create a new context in the connected browser
                context = browser.new_context()
                logger.info("[OK] Connected (new context)")

            page = context.new_page()
            logger.info("[OK] Opened new tab")

        # Navigate to the marketplace URL
        logger.info(f"[NAV] {args.url}")
        page.goto(args.url, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # Handle cookie consent
        try:
            for pattern in COOKIE_BUTTON_PATTERNS:
                allow_button = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE))
                if allow_button.is_visible(timeout=2000):
                    allow_button.click()
                    logger.info("[OK] Accepted cookies")
                    time.sleep(2)
                    break
        except Exception:
            pass

        # Wait for initial listings to render
        logger.info("[WAIT] Waiting for listings to load...")
        try:
            page.wait_for_selector(LISTING_LINK, timeout=15000)
        except Exception:
            logger.warning("[WARN] No listings found within timeout. Page may need login.")

        # Scroll to load all results — returns primary_count (listings before distant section)
        logger.info("[SCROLL] Loading all results...")
        primary_count = scroll_and_load(
            page,
            include_distant=args.include_distant,
            max_scrolls=args.max_scrolls,
            scroll_pause=args.scroll_pause,
        )

        # Extract listings — slice to primary_count to exclude distant results
        logger.info("[EXTRACT] Extracting listing data...")
        listings = extract_listings(
            page,
            primary_count=None if args.include_distant else primary_count,
        )

        logger.info(f"[OK] Extracted {len(listings)} listings")

        # Apply post-scrape filters (title keywords, etc.)
        listings = apply_filters(listings)
        logger.info(f"[OK] {len(listings)} listings after filtering")

        # Display results
        if listings:
            display_results(listings)

        # Save to JSON (results page snapshot — used before individual scraping)
        json_path = output_path.with_suffix(".json")
        save_to_json(listings, json_path)
        logger.info(f"[SAVED] {json_path}")

        logger.info(f"\n[SUMMARY]")
        logger.info(f"  Total saved:     {len(listings)}")
        logger.info(f"  Output:          {json_path}")

        # Keep page open if standalone
        if args.standalone:
            logger.info("\n[WAIT] Browser open for 30s inspection. Press Ctrl+C to close.")
            try:
                time.sleep(30)
            except KeyboardInterrupt:
                pass
            browser.close()
        else:
            # Close just the page we opened, keep browser running
            logger.info("[OK] Done. Browser still running (close page manually or leave it).")


if __name__ == "__main__":
    main()
