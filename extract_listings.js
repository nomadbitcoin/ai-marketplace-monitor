() => {
    const listings = [];
    const seen_urls = new Set();

    const LISTING_LINK = '__LISTING_LINK__';
    const PRICE_STYLE = '__PRICE_SPAN_STYLE__';
    const STRIKE_CLASS = '__ORIGINAL_PRICE_CLASS__';
    const TITLE_CLASS = '__TITLE_CONTAINER_CLASS__';
    const TITLE_STYLE = '__TITLE_SPAN_STYLE__';
    const LOCATION_STYLE = '__LOCATION_SPAN_STYLE__';
    const DISTANT_TEXT = '__DISTANT_RESULTS_TEXT__';
    const DISTANT_TEXT_EN = '__DISTANT_RESULTS_TEXT_EN__';

    // Find the distant results header element once — use DOM order comparison
    let distantHeader = null;
    for (const s of document.querySelectorAll('span')) {
        const t = (s.textContent || '').trim();
        if (t.includes(DISTANT_TEXT) || t.includes(DISTANT_TEXT_EN)) {
            distantHeader = s;
            break;
        }
    }

    const links = document.querySelectorAll(LISTING_LINK);

    links.forEach((link) => {
        try {
            const href = link.getAttribute('href');
            if (!href) return;

            const url = href.startsWith('http')
                ? href.split('?')[0]
                : 'https://www.facebook.com' + href.split('?')[0];

            if (seen_urls.has(url)) return;
            seen_urls.add(url);

            // --- LISTING ID ---
            const idMatch = url.match(/\/item\/(\d+)/);
            const listing_id = idMatch ? idMatch[1] : '';

            // --- PRICE ---
            let price = '';
            let original_price = '';
            const spans = link.querySelectorAll('span');
            for (const span of spans) {
                const style = span.getAttribute('style') || '';
                const text = (span.textContent || '').trim();
                if (style.includes(PRICE_STYLE)) {
                    const m = text.match(/NZ\$\s*([\d.,]+)/i) || text.match(/\$\s*([\d.,]+)/);
                    if (m) {
                        const cleaned = m[1].replace(/[.,]/g, '');
                        const cls = span.className || '';
                        if (cls.includes(STRIKE_CLASS)) {
                            if (!original_price) original_price = cleaned;
                        } else {
                            if (!price) price = cleaned;
                        }
                    }
                }
            }

            // --- TITLE ---
            // .xyqdw3p is inside the <a> link (inside aria-hidden span)
            let title = '';
            for (const tc of link.querySelectorAll('.' + TITLE_CLASS)) {
                for (const ts of tc.querySelectorAll('span')) {
                    const style = ts.getAttribute('style') || '';
                    if (style.includes(TITLE_STYLE)) {
                        const t = (ts.textContent || '').trim();
                        if (t.length > 2 && t.length < 200) {
                            title = t;
                            break;
                        }
                    }
                }
                if (title) break;
            }

            // Fallback: img alt "TITLE no grupo LOCATION"
            if (!title) {
                const img = link.querySelector('img');
                if (img) {
                    const alt = (img.getAttribute('alt') || '').trim();
                    const m = alt.match(/^(.+?)\s+no grupo/i);
                    if (m && m[1].trim().length > 2) title = m[1].trim();
                }
            }

            // --- LOCATION ---
            let location = '';
            for (const span of spans) {
                const style = span.getAttribute('style') || '';
                if (style.includes(LOCATION_STYLE)) {
                    const text = (span.textContent || '').trim();
                    if (text
                        && !text.startsWith('NZ$') && !text.startsWith('$')
                        && text.length > 2 && text.length < 100
                        && !/^\d/.test(text)
                        && !text.includes('mil milhas')
                        && !text.includes('km')
                    ) {
                        location = text;
                        break;
                    }
                }
            }

            // Fallback: location from img alt
            if (!location) {
                const img = link.querySelector('img');
                if (img) {
                    const alt = img.getAttribute('alt') || '';
                    const m = alt.match(/no grupo\s+(.+)/i);
                    if (m) location = m[1].trim();
                }
            }

            // --- IMAGE ---
            let image = '';
            const img = link.querySelector('img');
            if (img) image = img.getAttribute('src') || '';

            // --- MILEAGE ---
            let mileage = '';
            for (const span of spans) {
                const text = (span.textContent || '').trim();
                if (/mil\s*milhas|km/i.test(text) && text.length < 30) {
                    mileage = text;
                    break;
                }
            }

            // --- IS DISTANT ---
            // Use DOM order: if the distant header appears BEFORE this link
            // in document order, this listing is in the distant section.
            let is_distant = false;
            if (distantHeader) {
                const position = distantHeader.compareDocumentPosition(link);
                // DOCUMENT_POSITION_FOLLOWING = 4 means link comes after header
                is_distant = !!(position & Node.DOCUMENT_POSITION_FOLLOWING);
            }

            listings.push({ listing_id, url, price, original_price, title, location, image, mileage, is_distant });

        } catch (e) {
            // skip
        }
    });

    return listings;
}
