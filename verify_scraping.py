#!/usr/bin/env python3
"""Verify scraping of 3 specific listings for user to double-check."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from patchright.sync_api import sync_playwright
from ai_marketplace_monitor.facebook import FacebookMarketplace, parse_listing
from ai_marketplace_monitor.utils import amm_home
from rich.logging import RichHandler
from rich import print as rprint

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(markup=True, show_path=False, level=logging.INFO)],
)
logger = logging.getLogger("verify")

# 3 URLs to verify
TEST_URLS = [
    "https://www.facebook.com/marketplace/item/1436610837829708/",
    "https://www.facebook.com/marketplace/item/3171750023007118/",
    "https://www.facebook.com/marketplace/item/1569242467518413/",
]

print("\n" + "="*80)
print("VERIFICATION: Scraping 3 listings for manual verification")
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

    for i, url in enumerate(TEST_URLS, 1):
        print(f"\n{'='*80}")
        print(f"SAMPLE #{i}: {url}")
        print(f"{'='*80}\n")

        if marketplace.page:
            marketplace.page.goto(url, timeout=30000)
            marketplace.page.wait_for_load_state("domcontentloaded")

            listing = parse_listing(marketplace.page, url, None, logger)

            if listing:
                rprint(f"[green]✅ SUCCESSFULLY PARSED[/green]\n")
                rprint(f"[cyan]Title:[/cyan] {listing.title}")
                rprint(f"[cyan]Price:[/cyan] {listing.price}")
                rprint(f"[cyan]Location:[/cyan] {listing.location}")
                rprint(f"[cyan]Seller:[/cyan] {listing.seller}")
                rprint(f"[cyan]Condition:[/cyan] {listing.condition}")

                # Show first 300 chars of description
                desc = listing.description or "(empty)"
                if len(desc) > 300:
                    rprint(f"[cyan]Description:[/cyan] {desc[:300]}...")
                else:
                    rprint(f"[cyan]Description:[/cyan] {desc}")

                print(f"\n{'-'*80}\n")
                print(f"[bold]Please verify this data matches what you see at:[/bold]")
                print(f"[blue]{url}[/blue]\n")
            else:
                rprint(f"[red]❌ FAILED TO PARSE[/red]\n")

        # Wait a bit between requests
        marketplace.page.wait_for_timeout(2000)

    input("\n\nPress Enter to close browser and exit...")
    browser.close()

print("\n" + "="*80)
print("VERIFICATION COMPLETE - Please confirm if all 3 samples match Facebook data")
print("="*80 + "\n")
