"""Facebook Marketplace CSS selectors — single file to update when Facebook changes layout.

Update these selectors when Facebook breaks the scraping. Each selector has a
comment explaining what it targets so you can inspect the page and fix it.

Last verified: 2026-03-03
"""

# ============================================================================
# LISTING SELECTORS
# ============================================================================

# The main link wrapping each marketplace listing card
LISTING_LINK = 'a[href*="/marketplace/item/"]'

# Container div that holds the grid of results (max-width ~1872px)
RESULTS_CONTAINER = 'div.x11t971q.xvc5jky.x1n2onr6'

# Individual listing card wrapper (each card in the grid)
LISTING_CARD = 'div.x9f619.x78zum5.x1r8uery.xdt5ytf.x1iyjqo2'

# ============================================================================
# PRICE SELECTORS
# ============================================================================

# Current/sale price — spans with font-size 17px, NOT strikethrough
# These contain text like "NZ$1.500"
PRICE_SPAN_STYLE = '--x-fontSize: 17px'

# Original price (crossed out) — has the strikethrough class
ORIGINAL_PRICE_CLASS = 'xk50ysn'

# ============================================================================
# TITLE / DESCRIPTION SELECTORS
# ============================================================================

# Title block — div with class xyqdw3p (15px font-size block with title text)
TITLE_CONTAINER_CLASS = 'xyqdw3p'
TITLE_SPAN_STYLE = '--x-fontSize: 15px'

# ============================================================================
# LOCATION SELECTORS
# ============================================================================

# Location text — spans with 13px font-size containing city name
LOCATION_SPAN_STYLE = '--x-fontSize: 13px'

# ============================================================================
# IMAGE SELECTORS
# ============================================================================

# Listing image — img inside the card
LISTING_IMAGE = 'img.x15mokao'

# ============================================================================
# SCROLL / PAGINATION SELECTORS
# ============================================================================

# "Results a bit further than your selection" — marks the boundary between
# primary and distant results. Text: "Resultados um pouco mais distantes..."
# This is a span inside a div with classes x11t971q xvc5jky x1n2onr6
DISTANT_RESULTS_TEXT = 'Resultados um pouco mais distantes'

# Alternative (English): "Results a little further than you selected"
DISTANT_RESULTS_TEXT_EN = 'Results a little further'

# Virtualized (not-yet-rendered) items indicator
VIRTUALIZED_ATTR = 'data-virtualized'
VIRTUALIZED_VALUE = 'true'

# Loading spinner indicator
LOADING_INDICATOR = '[role="status"][aria-label*="Carregando"], [role="status"][aria-label*="Loading"]'

# ============================================================================
# COOKIE / UI SELECTORS
# ============================================================================

# Cookie consent button patterns (regex)
COOKIE_BUTTON_PATTERNS = [
    r"Allow all cookies",
    r"Allow cookies",
    r"Accept All",
    r"Permitir todos os cookies",
    r"Permitir cookies",
]
