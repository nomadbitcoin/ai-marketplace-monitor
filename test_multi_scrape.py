#!/usr/bin/env python3
"""Test script to scrape multiple Auckland car listings and save to database."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace
from ai_marketplace_monitor.database import DatabaseManager, CarListing
from ai_marketplace_monitor.nz_filters import check_wof_and_rego
from ai_marketplace_monitor.utils import amm_home
from ai_marketplace_monitor.config import Config
from rich.logging import RichHandler
from rich import print as rprint

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("scraper")

# Load config
config_files = [Path.home() / ".ai-marketplace-monitor" / "config.toml"]
config = Config(config_files, logger=logger)

# Get marketplace and item configs
marketplace_config = config.marketplace["facebook"]
item_config = list(config.item.values())[0]

print(f"\n{'='*80}")
print(f"TESTING MULTI-LISTING SCRAPER")
print(f"Item: {item_config.name}")
print(f"Search: {item_config.search_phrases}")
print(f"Price: ${item_config.min_price} - ${item_config.max_price}")
print(f"{'='*80}\n")

# Initialize database
db = DatabaseManager()
initial_stats = db.get_stats()
print(f"📊 Initial Database Stats: {initial_stats['total_listings']} listings\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    marketplace = FacebookMarketplace("facebook", browser, logger=logger)
    marketplace.config = marketplace_config

    # Load session
    marketplace.login()

    print("\n🔍 Starting search...\n")

    # Search and save listings
    count = 0
    saved = 0
    for listing in marketplace.search(item_config):
        count += 1
        print(f"\n{'='*80}")
        print(f"LISTING #{count}")
        print(f"{'='*80}")
        print(f"  🔗 URL: {listing.post_url}")
        print(f"  📝 Title: {listing.title}")
        print(f"  💰 Price: ${listing.price}")
        print(f"  📍 Location: {listing.location}")
        print(f"  👤 Seller: {listing.seller}")

        # Check WOF/Rego
        search_text = f"{listing.title} {listing.description}"
        has_wof, has_rego = check_wof_and_rego(search_text)
        print(f"  🚗 WOF: {'✅' if has_wof else '❌'} | Rego: {'✅' if has_rego else '❌'}")

        # Save to database
        car_listing = CarListing.from_listing(
            listing=listing,
            search_city="Auckland",
            has_wof_mention=has_wof,
            has_rego_mention=has_rego,
            intercity_duration="N/A",
            city_priority=1,
        )

        is_new = db.insert_car_listing(car_listing)
        if is_new:
            saved += 1
            print(f"  💾 Saved to database")
        else:
            print(f"  ⚠️  Already in database (duplicate)")

        print(f"{'='*80}\n")

        if count >= 10:  # Stop after 10 listings
            print(f"\n✋ Stopping after {count} listings\n")
            break

    browser.close()

    # Show final stats
    final_stats = db.get_stats()
    print(f"\n{'='*80}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*80}")
    print(f"  Listings processed: {count}")
    print(f"  New listings saved: {saved}")
    print(f"  Duplicates skipped: {count - saved}")
    print(f"\n📊 Final Database Stats:")
    print(f"  Total listings: {final_stats['total_listings']}")
    print(f"  WOF mentions: {final_stats['wof_mentions']}")
    print(f"  Rego mentions: {final_stats['rego_mentions']}")
    print(f"  Both WOF & Rego: {final_stats['wof_and_rego']}")
    print(f"{'='*80}\n")
