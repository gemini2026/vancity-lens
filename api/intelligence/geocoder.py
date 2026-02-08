"""
VCL-84: Geocoding accuracy improvement for VanCity Lens

Provides geocoding services using Vancouver parcels table as primary source.
Implements exact match, fuzzy match, and regex-based address extraction.
"""

import logging
import re
from typing import Optional
from decimal import Decimal

import asyncpg

logger = logging.getLogger(__name__)


# ── Address Parser ─────────────────────────────────────────────────────────


class AddressParser:
    """Parse and normalize Vancouver addresses."""

    # Vancouver street directions (suffix)
    DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}

    # Street type abbreviations to canonical forms
    ABBREVIATIONS = {
        "ST": "STREET",
        "AVE": "AVENUE",
        "BLVD": "BOULEVARD",
        "DR": "DRIVE",
        "RD": "ROAD",
        "CRES": "CRESCENT",
        "LN": "LANE",
        "PL": "PLACE",
        "PKWY": "PARKWAY",
        "TERR": "TERRACE",
        "WALK": "WALK",
        "CTR": "CENTER",
        "CRT": "COURT",
        "PROM": "PROMENADE",
        "TR": "TRAIL",
        "WY": "WAY",
    }

    @staticmethod
    def parse_vancouver_address(raw: str) -> dict:
        """
        Parse a raw Vancouver address into components.

        Returns:
            dict with keys: street_number, street_name, street_type, direction, raw

        Example:
            "1234 Main Street" -> {
                "street_number": "1234",
                "street_name": "Main",
                "street_type": "Street",
                "direction": None,
                "raw": "1234 Main Street"
            }
        """
        if not raw:
            return {
                "street_number": None,
                "street_name": None,
                "street_type": None,
                "direction": None,
                "raw": raw,
            }

        raw_clean = raw.upper().strip()

        # Remove city/province/postal code suffixes
        raw_clean = re.sub(
            r",?\s*(VANCOUVER|BC|V\d\w\s*\d\w\d|CANADA).*$", "", raw_clean
        )
        raw_clean = raw_clean.strip()

        result = {
            "street_number": None,
            "street_name": None,
            "street_type": None,
            "direction": None,
            "raw": raw,
        }

        # Pattern: <number> <name> <type> [<direction>]
        # Example: "1234 Main Street", "5678 Granville Avenue W"
        pattern = (
            r"^(\d+)\s+"  # street number
            r"([A-Z\s]+?)\s+"  # street name
            r"(STREET|AVENUE|BOULEVARD|DRIVE|ROAD|CRESCENT|LANE|PLACE|PARKWAY|"
            r"TERRACE|WALK|CENTER|COURT|PROMENADE|TRAIL|WAY|"
            r"ST|AVE|BLVD|DR|RD|CRES|LN|PL|PKWY|TERR|TR|WY|CTR|CRT|PROM)"
            r"(?:\s+(N|S|E|W|NE|NW|SE|SW))?$"
        )

        match = re.match(pattern, raw_clean)
        if match:
            result["street_number"] = match.group(1)
            result["street_name"] = match.group(2).strip()
            street_type_raw = match.group(3).strip()
            result["street_type"] = AddressParser.ABBREVIATIONS.get(
                street_type_raw, street_type_raw
            )
            result["direction"] = match.group(4) if match.group(4) else None

        return result

    @staticmethod
    def normalize_address(address: str) -> str:
        """
        Normalize an address by standardizing abbreviations and formatting.

        Example:
            "1234 Main St, Vancouver, BC" -> "1234 Main Street"
        """
        if not address:
            return ""

        # Remove city/province/postal code
        normalized = re.sub(
            r",?\s*(VANCOUVER|BC|V\d\w\s*\d\w\d|CANADA).*$",
            "",
            address.upper(),
        )
        normalized = normalized.strip()

        # Replace abbreviations
        for abbr, full in AddressParser.ABBREVIATIONS.items():
            normalized = re.sub(rf"\b{abbr}\b", full, normalized)

        # Normalize directional prefixes (West Main -> Main West)
        normalized = re.sub(r"\b(WEST|EAST|NORTH|SOUTH)\s+", r"\1 ", normalized)

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    @staticmethod
    def extract_addresses(text: str) -> list[str]:
        """
        Extract Vancouver addresses from free text using regex.

        Returns list of suspected addresses (may include false positives).

        Example:
            "Meeting at 1234 Main Street today" -> ["1234 Main Street"]
        """
        if not text:
            return []

        addresses = []

        # Pattern: number + street name + street type [+ direction]
        pattern = (
            r"\b"
            r"(\d{1,5})\s+"  # street number
            r"([A-Za-z\s]{3,}?)\s+"  # street name
            r"(Street|Avenue|Boulevard|Drive|Road|Crescent|Lane|Place|Parkway|"
            r"Terrace|Walk|Center|Court|Promenade|Trail|Way|"
            r"St|Ave|Blvd|Dr|Rd|Cres|Ln|Pl|Pkwy|Terr|Tr|Wy|Ctr|Crt|Prom)"
            r"(?:\s+(N|S|E|W|NE|NW|SE|SW))?"
            r"(?:\s|,|$)"
        )

        for match in re.finditer(pattern, text, re.IGNORECASE):
            full_match = match.group(0).strip()
            # Remove trailing punctuation but preserve the address
            full_match = re.sub(r",?\s*$", "", full_match)
            if full_match and len(full_match) > 5:
                addresses.append(full_match)

        return addresses


