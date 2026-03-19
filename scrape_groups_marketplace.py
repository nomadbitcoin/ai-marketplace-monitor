#!/usr/bin/env python3
"""Facebook Groups scraper for marketplace listings."""

import sys
import logging
import time
import re
import json
from pathlib import Path

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
print("FACEBOOK GROUPS MARKETPLACE SCRAPER")
print("=" * 80 + "\n")

# JavaScript to extract marketplace listing data
EXTRACT_MARKETPLACE_JS = """
() => {
    const posts = [];

    // Look for marketplace cards - they usually have specific patterns
    // Try multiple approaches to find the listings

    // Approach 1: Look for elements with price patterns (NZ$, $, etc.)
    const allElements = document.querySelectorAll('div');
    const pricePattern = /NZ?\$\s*[\d,]+/;
    const potentialCards = new Set();

    allElements.forEach(el => {
        const text = el.textContent || '';
        if (pricePattern.test(text) && text.length > 50 && text.length < 2000) {
            // Found an element with a price - this might be a card
            potentialCards.add(el);
        }
    });

    console.log(`Found ${potentialCards.size} potential marketplace cards with prices`);

    // Approach 2: Look for common marketplace card patterns
    const cardSelectors = [
        'a[href*="/marketplace/item/"]',
        'a[href*="/groups/"][href*="/permalink/"]',
        '[data-testid*="marketplace"]',
        'div[class*="listing"]',
        'div[class*="card"]',
    ];

    cardSelectors.forEach(selector => {
        try {
            const elements = document.querySelectorAll(selector);
            if (elements.length > 0) {
                console.log(`Selector "${selector}" found ${elements.length} elements`);
                elements.forEach(el => {
                    // Get parent that contains the full card
                    let card = el;
                    for (let i = 0; i < 10; i++) {
                        if (card.parentElement) card = card.parentElement;
                        const text = card.textContent || '';
                        if (text.length > 100 && text.length < 3000) {
                            potentialCards.add(card);
                            break;
                        }
                    }
                });
            }
        } catch (e) {
            console.log(`Error with selector ${selector}: ${e.message}`);
        }
    });

    console.log(`Total unique potential cards: ${potentialCards.size}`);

    // Extract data from each potential card
    potentialCards.forEach((card, index) => {
        const post = {
            index,
            title: '',
            description: '',
            url: '',
            price: '',
            location: '',
            raw_text: '',
        };

        const allText = card.textContent || '';
        post.raw_text = allText;
        post.description = allText;

        // Extract price - look for NZ$ or $ followed by numbers
        const pricePatterns = [
            /NZ\$\s*([\d,]+)/i,
            /\$\s*([\d,]+)/,
            /([\d,]+)\s*(?:dollars?|nzd)/i,
        ];

        for (const pattern of pricePatterns) {
            const match = allText.match(pattern);
            if (match) {
                const priceStr = match[1].replace(/,/g, '');
                const priceVal = parseInt(priceStr);
                if (priceVal >= 100 && priceVal <= 100000) {
                    post.price = priceStr;
                    break;
                }
            }
        }

        // Extract title - look for car models/years
        const titlePatterns = [
            /(\d{4}\s+[A-Z][A-Z\s]+(?:FIT|CIVIC|COROLLA|MAZDA|HONDA|TOYOTA|NISSAN|FORD|HOLDEN)[A-Z\s]*)/i,
            /([A-Z][A-Z\s]+(?:FIT|CIVIC|COROLLA|MAZDA|HONDA|TOYOTA|NISSAN|FORD|HOLDEN)[A-Z\s]*\s+\d{4})/i,
        ];

        for (const pattern of titlePatterns) {
            const match = allText.match(pattern);
            if (match) {
                post.title = match[1].trim().substring(0, 200);
                break;
            }
        }

        // If no title found, use first substantial line
        if (!post.title) {
            const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 5 && l.length < 100);
            if (lines.length > 0) {
                // Skip common metadata lines
                for (const line of lines) {
                    if (!line.match(/^\d+\s*min/) && !line.match(/^(WOF|REGO|KMS)/i)) {
                        post.title = line.substring(0, 200);
                        break;
                    }
                }
            }
        }

        // Extract location
        const locationPattern = /AUCKLAND|WELLINGTON|CHRISTCHURCH|HAMILTON|TAURANGA|DUNEDIN|PALMERSTON NORTH|NAPIER|ROTORUA|NEW PLYMOUTH/i;
        const locationMatch = allText.match(locationPattern);
        if (locationMatch) {
            post.location = locationMatch[0];
        }

        // Find URL - look for links within the card
        const links = card.querySelectorAll('a');
        for (const link of links) {
            const href = link.getAttribute('href');
            if (href && (href.includes('/marketplace/') || href.includes('/groups/') || href.includes('/permalink/'))) {
                post.url = href.startsWith('http') ? href : `https://www.facebook.com${href}`;
                break;
            }
        }

        // Only add if we found some useful data
        if (post.price || post.title || allText.length > 100) {
            posts.push(post);
        }
    });

    return posts;
}
"""

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

    # Scroll to load listings
    logger.info("📜 Scrolling to trigger listing loading...")
    for i in range(3):
        page.evaluate(f"window.scrollTo(0, {(i + 1) * 600})")
        time.sleep(2)

    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    # Click "See more" buttons
    try:
        see_more_pattern = re.compile(r"(See more|Ver mais)", re.IGNORECASE)
        see_more_buttons = page.get_by_text(see_more_pattern).all()
        clicked = 0
        for button in see_more_buttons[:5]:
            try:
                if button.is_visible(timeout=1000):
                    button.click()
                    clicked += 1
                    time.sleep(0.5)
            except:
                pass
        if clicked > 0:
            logger.info(f"✅ Clicked {clicked} 'See more' buttons")
            time.sleep(2)
    except:
        pass

    # Extract marketplace listings
    logger.info("\n🔍 Extracting marketplace listings...")
    try:
        posts_data = page.evaluate(EXTRACT_MARKETPLACE_JS)

        print("\n" + "=" * 80)
        print(f"EXTRACTION COMPLETE - Found {len(posts_data)} listings")
        print("=" * 80 + "\n")

        for idx, post in enumerate(posts_data, 1):
            print(f"\n🚗 LISTING #{idx}:")
            print(f"  📝 Title: {post.get('title', '') or '(not found)'}")
            print(f"  💰 Price: ${post.get('price', '') or '(not found)'}")
            print(f"  📍 Location: {post.get('location', '') or '(not found)'}")
            url = post.get('url', '')
            print(f"  🔗 URL: {url[:80] if url else '(not found)'}")
            raw_text = post.get('raw_text', '')
            print(f"  📄 Description length: {len(raw_text)} chars")
            if raw_text:
                print(f"  📄 Preview: {raw_text[:200]}...")

        # Filter to valid listings
        valid_posts = [p for p in posts_data if p['price'] or (p['title'] and len(p['raw_text']) > 100)]
        print(f"\n✅ Valid listings with price or substantial content: {len(valid_posts)}")

        if valid_posts:
            print("\n🎉 SUCCESS! Here's the first valid listing:")
            first = valid_posts[0]
            print(json.dumps(first, indent=2))

    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()

    logger.info("\n⏸️  Browser will remain open for 90 seconds for inspection...")
    time.sleep(90)

    logger.info("Closing browser...")
    browser.close()

print("\n" + "=" * 80)
print("DONE")
print("=" * 80 + "\n")
