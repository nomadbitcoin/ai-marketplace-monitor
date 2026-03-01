"""Database module for storing scraped car listings in SQLite.

This module provides structured storage for Facebook Marketplace car listings,
enabling CSV export and deduplication across multi-city searches. Works alongside
diskcache for backwards compatibility.

NZ Car Scraper specific schema with WOF/Rego tracking.
"""

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .listing import Listing
from .utils import amm_home


@dataclass
class CarListing:
    """Car listing with NZ-specific fields (WOF/Rego tracking)."""

    listing_id: str
    url: str
    title: str
    price: float
    search_city: str
    actual_location: str
    distance_from_city_km: Optional[float] = None
    seller_profile_url: Optional[str] = None
    has_wof_mention: bool = False
    has_rego_mention: bool = False
    description: str = ""
    image_urls: str = ""  # JSON array as string
    scraped_at: Optional[str] = None
    intercity_duration: Optional[str] = None
    city_priority: Optional[int] = None
    condition: Optional[str] = None
    seller: Optional[str] = None

    @classmethod
    def from_listing(
        cls,
        listing: Listing,
        search_city: str,
        has_wof_mention: bool = False,
        has_rego_mention: bool = False,
        distance_km: Optional[float] = None,
        seller_profile_url: Optional[str] = None,
        intercity_duration: Optional[str] = None,
        city_priority: Optional[int] = None,
    ) -> "CarListing":
        """Create CarListing from generic Listing model."""
        # Extract numeric price from string (handle ranges like "NZ$2.000 | NZ$2.500")
        price_value = 0.0
        if listing.price:
            # Take first price if it's a range (separated by |)
            first_price = listing.price.split("|")[0].strip()
            # Remove currency symbols and extract number
            import re
            numbers = re.findall(r"[\d,.]+", first_price)
            if numbers:
                # Remove periods used as thousand separators in some locales
                # and convert commas to dots for decimal points
                num_str = numbers[0].replace(".", "").replace(",", ".")
                try:
                    price_value = float(num_str)
                except ValueError:
                    # If still can't convert, try without any replacements
                    try:
                        price_value = float(numbers[0].replace(",", ""))
                    except ValueError:
                        price_value = 0.0

        return cls(
            listing_id=listing.id,
            url=listing.post_url,
            title=listing.title,
            price=price_value,
            search_city=search_city,
            actual_location=listing.location,
            distance_from_city_km=distance_km,
            seller_profile_url=seller_profile_url,
            has_wof_mention=has_wof_mention,
            has_rego_mention=has_rego_mention,
            description=listing.description,
            image_urls=json.dumps([listing.image]) if listing.image else "[]",
            scraped_at=datetime.now().isoformat(),
            intercity_duration=intercity_duration,
            city_priority=city_priority,
            condition=listing.condition,
            seller=listing.seller,
        )


