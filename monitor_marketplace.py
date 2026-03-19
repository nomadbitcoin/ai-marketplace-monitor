#!/usr/bin/env python3
"""Monitor Facebook Marketplace for new listings and send webhook notifications.

Designed to run as a cron job every 6 hours. Each run:
    1. Launches a fresh browser with saved Facebook session
    2. Scrapes the configured search URL
    3. Compares results against previously seen listing IDs
    4. POSTs new listing URLs to the configured webhook
    5. Updates the seen-IDs state file
    6. Closes the browser and exits

Never gets stuck: a hard timeout via SIGALRM kills the process if it runs
longer than MAX_RUNTIME_SECONDS.

Usage:
    .venv/bin/python monitor_marketplace.py

Cron (every 6 hours):
    0 */6 * * * cd /path/to/ai-marketplace-monitor && .venv/bin/python monitor_marketplace.py >> data/monitor.log 2>&1
"""

import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

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

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("marketplace_monitor")

# ============================================================================
# CONFIGURATION — edit here
# ============================================================================
SEARCH_URLS = [
    {
        "label": "WOF",
        "url": (
            "https://www.facebook.com/marketplace/115055298507659/search/"
            "?minPrice=1235&maxPrice=1550&query=wof&exact=false"
        ),
    },
    # Add more searches here, e.g.:
    {
        "label": "Car",
        "url": "https://www.facebook.com/marketplace/115055298507659/search/?minPrice=1235&maxPrice=1550&query=car&exact=false",
    },
]

WEBHOOK_URL = "https://automate.nomadbitcoin.xyz/webhook/6e0857d3-8600-4828-a6a9-8fa76078b50b"
WEBHOOK_AUTH = "Basic YWktbWFya2V0cGxhY2UtbW9uaXRvcjpZV2t0YldGeWEyVjBjR3hoWTJVdGJXOXVhWFJ2Y2pwaWRXNWtZUT0="

TITLE_EXCLUDE_KEYWORDS = ["boat", "trailer", "motor and trailer"]

# How long before giving up entirely (seconds) — prevents cron overlap / stuck runs
MAX_RUNTIME_SECONDS = 20 * 60  # 20 minutes

DATA_DIR = Path(__file__).parent / "data"
SEEN_IDS_FILE = DATA_DIR / "seen_listing_ids.json"
SESSION_FILE = Path("/Users/nomadbitcoin/.ai-marketplace-monitor/facebook_session.json")
PROFILE_DIR = DATA_DIR / ".chromium_profile"

# Scroll settings (faster than interactive runs)
MAX_SCROLLS = 60
SCROLL_PAUSE = 1.5
# ============================================================================


def hard_timeout_handler(signum, frame):
    logger.error("[TIMEOUT] Hard timeout reached — forcing exit to avoid cron overlap.")
    sys.exit(2)


def load_seen_ids() -> set:
    if SEEN_IDS_FILE.exists():
        try:
            return set(json.loads(SEEN_IDS_FILE.read_text()).get("ids", []))
        except Exception:
            pass
    return set()


def save_seen_ids(ids: set) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_IDS_FILE.write_text(
        json.dumps({"updated_at": datetime.now().isoformat(), "ids": sorted(ids)}, indent=2)
    )


def send_webhook(new_listings: list) -> bool:
    """POST new listing URLs to the configured webhook. Returns True on success."""
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        logger.error("[WEBHOOK] requests library not available — install it first")
        return False

    lines = [f"New Car listings with wof query ({len(new_listings)} found):"]
    for l in new_listings:
        title = l.get("title") or "(no title)"
        price = l.get("price") or "?"
        url = l.get("url", "")
        label = l.get("_label", "")
        prefix = f"[{label}] " if label else ""
        lines.append(f"• {prefix}NZ${price} — {title}\n  {url}")

    message = "\n".join(lines)

    try:
        resp = requests.post(
            WEBHOOK_URL,
            headers={
                "Authorization": WEBHOOK_AUTH,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"message": message},
            timeout=15,
        )
        if resp.ok:
            logger.info(f"[WEBHOOK] Sent — status {resp.status_code}")
            return True
        else:
            logger.warning(f"[WEBHOOK] Non-OK response: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed: {e}")
        return False


def build_extract_js() -> str:
    js_path = Path(__file__).parent / "extract_listings.js"
    js = js_path.read_text()
    return (
        js.replace("__LISTING_LINK__", LISTING_LINK)
        .replace("__PRICE_SPAN_STYLE__", PRICE_SPAN_STYLE)
        .replace("__ORIGINAL_PRICE_CLASS__", ORIGINAL_PRICE_CLASS)
        .replace("__TITLE_CONTAINER_CLASS__", TITLE_CONTAINER_CLASS)
        .replace("__TITLE_SPAN_STYLE__", TITLE_SPAN_STYLE)
        .replace("__LOCATION_SPAN_STYLE__", LOCATION_SPAN_STYLE)
        .replace("__DISTANT_RESULTS_TEXT__", DISTANT_RESULTS_TEXT)
        .replace("__DISTANT_RESULTS_TEXT_EN__", DISTANT_RESULTS_TEXT_EN)
    )


