#!/usr/bin/env python3
"""Facebook Groups scraper using JavaScript evaluation to extract data from rendered DOM."""

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
print("FACEBOOK GROUPS SCRAPER - JavaScript Evaluation Method")
print("=" * 80 + "\n")

# JavaScript to extract post data from the rendered page
EXTRACT_POSTS_JS = """
() => {
    const posts = [];

    // Try different selectors to find posts
    const postSelectors = [
        'div[role="article"]',
        '[data-pagelet*="FeedUnit"]',
        '[data-pagelet*="GroupPost"]',
        'div[class*="story"]',
    ];

    let postElements = [];
    for (const selector of postSelectors) {
        postElements = document.querySelectorAll(selector);
        if (postElements.length > 0) {
            console.log(`Found ${postElements.length} elements with selector: ${selector}`);
            break;
        }
    }

    postElements.forEach((element, index) => {
        const post = {
            index,
            text_length: 0,
            title: '',
            description: '',
            url: '',
            price: '',
            has_links: false,
            link_count: 0,
        };

        // Get all text content
        const allText = element.textContent || '';
        post.text_length = allText.length;
        post.description = allText.substring(0, 500); // First 500 chars

        // Extract first line as title
        const lines = allText.split('\\n').filter(l => l.trim().length > 10);
        if (lines.length > 0) {
            post.title = lines[0].substring(0, 200);
        }

        // Find links
        const links = element.querySelectorAll('a');
        post.link_count = links.length;
        post.has_links = links.length > 0;

        // Try to find post URL
        for (const link of links) {
            const href = link.getAttribute('href');
            if (href && (href.includes('/posts/') || href.includes('/permalink/') || href.includes('/groups/'))) {
                post.url = href.startsWith('/') ? `https://www.facebook.com${href}` : href;
                break;
            }
        }

        // Extract price using regex
        const pricePatterns = [
            /\\$\\s*(\\d{1,3}(?:[,\\.]\\d{3})*)/g,
            /(\\d{1,3}(?:[,\\.]\\d{3})*)\\s*(?:dollars?|usd|\\$)/gi,
        ];

        for (const pattern of pricePatterns) {
            const matches = allText.match(pattern);
            if (matches && matches.length > 0) {
                // Clean up and extract number
                const priceStr = matches[0].replace(/[^\\d]/g, '');
                const priceVal = parseInt(priceStr);
                if (priceVal >= 100 && priceVal <= 100000) {
                    post.price = priceVal.toString();
                    break;
                }
            }
        }

        posts.push(post);
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

    # Scroll to load posts
    logger.info("📜 Scrolling to trigger post loading...")
    for i in range(3):
        page.evaluate(f"window.scrollTo(0, {(i + 1) * 500})")
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

    # Extract posts using JavaScript
    logger.info("\n🔍 Extracting posts using JavaScript evaluation...")
    try:
        posts_data = page.evaluate(EXTRACT_POSTS_JS)

        print("\n" + "=" * 80)
        print(f"EXTRACTION COMPLETE - Found {len(posts_data)} elements")
        print("=" * 80 + "\n")

        for post in posts_data:
            print(f"\n📄 POST #{post['index'] + 1}:")
            print(f"  📏 Text length: {post['text_length']} chars")
            print(f"  🔗 Links found: {post['link_count']}")
            print(f"  🔗 URL: {post['url'] or '(not found)'}")
            print(f"  📝 Title: {post['title'] or '(not found)'}")
            print(f"  💰 Price: ${post['price'] or '(not found)'}")
            print(f"  📄 Description preview: {post['description'][:150]}...")

        # Filter to posts with actual content
        real_posts = [p for p in posts_data if p['text_length'] > 100]
        print(f"\n✅ Posts with content (>100 chars): {len(real_posts)}")

        if real_posts:
            print("\n🎉 SUCCESS! Extraction working!")
            print("\nFirst valid post details:")
            first = real_posts[0]
            print(json.dumps(first, indent=2))

    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()

    # Save session
    if not storage_state_path.exists():
        try:
            context.storage_state(path=str(storage_state_path))
            logger.info(f"✅ Session saved")
        except Exception as e:
            logger.warning(f"Failed to save session: {e}")

    logger.info("\n⏸️  Browser will remain open for 90 seconds for inspection...")
    time.sleep(90)

    logger.info("Closing browser...")
    browser.close()

print("\n" + "=" * 80)
print("DONE")
print("=" * 80 + "\n")
