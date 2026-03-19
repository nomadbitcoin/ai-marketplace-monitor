#!/usr/bin/env python3
"""Scrape Facebook Marketplace and append to existing CSV file."""

import sys
import csv
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace
from ai_marketplace_monitor.nz_filters import check_wof_and_rego
from ai_marketplace_monitor.utils import amm_home
from ai_marketplace_monitor.config import Config
from rich.logging import RichHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("scraper")

# Use existing CSV file
CSV_PATH = Path(__file__).parent / "data" / "nz_cars_20260302_110901.csv"

# CSV columns
CSV_COLUMNS = [
    "listing_id",
    "url",
    "title",
    "price",
    "location",
    "seller",
    "condition",
    "description",
    "has_wof",
    "has_rego",
    "scraped_at",
]

# Load config
config_files = [Path.home() / ".ai-marketplace-monitor" / "config.toml"]
config = Config(config_files, logger=logger)

marketplace_config = config.marketplace["facebook"]
item_config = list(config.item.values())[0]

print(f"\n{'='*80}")
print(f"APPENDING TO CSV: {CSV_PATH}")
print(f"Item: {item_config.name}")
print(f"Price: ${item_config.min_price} - ${item_config.max_price}")
print(f"Cities: Taupo, Wellington, New Plymouth (from config)")
print(f"{'='*80}\n")

# Read existing listing IDs to avoid duplicates
existing_ids = set()
if CSV_PATH.exists():
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_ids.add(row['listing_id'])
    print(f"📋 Found {len(existing_ids)} existing listings in CSV\n")

# Open CSV file in append mode
csv_file = open(CSV_PATH, 'a', newline='', encoding='utf-8')
csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)

count = 0
saved = 0
skipped = 0

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        marketplace = FacebookMarketplace("facebook", browser, logger=logger)
        marketplace.config = marketplace_config

        # Login
        marketplace.login()

        print("\n🔍 Starting search with 3 scrolls...\n")

        # Search and save each listing immediately
        for listing in marketplace.search(item_config):
            count += 1

            # Skip if already exists
            if listing.id in existing_ids:
                skipped += 1
                print(f"⏭️  [{count}] Skipped duplicate: {listing.title[:50]}... | ${listing.price}")
                continue

            # Check WOF/Rego
            search_text = f"{listing.title} {listing.description}"
            has_wof, has_rego = check_wof_and_rego(search_text)

            # Prepare CSV row
            row = {
                "listing_id": listing.id,
                "url": listing.post_url,
                "title": listing.title,
                "price": listing.price,
                "location": listing.location,
                "seller": listing.seller,
                "condition": listing.condition,
                "description": listing.description,
                "has_wof": "YES" if has_wof else "NO",
                "has_rego": "YES" if has_rego else "NO",
                "scraped_at": datetime.now().isoformat(),
            }

            # Write to CSV immediately
            csv_writer.writerow(row)
            csv_file.flush()  # Force write to disk
            saved += 1
            existing_ids.add(listing.id)  # Add to set to prevent duplicates in this run

            print(f"✅ [{count}] Saved: {listing.title[:50]}... | WOF:{has_wof} Rego:{has_rego} | ${listing.price}")

        browser.close()

except KeyboardInterrupt:
    print("\n\n⚠️  Interrupted by user")
except Exception as e:
    logger.error(f"Error during scraping: {e}")
    raise
finally:
    csv_file.close()
    print(f"\n{'='*80}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*80}")
    print(f"  Listings processed: {count}")
    print(f"  Rows saved to CSV: {saved}")
    print(f"  Duplicates skipped: {skipped}")
    print(f"  CSV file: {CSV_PATH}")
    print(f"{'='*80}\n")
