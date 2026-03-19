#!/usr/bin/env python3
"""Continuous Facebook Groups scraper - saves to CSV incrementally."""

import sys
import logging
import time
import re
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("groups_scraper")

GROUP_URL = "https://www.facebook.com/groups/kiwicars.nz.tauranga/"
MAX_PRICE = 2000  # Only cars $2000 or less
CSV_FILE = Path(__file__).parent / f"data/cars_900_to_{MAX_PRICE}.csv"

print("\n" + "=" * 80)
print(f"CONTINUOUS SCRAPER - CARS UNDER ${MAX_PRICE}")
print("=" * 80 + "\n")


def is_valid_sale_post(text: str, price: str) -> bool:
    """Filter out non-sale posts."""
    text_lower = text.lower()

    if "stolen" in text_lower:
        return False

    if price in ["123", "456", "123456"]:
        return False

    if price:
        try:
            price_val = int(price)
            # Filter for cars > $900 and <= MAX_PRICE (avoid fake offers below $900)
            if price_val <= 900 or price_val > MAX_PRICE:
                return False
        except ValueError:
            return False

    return True


def clean_text(text: str) -> str:
    """Clean UI noise from text."""
    text = re.sub(r'Facebook{3,}', '', text)  # Remove repeated Facebook
    text = re.sub(r'Enviar mensagem.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'pPGRT.*', '', text)
    text = re.sub(r'[A-Za-z0-9]{6,}\.com', '', text)  # Remove random domain names
    text = text.replace('\u00a0', ' ')  # Replace non-breaking spaces
    text = ' '.join(text.split())  # Normalize whitespace
    return text.strip()


def extract_listings(page, logger):
    """Extract car posts using JavaScript."""

    js_code = """
    () => {
        const listings = new Map();
        const allDivs = document.querySelectorAll('div');
        const pricePattern = /NZ?\\$\\s*[\\d,]+/;

        allDivs.forEach(div => {
            const text = div.textContent || '';
            if (!pricePattern.test(text) || text.length < 100 || text.length > 3000) {
                return;
            }

            let price = '';
            const priceMatches = text.match(/NZ?\\$\\s*([\\d,\\.]+)/i);
            if (priceMatches) {
                price = priceMatches[1].replace(/[,\\.]/g, '');
            }

            let url = '';
            let currentEl = div;
            for (let i = 0; i < 5; i++) {
                const links = currentEl.querySelectorAll('a');
                for (const link of links) {
                    const href = link.getAttribute('href');
                    if (href && href.includes('/commerce/listing/')) {
                        url = href.startsWith('http') ? href : `https://www.facebook.com${href}`;
                        url = url.split('?')[0];
                        break;
                    }
                }
                if (url || !currentEl.parentElement) break;
                currentEl = currentEl.parentElement;
            }

            let title = '';
            const titlePatterns = [
                /(\\d{4}\\s+[A-Z][A-Z\\s]+(?:FIT|CIVIC|COROLLA|MAZDA|HONDA|TOYOTA|NISSAN|FORD|HOLDEN)[A-Z\\s]*)/i,
            ];
            for (const pattern of titlePatterns) {
                const match = text.match(pattern);
                if (match) {
                    title = match[1].trim().substring(0, 100);
                    break;
                }
            }

            let location = '';
            const locationMatch = text.match(/Auckland|Wellington|Christchurch|Hamilton|Tauranga/i);
            if (locationMatch) {
                location = locationMatch[0];
            }

            const uniqueKey = url ? url : (price + title.substring(0, 30));

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
        valid_listings = []

        for listing in raw_listings:
            if is_valid_sale_post(listing.get('description', ''), listing.get('price', '')):
                listing['title'] = clean_text(listing.get('title', ''))
                listing['description'] = clean_text(listing.get('description', ''))
                valid_listings.append(listing)

        return valid_listings
    except Exception as e:
        logger.error(f"Error extracting listings: {e}")
        return []


def save_to_csv(listings, csv_file):
    """Save listings to CSV file."""
    csv_file.parent.mkdir(exist_ok=True)

    # Read existing URLs to avoid duplicates
    existing_urls = set()
    if csv_file.exists():
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_urls.add(row['url'])

    # Append new listings
    new_count = 0
    mode = 'a' if csv_file.exists() else 'w'
    with open(csv_file, mode, newline='', encoding='utf-8') as f:
        fieldnames = ['timestamp', 'title', 'price', 'location', 'url', 'description']
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if mode == 'w':
            writer.writeheader()

        for listing in listings:
            url = listing.get('url', '')
            if url and url not in existing_urls:
                writer.writerow({
                    'timestamp': datetime.now().isoformat(),
                    'title': listing.get('title', ''),
                    'price': listing.get('price', ''),
                    'location': listing.get('location', ''),
                    'url': url,
                    'description': listing.get('description', '')[:500],  # Limit description
                })
                existing_urls.add(url)
                new_count += 1

    return new_count


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

    logger.info(f"\n💾 CSV file: {CSV_FILE}")
    logger.info(f"💰 Max price filter: ${MAX_PRICE}")
    logger.info("\n🔄 Starting continuous scrolling... (Press Ctrl+C to stop)\n")

    def count_listings():
        return page.evaluate("""
            () => document.querySelectorAll('a[href*="/commerce/listing/"]').length
        """)

    total_saved = 0
    scroll_count = 0

    try:
        while True:  # Infinite loop until user stops
            # Scroll to bottom
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            scroll_count += 1
            current_count = count_listings()

            logger.info(f"📜 Scroll #{scroll_count}: {current_count} total listings on page")

            # Click "Ver mais" buttons
            try:
                see_more_buttons = page.get_by_text(re.compile(r"(See more|Ver mais)", re.IGNORECASE)).all()
                clicked = 0
                for button in see_more_buttons[:20]:
                    try:
                        if button.is_visible(timeout=300):
                            button.click()
                            clicked += 1
                            time.sleep(0.1)
                    except:
                        pass
                if clicked > 0:
                    logger.info(f"  ✅ Expanded {clicked} descriptions")
                    time.sleep(1)
            except:
                pass

            # Extract and save
            listings = extract_listings(page, logger)
            new_saved = save_to_csv(listings, CSV_FILE)
            total_saved += new_saved

            if new_saved > 0:
                logger.info(f"  💾 Saved {new_saved} new cars (Total: {total_saved} cars under ${MAX_PRICE})")

            # Small pause before next scroll
            time.sleep(2)

    except KeyboardInterrupt:
        logger.info("\n\n⏹️  Stopped by user")

    logger.info(f"\n📊 FINAL RESULTS:")
    logger.info(f"   Total scrolls: {scroll_count}")
    logger.info(f"   Total cars saved: {total_saved}")
    logger.info(f"   CSV file: {CSV_FILE}")

    logger.info("\n⏸️  Browser will remain open for 30 seconds...")
    time.sleep(30)

    logger.info("Closing browser...")
    browser.close()

print("\n" + "=" * 80)
print("DONE")
print("=" * 80 + "\n")
