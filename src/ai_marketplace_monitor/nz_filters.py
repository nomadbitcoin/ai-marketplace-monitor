"""NZ-specific filtering utilities for car scraper.

Provides WOF (Warrant of Fitness) and Rego (Vehicle Registration) detection
for NZ car marketplace listings.
"""

import re
from typing import Tuple


def check_wof_mention(text: str) -> bool:
    """Check if text contains WOF (Warrant of Fitness) mention.

    Args:
        text: Text to search (title + description)

    Returns:
        True if WOF mention found, False otherwise

    Examples:
        >>> check_wof_mention("Car with 6 months WOF")
        True
        >>> check_wof_mention("Has current warrant of fitness")
        True
        >>> check_wof_mention("WOF due soon")
        True
        >>> check_wof_mention("Great condition")
        False
    """
    if not text:
        return False

    # Case-insensitive patterns for WOF mentions
    wof_patterns = [
        r"\bwof\b",  # "WOF" as whole word
        r"\bwarrant\s+of\s+fitness\b",  # "warrant of fitness"
        r"\bwarrant\b",  # "warrant" (often implies WOF in NZ car context)
    ]

    text_lower = text.lower()

    for pattern in wof_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


def check_rego_mention(text: str) -> bool:
    """Check if text contains Rego (Vehicle Registration) mention.

    Args:
        text: Text to search (title + description)

    Returns:
        True if Rego mention found, False otherwise

    Examples:
        >>> check_rego_mention("Car with 6 months rego")
        True
        >>> check_rego_mention("Registration paid until Dec")
        True
        >>> check_rego_mention("Fully registered")
        True
        >>> check_rego_mention("Needs work")
        False
    """
    if not text:
        return False

    # Case-insensitive patterns for Rego mentions
    rego_patterns = [
        r"\brego\b",  # "rego" as whole word
        r"\bregistration\b",  # "registration"
        r"\bregistered\b",  # "registered"
        r"\breg\b",  # "reg" (common abbreviation)
    ]

    text_lower = text.lower()

    for pattern in rego_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


def check_wof_and_rego(text: str) -> Tuple[bool, bool]:
    """Check for both WOF and Rego mentions.

    Args:
        text: Text to search (title + description)

    Returns:
        Tuple of (has_wof, has_rego)

    Examples:
        >>> check_wof_and_rego("Car with WOF and rego")
        (True, True)
        >>> check_wof_and_rego("Has WOF only")
        (True, False)
        >>> check_wof_and_rego("Registered vehicle")
        (False, True)
    """
    return (check_wof_mention(text), check_rego_mention(text))


def get_nz_car_priority(search_city: str) -> int:
    """Get priority ranking for NZ city (lower number = higher priority).

    Args:
        search_city: City name (Auckland, Hamilton, Rotorua, Napier, Wellington)

    Returns:
        Priority number (1-5), or 999 if unknown city

    Priority order per PRD:
        1. Auckland (closest to Tauranga via Intercity)
        2. Hamilton
        3. Rotorua
        4. Napier
        5. Wellington
    """
    city_priorities = {
        "auckland": 1,
        "104080336295923": 2,  # Hamilton Facebook ID
        "hamilton": 2,
        "rotorua": 3,
        "napier": 4,
        "wellington": 5,
    }

    city_lower = search_city.lower()
    return city_priorities.get(city_lower, 999)


def get_intercity_duration(search_city: str) -> str:
    """Get estimated Intercity bus duration from Tauranga to city.

    Args:
        search_city: City name

    Returns:
        Estimated duration string (e.g., "3h 45min")

    Duration estimates per PRD (from Tauranga):
        - Auckland: 3h 45min
        - Hamilton: 1h 50min
        - Rotorua: 1h 20min
        - Napier: ~4h (via Rotorua)
        - Wellington: ~8h (long journey)
    """
    durations = {
        "auckland": "3h 45min",
        "hamilton": "1h 50min",
        "104080336295923": "1h 50min",  # Hamilton FB ID
        "rotorua": "1h 20min",
        "napier": "4h 0min",
        "wellington": "8h 0min",
    }

    city_lower = search_city.lower()
    return durations.get(city_lower, "Unknown")
