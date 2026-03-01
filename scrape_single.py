#!/usr/bin/env python3
"""Scrape a single Facebook Marketplace listing."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace, parse_listing
from ai_marketplace_monitor.database import DatabaseManager, CarListing
from ai_marketplace_monitor.nz_filters import check_wof_and_rego, get_nz_car_priority, get_intercity_duration
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler
from rich import print as rprint

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("scraper")

# URL to scrape
TARGET_URL = "https://www.facebook.com/marketplace/item/1436610837829708/?ref=search&referral_code=null&referral_story_type=post&tracking=browse_serp%3A523b45e6-56c1-4b95-af8a-9cc839fefd74"

print("\n" + "="*80)
print(f"SCRAPING: {TARGET_URL}")
print("="*80 + "\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    marketplace = FacebookMarketplace("facebook", browser, logger=logger)

    # Load session
    storage_state_path = amm_home / "facebook_session.json"
    if storage_state_path.exists():
        from ai_marketplace_monitor.marketplace import MarketplaceConfig
        from ai_marketplace_monitor.utils import MonitorConfig

        # Create minimal config
        marketplace.config = type('obj', (object,), {
            'login_wait_time': 0,
            'monitor_config': None
        })()

        marketplace.login()

    # Navigate to listing
    if marketplace.page:
        marketplace.page.goto(TARGET_URL, timeout=30000)
        marketplace.page.wait_for_load_state("domcontentloaded")

        print("\n📄 Attempting to parse listing...\n")

        # Try to parse
        listing = parse_listing(marketplace.page, TARGET_URL, None, logger)

        if listing:
            print("✅ SUCCESSFULLY PARSED LISTING:\n")
            print(f"  🔗 URL: {listing.post_url}")
            print(f"  📝 Title: {listing.title}")
            print(f"  💰 Price: ${listing.price}")
            print(f"  📍 Location: {listing.location}")
            print(f"  👤 Seller: {listing.seller}")
            print(f"  ✨ Condition: {listing.condition}")
            print(f"  📄 Description: {listing.description[:200]}..." if listing.description else "  📄 Description: (empty)")
            print(f"  🖼️  Image: {listing.image[:80]}..." if listing.image else "  🖼️  Image: (none)")

            # Check WOF/Rego
            search_text = f"{listing.title} {listing.description}"
            has_wof, has_rego = check_wof_and_rego(search_text)

            print(f"\n🚗 NZ Car Metadata:")
            print(f"  WOF mentioned: {'✅ YES' if has_wof else '❌ NO'}")
            print(f"  Rego mentioned: {'✅ YES' if has_rego else '❌ NO'}")

            # Save to database
            print(f"\n💾 Saving to database...")
            db = DatabaseManager()

            car_listing = CarListing.from_listing(
                listing=listing,
                search_city="Auckland",
                has_wof_mention=has_wof,
                has_rego_mention=has_rego,
                intercity_duration="3h 45min",
                city_priority=1,
            )

            is_new = db.insert_car_listing(car_listing)
            print(f"  {'✅ Saved as NEW listing' if is_new else '⚠️  Already in database (duplicate)'}")

            # Show database stats
            stats = db.get_stats()
            print(f"\n📊 Database Stats:")
            print(f"  Total listings: {stats['total_listings']}")
            print(f"  WOF mentions: {stats['wof_mentions']}")
            print(f"  Rego mentions: {stats['rego_mentions']}")

        else:
            print("❌ FAILED TO PARSE - No parser matched the page layout")
            print("\nLet me show you what's on the page...\n")

            # Try to extract whatever we can find
            try:
                h1_elements = marketplace.page.query_selector_all("h1")
                print(f"Found {len(h1_elements)} H1 elements:")
                for i, h1 in enumerate(h1_elements[:5]):
                    text = h1.text_content()
                    print(f"  H1[{i}]: {text[:100]}")

                print(f"\nLooking for seller link...")
                seller_links = marketplace.page.query_selector_all("a[href*='marketplace/profile']")
                print(f"Found {len(seller_links)} seller profile links")
                for i, link in enumerate(seller_links[:3]):
                    print(f"  Seller[{i}]: {link.text_content()}")

                print(f"\nLooking for condition...")
                lis = marketplace.page.query_selector_all("li")
                condition_found = False
                for li in lis:
                    text = li.text_content() or ""
                    if "Condition" in text or "condition" in text:
                        print(f"  Found: {text[:100]}")
                        condition_found = True
                        break
                if not condition_found:
                    print(f"  No 'Condition' text found in {len(lis)} LI elements")

            except Exception as e:
                print(f"Error extracting page elements: {e}")

    input("\n\nPress Enter to close browser...")
    browser.close()

print("\n" + "="*80)
print("DONE")
print("="*80 + "\n")