# ── Vancouver Geocoder ─────────────────────────────────────────────────────


class VancouverGeocoder:
    """Geocode Vancouver addresses using parcels table as primary source."""

    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize geocoder with database pool.

        Args:
            db_pool: asyncpg connection pool
        """
        self.pool = db_pool

    async def geocode_address(self, address: str) -> Optional[tuple[float, float]]:
        """
        Geocode a single address to (lng, lat) tuple.

        Attempts in order:
        1. Exact match on parcels.civic_address
        2. Fuzzy match using pg_trgm similarity (threshold 0.6)
        3. Regex-based street number + name extraction

        Args:
            address: Address string to geocode

        Returns:
            (lng, lat) tuple from parcel centroid, or None if not found
        """
        if not address or not address.strip():
            return None

        normalized = AddressParser.normalize_address(address)

        async with self.pool.acquire() as conn:
            # 1. Try exact match
            row = await conn.fetchrow(
                """
                SELECT ST_X(ST_Centroid(geom)) as lng, ST_Y(ST_Centroid(geom)) as lat
                FROM parcels
                WHERE UPPER(COALESCE(civic_address, '')) = UPPER($1)
                LIMIT 1
                """,
                normalized,
            )
            if row:
                return (float(row["lng"]), float(row["lat"]))

            # 2. Try fuzzy match with pg_trgm (similarity > 0.6)
            row = await conn.fetchrow(
                """
                SELECT ST_X(ST_Centroid(geom)) as lng, ST_Y(ST_Centroid(geom)) as lat
                FROM parcels
                WHERE SIMILARITY(UPPER(COALESCE(civic_address, '')), UPPER($1)) > 0.6
                ORDER BY SIMILARITY(UPPER(COALESCE(civic_address, '')), UPPER($1)) DESC
                LIMIT 1
                """,
                normalized,
            )
            if row:
                return (float(row["lng"]), float(row["lat"]))

            # 3. Try regex-based extraction
            parsed = AddressParser.parse_vancouver_address(address)
            if parsed["street_number"] and parsed["street_name"]:
                # Build search pattern: "number street_name"
                search_pattern = f"{parsed['street_number']} {parsed['street_name']}"
                row = await conn.fetchrow(
                    """
                    SELECT ST_X(ST_Centroid(geom)) as lng, ST_Y(ST_Centroid(geom)) as lat
                    FROM parcels
                    WHERE civic_address ILIKE %s
                    LIMIT 1
                    """,
                    f"%{search_pattern}%",
                )
                if row:
                    return (float(row["lng"]), float(row["lat"]))

        return None

    async def geocode_from_neighborhood(
        self, neighborhood: str
    ) -> Optional[tuple[float, float]]:
        """
        Get centroid of a neighborhood polygon.

        Args:
            neighborhood: Vancouver neighborhood name

        Returns:
            (lng, lat) tuple of neighborhood centroid, or None if not found
        """
        if not neighborhood or not neighborhood.strip():
            return None

        async with self.pool.acquire() as conn:
            # Attempt to find neighborhood geometry
            # This depends on a neighborhoods table that should exist
            row = await conn.fetchrow(
                """
                SELECT ST_X(ST_Centroid(geom)) as lng, ST_Y(ST_Centroid(geom)) as lat
                FROM neighborhoods
                WHERE UPPER(name) = UPPER($1)
                LIMIT 1
                """,
                neighborhood,
            )
            if row:
                return (float(row["lng"]), float(row["lat"]))

            # Fallback: try to get centroid from signals in that neighborhood
            row = await conn.fetchrow(
                """
                SELECT ST_X(ST_Centroid(ST_Union(geom))) as lng,
                       ST_Y(ST_Centroid(ST_Union(geom))) as lat
                FROM intelligence_signals
                WHERE UPPER(COALESCE(neighborhood, '')) = UPPER($1)
                  AND geom IS NOT NULL
                GROUP BY neighborhood
                LIMIT 1
                """,
                neighborhood,
            )
            if row:
                return (float(row["lng"]), float(row["lat"]))

        return None

    async def batch_geocode(
        self, addresses: list[str]
    ) -> list[Optional[tuple[float, float]]]:
        """
        Batch geocode multiple addresses.

        Args:
            addresses: List of address strings

        Returns:
            List of (lng, lat) tuples or None, in same order as input
        """
        results = []
        for address in addresses:
            result = await self.geocode_address(address)
            results.append(result)
        return results

    async def geocode_signal(self, signal_id: int) -> bool:
        """
        Geocode a single signal's addresses and update its geom field.

        Attempts to geocode the first address in signal.addresses array.
        Falls back to neighborhood centroid if no address can be geocoded.

        Args:
            signal_id: ID of intelligence signal to geocode

        Returns:
            True if geom was updated, False if no match found
        """
        async with self.pool.acquire() as conn:
            # Fetch signal addresses and neighborhood
            signal = await conn.fetchrow(
                """
                SELECT addresses, neighborhood FROM intelligence_signals
                WHERE id = $1
                """,
                signal_id,
            )

            if not signal:
                logger.warning(f"Signal {signal_id} not found")
                return False

            addresses = signal["addresses"] or []
            neighborhood = signal["neighborhood"]

            geom_result = None

            # Try to geocode first address
            if addresses:
                for address in addresses:
                    geom_result = await self.geocode_address(address)
                    if geom_result:
                        break

            # Fallback to neighborhood
            if not geom_result and neighborhood:
                geom_result = await self.geocode_from_neighborhood(neighborhood)

            # Update signal if we found a location
            if geom_result:
                lng, lat = geom_result
                await conn.execute(
                    """
                    UPDATE intelligence_signals
                    SET geom = ST_GeomFromText($1, 4326)
                    WHERE id = $2
                    """,
                    f"POINT({lng} {lat})",
                    signal_id,
                )
                logger.info(f"Geocoded signal {signal_id} to ({lng}, {lat})")
                return True

            logger.debug(f"Could not geocode signal {signal_id}")
            return False

    async def backfill_missing_geocodes(self, limit: int = 100) -> dict:
        """
        Find signals with addresses but no geom and attempt to geocode them.

        Args:
            limit: Maximum number of signals to process

        Returns:
            dict with keys: attempted, succeeded, failed
        """
        stats = {"attempted": 0, "succeeded": 0, "failed": 0}

        async with self.pool.acquire() as conn:
            # Find signals with addresses but no geom
            signals = await conn.fetch(
                """
                SELECT id, addresses, neighborhood
                FROM intelligence_signals
                WHERE (addresses IS NOT NULL AND array_length(addresses, 1) > 0)
                  AND geom IS NULL
                LIMIT $1
                """,
                limit,
            )

            stats["attempted"] = len(signals)

            for signal in signals:
                try:
                    success = await self.geocode_signal(signal["id"])
                    if success:
                        stats["succeeded"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Error geocoding signal {signal['id']}: {e}")
                    stats["failed"] += 1

        return stats