class DatabaseManager:
    """Manages SQLite database for car listings with CSV export capabilities."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.ai-marketplace-monitor/nz_cars.db
        """
        if db_path is None:
            db_path = amm_home / "nz_cars.db"

        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scraped_cars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    price REAL,
                    search_city TEXT,
                    actual_location TEXT,
                    distance_from_city_km REAL,
                    seller_profile_url TEXT,
                    has_wof_mention BOOLEAN DEFAULT 0,
                    has_rego_mention BOOLEAN DEFAULT 0,
                    description TEXT,
                    image_urls TEXT,
                    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    intercity_duration TEXT,
                    city_priority INTEGER,
                    condition TEXT,
                    seller TEXT
                )
                """
            )
            # Create indexes for efficient queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_listing_id ON scraped_cars(listing_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scraped_at ON scraped_cars(scraped_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_city ON scraped_cars(search_city)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_wof_rego ON scraped_cars(has_wof_mention, has_rego_mention)"
            )
            conn.commit()

    def insert_car_listing(self, car: CarListing) -> bool:
        """Insert or update car listing (deduplication by listing_id).

        Args:
            car: CarListing to insert

        Returns:
            True if inserted, False if duplicate (updated)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if listing already exists
            cursor.execute(
                "SELECT id, search_city, city_priority FROM scraped_cars WHERE listing_id = ?",
                (car.listing_id,),
            )
            existing = cursor.fetchone()

            if existing:
                # Update if new city has higher priority (lower number = higher priority)
                existing_priority = existing[2] if existing[2] is not None else 999
                new_priority = car.city_priority if car.city_priority is not None else 999

                if new_priority < existing_priority:
                    # Update with higher priority city
                    cursor.execute(
                        """
                        UPDATE scraped_cars
                        SET search_city = ?, city_priority = ?, scraped_at = ?
                        WHERE listing_id = ?
                        """,
                        (car.search_city, car.city_priority, car.scraped_at, car.listing_id),
                    )
                    conn.commit()

                return False  # Duplicate (updated or skipped)

            # Insert new listing
            cursor.execute(
                """
                INSERT INTO scraped_cars (
                    listing_id, url, title, price, search_city, actual_location,
                    distance_from_city_km, seller_profile_url, has_wof_mention,
                    has_rego_mention, description, image_urls, scraped_at,
                    intercity_duration, city_priority, condition, seller
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    car.listing_id,
                    car.url,
                    car.title,
                    car.price,
                    car.search_city,
                    car.actual_location,
                    car.distance_from_city_km,
                    car.seller_profile_url,
                    car.has_wof_mention,
                    car.has_rego_mention,
                    car.description,
                    car.image_urls,
                    car.scraped_at,
                    car.intercity_duration,
                    car.city_priority,
                    car.condition,
                    car.seller,
                ),
            )
            conn.commit()
            return True  # Newly inserted

    def get_listings_by_city(self, city: str) -> List[Dict[str, Any]]:
        """Get all listings for a specific search city.

        Args:
            city: Search city name

        Returns:
            List of car listings as dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scraped_cars WHERE search_city = ? ORDER BY scraped_at DESC",
                (city,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_listings(
        self,
        require_wof: bool = False,
        require_rego: bool = False,
        max_price: Optional[float] = None,
        cities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get all listings with optional filters.

        Args:
            require_wof: Only return listings with WOF mention
            require_rego: Only return listings with Rego mention
            max_price: Maximum price filter
            cities: Filter by specific cities

        Returns:
            List of car listings as dictionaries
        """
        query = "SELECT * FROM scraped_cars WHERE 1=1"
        params: List[Any] = []

        if require_wof:
            query += " AND has_wof_mention = 1"

        if require_rego:
            query += " AND has_rego_mention = 1"

        if max_price is not None:
            query += " AND price <= ?"
            params.append(max_price)

        if cities:
            placeholders = ",".join("?" * len(cities))
            query += f" AND search_city IN ({placeholders})"
            params.extend(cities)

        query += " ORDER BY scraped_at DESC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def export_to_csv(
        self,
        output_path: Path,
        require_wof: bool = False,
        require_rego: bool = False,
        max_price: Optional[float] = None,
        cities: Optional[List[str]] = None,
    ) -> int:
        """Export listings to CSV file.

        Args:
            output_path: Path to output CSV file
            require_wof: Only export listings with WOF mention
            require_rego: Only export listings with Rego mention
            max_price: Maximum price filter
            cities: Filter by specific cities

        Returns:
            Number of listings exported
        """
        listings = self.get_all_listings(
            require_wof=require_wof,
            require_rego=require_rego,
            max_price=max_price,
            cities=cities,
        )

        if not listings:
            return 0

        # Define CSV column order (exclude internal 'id' field)
        fieldnames = [
            "listing_id",
            "title",
            "price",
            "search_city",
            "actual_location",
            "distance_from_city_km",
            "seller_profile_url",
            "has_wof_mention",
            "has_rego_mention",
            "url",
            "intercity_duration",
            "condition",
            "seller",
            "image_urls",
            "description",
            "scraped_at",
        ]

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            for listing in listings:
                # Parse image_urls JSON array to pipe-delimited string
                try:
                    image_urls = json.loads(listing.get("image_urls", "[]"))
                    listing["image_urls"] = "|".join(image_urls)
                except (json.JSONDecodeError, TypeError):
                    listing["image_urls"] = ""

                writer.writerow(listing)

        return len(listings)

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with database stats
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM scraped_cars")
            total_listings = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM scraped_cars WHERE has_wof_mention = 1")
            wof_listings = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM scraped_cars WHERE has_rego_mention = 1")
            rego_listings = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM scraped_cars WHERE has_wof_mention = 1 AND has_rego_mention = 1"
            )
            both_listings = cursor.fetchone()[0]

            cursor.execute(
                "SELECT search_city, COUNT(*) FROM scraped_cars GROUP BY search_city ORDER BY COUNT(*) DESC"
            )
            by_city = dict(cursor.fetchall())

            return {
                "total_listings": total_listings,
                "wof_mentions": wof_listings,
                "rego_mentions": rego_listings,
                "wof_and_rego": both_listings,
                "by_city": by_city,
            }