def scroll_and_load(page) -> int:
    """Scroll until distant results section appears. Returns primary listing count."""
    check_distant_js = f"""
    () => {{
        for (const s of document.querySelectorAll('span')) {{
            const t = (s.textContent || '').trim();
            if (t.includes('{DISTANT_RESULTS_TEXT}') || t.includes('{DISTANT_RESULTS_TEXT_EN}')) return true;
        }}
        return false;
    }}
    """
    count_js = f"() => document.querySelectorAll('{LISTING_LINK}').length"
    check_loading_js = f"""
    () => document.querySelectorAll('{LOADING_INDICATOR}').length > 0
    """

    prev_count = 0
    no_change = 0

    for i in range(1, MAX_SCROLLS + 1):
        if page.evaluate(check_distant_js):
            count = page.evaluate(count_js)
            logger.info(f"[STOP] Distant section found at scroll #{i} — {count} primary listings")
            return count

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(SCROLL_PAUSE)

        for _ in range(10):
            if not page.evaluate(check_loading_js):
                break
            time.sleep(0.3)

        current = page.evaluate(count_js)
        logger.info(f"  Scroll #{i}: {current} listings")

        if current == prev_count:
            no_change += 1
            if no_change >= 4:
                logger.info("[STOP] No new results — end of page")
                break
        else:
            no_change = 0
        prev_count = current

    # Devirtualize: slow scroll back up then down
    height = page.evaluate("document.body.scrollHeight")
    step = page.evaluate("window.innerHeight") * 0.8
    pos = 0
    while pos < height:
        page.evaluate(f"window.scrollTo(0, {pos})")
        time.sleep(0.2)
        pos += step

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    return page.evaluate(count_js)


def scrape(page, url: str, label: str = "") -> list:
    """Navigate to url, scroll, extract, and filter listings."""
    logger.info(f"[NAV] {label + ': ' if label else ''}{url}")
    page.goto(url, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    # Cookie consent
    try:
        for pattern in COOKIE_BUTTON_PATTERNS:
            btn = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE))
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(2)
                break
    except Exception:
        pass

    # Wait for initial listings
    try:
        page.wait_for_selector(LISTING_LINK, timeout=15000)
    except Exception:
        logger.warning("[WARN] No listings found within timeout — may need to re-login")
        return []

    primary_count = scroll_and_load(page)

    extract_js = build_extract_js()
    listings = page.evaluate(extract_js)
    listings = listings[:primary_count]

    # Filter
    kept = []
    for l in listings:
        title = (l.get("title") or "").lower()
        if not any(kw in title for kw in TITLE_EXCLUDE_KEYWORDS):
            kept.append(l)

    logger.info(f"[EXTRACT] {len(kept)} listings after filtering (from {len(listings)} raw)")
    return kept


def main():
    # Hard timeout — guarantee exit
    signal.signal(signal.SIGALRM, hard_timeout_handler)
    signal.alarm(MAX_RUNTIME_SECONDS)

    logger.info("=" * 55)
    logger.info(f"[START] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 55)

    seen_ids = load_seen_ids()
    logger.info(f"[STATE] {len(seen_ids)} previously seen listing IDs")

    from patchright.sync_api import sync_playwright  # noqa: PLC0415

    all_listings = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx_opts = {"viewport": {"width": 1920, "height": 1080}}
            if SESSION_FILE.exists():
                ctx_opts["storage_state"] = str(SESSION_FILE)
                logger.info(f"[SESSION] Loaded from {SESSION_FILE}")
            else:
                logger.warning("[SESSION] Not found — will scrape without login")

            context = browser.new_context(**ctx_opts)
            page = context.new_page()

            try:
                for entry in SEARCH_URLS:
                    url = entry["url"]
                    label = entry.get("label", "")
                    results = scrape(page, url, label)
                    for r in results:
                        r["_label"] = label
                    all_listings.extend(results)
                    logger.info(f"[URL] {label or url}: {len(results)} listings")
            finally:
                try:
                    browser.close()
                    logger.info("[BROWSER] Closed cleanly")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"[ERROR] Scraping failed: {e}")
        sys.exit(1)

    # Find new listings — deduplicate by listing_id (same item may appear in multiple search URLs)
    seen_new_ids: set = set()
    new_listings = []
    for l in all_listings:
        lid = l.get("listing_id")
        if lid and lid not in seen_ids and lid not in seen_new_ids:
            seen_new_ids.add(lid)
            new_listings.append(l)
    logger.info(f"[NEW] {len(new_listings)} new listings (out of {len(all_listings)} total)")

    if new_listings:
        for l in new_listings:
            label = f"[{l['_label']}] " if l.get("_label") else ""
            logger.info(f"  + {label}{l.get('title') or '(no title)'} — NZ${l.get('price', '?')} — {l.get('url', '')}")
        send_webhook(new_listings)
    else:
        logger.info("[OK] No new listings — nothing to send")

    # Update state: union of seen + all current IDs (so deleted listings don't re-alert)
    current_ids = {l["listing_id"] for l in all_listings if l.get("listing_id")}
    save_seen_ids(seen_ids | current_ids)
    logger.info(f"[STATE] Saved {len(seen_ids | current_ids)} total seen IDs ({len(SEARCH_URLS)} URL(s) monitored)")

    logger.info("[DONE] Exiting cleanly")
    signal.alarm(0)  # Cancel timeout


if __name__ == "__main__":
    main()
