#!/usr/bin/env python3
"""Test script to scrape a single Facebook Marketplace listing."""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ai_marketplace_monitor.monitor import MarketplaceMonitor
from ai_marketplace_monitor.facebook import FacebookMarketplace
from ai_marketplace_monitor.config import Config
from rich.logging import RichHandler

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.DEBUG)],
)
logger = logging.getLogger("test")

# Load config
config_files = [Path.home() / ".ai-marketplace-monitor" / "config.toml"]
config = Config.load_config(config_files, logger=logger)

# Get marketplace config
marketplace_config = config.marketplaces.get("facebook")
if not marketplace_config:
    print("No facebook marketplace config found")
    sys.exit(1)

# Get first item config
item_configs = list(config.items.values())
if not item_configs:
    print("No item configs found")
    sys.exit(1)

item_config = item_configs[0]
print(f"\n=== Testing with item: {item_config.name} ===\n")

# Create monitor and marketplace
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # Show browser for debugging

    marketplace = FacebookMarketplace("facebook", browser, logger=logger)
    marketplace.config = marketplace_config

    # Login (or use saved session)
    marketplace.login()

    print("\n=== Starting search ===\n")

    # Search and get first listing
    count = 0
    for listing in marketplace.search(item_config):
        count += 1
        print(f"\n{'='*80}")
        print(f"LISTING #{count}")
        print(f"{'='*80}")
        print(f"URL: {listing.post_url}")
        print(f"Title: {listing.title}")
        print(f"Price: ${listing.price}")
        print(f"Location: {listing.location}")
        print(f"Seller: {listing.seller}")
        print(f"Condition: {listing.condition}")
        print(f"Description: {listing.description[:200]}..." if listing.description else "Description: (empty)")
        print(f"{'='*80}\n")

        if count >= 1:  # Stop after first successful listing
            break

    browser.close()

    if count == 0:
        print("❌ No listings successfully scraped")
    else:
        print(f"✅ Successfully scraped {count} listing(s)")
