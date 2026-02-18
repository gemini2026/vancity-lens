"""
VanCity Lens — Address-based parcel search service.

Provides comprehensive parcel search capabilities for VanCity Lens via multiple
search methods: full-text address search, PID lookup, spatial coordinates search,
and fuzzy address matching with PostgreSQL full-text search (ts_vector) and
trigram similarity (pg_trgm).

Key features:
- Address normalization (unit number stripping, street suffix standardization)
- PostgreSQL ts_vector for indexed full-text search
- Trigram similarity for fuzzy matching
- Spatial search via coordinates and radius
- Match score ranking for result prioritization
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/parcels", tags=["parcel-search"])

# Pattern to detect PID format: NNN-NNN-NNN (3 groups of 3 digits separated by hyphens)
PID_PATTERN = re.compile(r"^\d{3}-\d{3}-\d{3}$")


@dataclass
class ParcelSearchResult:
    """Represents a single parcel search result with location and zoning info."""

    parcel_id: str
    pid: str
    civic_address: str
    lat: float
    lng: float
    lot_area_sqm: float
    zoning: str
    neighborhood: str
    match_score: float


class AddressNormalizer:
    """Normalizes addresses for consistent searching and matching."""

    STREET_SUFFIXES = {
        "st": "street",
        "str": "street",
        "ave": "avenue",
        "av": "avenue",
        "blvd": "boulevard",
        "bd": "boulevard",
        "rd": "road",
        "lane": "lane",
        "ln": "lane",
        "drive": "drive",
        "dr": "drive",
        "court": "court",
        "ct": "court",
        "cres": "crescent",
        "crt": "crescent",
        "pl": "place",
        "terr": "terrace",
        "ter": "terrace",
        "way": "way",
    }

    @staticmethod
    def normalize(query: str) -> str:
        """
        Normalize an address query for searching.

        Applies Vancouver-specific normalization rules:
        - Removes unit numbers (e.g., "#202", "Suite 100")
        - Standardizes street suffixes (St -> Street, Ave -> Avenue)
        - Converts to lowercase
        - Removes extra whitespace
        """
        # Remove unit/suite numbers at start of address
        normalized = re.sub(r"^[#]?\d+[a-z]?\s*", "", query, flags=re.IGNORECASE)
        normalized = re.sub(r"^suite\s+\d+\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(
            r"^unit\s+\d+[a-z]?\s*", "", normalized, flags=re.IGNORECASE
        )

        # Normalize street suffixes
        words = normalized.split()
        for i, word in enumerate(words):
            clean_word = word.rstrip(".,")
            if clean_word.lower() in AddressNormalizer.STREET_SUFFIXES:
                words[i] = AddressNormalizer.STREET_SUFFIXES[clean_word.lower()]

        normalized = " ".join(words)
        normalized = normalized.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized


class ParcelSearchService:
    """Service for searching and filtering parcel data in PostgreSQL."""

    def __init__(self, db_pool: asyncpg.Pool):
        """Initialize the service with a database connection pool."""
        self.pool = db_pool

    async def search_by_address(
        self, query: str, limit: int = 10
    ) -> list[ParcelSearchResult]:
        """
        Search parcels by address using full-text search.

        Uses PostgreSQL ts_vector for indexed full-text search on civic_address.
        Returns results ranked by relevance score.

        Args:
            query: Address search query (can be partial)
            limit: Maximum number of results (default 10, max 100)

        Returns:
            List of ParcelSearchResult objects ranked by match_score descending
        """
        if not query or not query.strip():
            return []

        limit = min(max(1, limit), 100)
        normalized = AddressNormalizer.normalize(query)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        pid,
                        civic_address,
                        ST_Y(ST_Centroid(geom)) as lat,
                        ST_X(ST_Centroid(geom)) as lng,
                        COALESCE(lot_area_sqm, 0) as lot_area_sqm,
                        COALESCE(current_zoning, '') as zoning,
                        COALESCE(geo_local_area, '') as neighborhood,
                        ts_rank(
                            to_tsvector('english', COALESCE(civic_address, '')),
                            plainto_tsquery('english', $1)
                        ) as match_score
                    FROM parcels
                    WHERE to_tsvector('english', COALESCE(civic_address, '')) @@
                          plainto_tsquery('english', $1)
                    ORDER BY match_score DESC
                    LIMIT $2
                    """,
                    normalized,
                    limit,
                )

                return [
                    ParcelSearchResult(
                        parcel_id=str(row["id"]),
                        pid=row["pid"],
                        civic_address=row["civic_address"] or "",
                        lat=float(row["lat"]),
                        lng=float(row["lng"]),
                        lot_area_sqm=float(row["lot_area_sqm"]),
                        zoning=row["zoning"],
                        neighborhood=row["neighborhood"],
                        match_score=float(row["match_score"]),
                    )
                    for row in rows
                ]
        except asyncpg.PostgresError as e:
            logger.error(f"Database error in search_by_address: {e}")
            raise

    async def search_by_pid(self, pid: str) -> Optional[ParcelSearchResult]:
        """
        Look up a single parcel by its Property ID (PID).

        Args:
            pid: Property ID string (format: "XXXX-XXX-XXX")

        Returns:
            ParcelSearchResult if found, None otherwise
        """
        if not pid or not pid.strip():
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        pid,
                        civic_address,
                        ST_Y(ST_Centroid(geom)) as lat,
                        ST_X(ST_Centroid(geom)) as lng,
                        COALESCE(lot_area_sqm, 0) as lot_area_sqm,
                        COALESCE(current_zoning, '') as zoning,
                        COALESCE(geo_local_area, '') as neighborhood
                    FROM parcels
                    WHERE pid = $1
                    """,
                    pid.strip(),
                )

                if not row:
                    return None

                return ParcelSearchResult(
                    parcel_id=str(row["id"]),
                    pid=row["pid"],
                    civic_address=row["civic_address"] or "",
                    lat=float(row["lat"]),
                    lng=float(row["lng"]),
                    lot_area_sqm=float(row["lot_area_sqm"]),
                    zoning=row["zoning"],
                    neighborhood=row["neighborhood"],
                    match_score=1.0,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Database error in search_by_pid: {e}")
            raise

    async def search_by_coordinates(
        self, lat: float, lng: float, radius_m: float = 500.0
    ) -> list[ParcelSearchResult]:
        """
        Search parcels within a radius of given coordinates.

        Uses PostGIS ST_DWithin for efficient spatial search.

        Args:
            lat: Latitude (WGS84)
            lng: Longitude (WGS84)
            radius_m: Search radius in meters (default 500)

        Returns:
            List of ParcelSearchResult objects ordered by distance
        """
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return []

        radius_m = max(1, min(radius_m, 10000))

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        pid,
                        civic_address,
                        ST_Y(ST_Centroid(geom)) as lat,
                        ST_X(ST_Centroid(geom)) as lng,
                        COALESCE(lot_area_sqm, 0) as lot_area_sqm,
                        COALESCE(current_zoning, '') as zoning,
                        COALESCE(geo_local_area, '') as neighborhood,
                        ST_Distance(
                            ST_SetSRID(ST_Point($2, $1), 4326)::geography,
                            ST_Centroid(geom)::geography
                        ) as distance_m
                    FROM parcels
                    WHERE ST_DWithin(
                        ST_SetSRID(ST_Point($2, $1), 4326)::geography,
                        geom::geography,
                        $3
                    )
                    ORDER BY distance_m ASC
                    LIMIT 50
                    """,
                    lat,
                    lng,
                    float(radius_m),
                )

                return [
                    ParcelSearchResult(
                        parcel_id=str(row["id"]),
                        pid=row["pid"],
                        civic_address=row["civic_address"] or "",
                        lat=float(row["lat"]),
                        lng=float(row["lng"]),
                        lot_area_sqm=float(row["lot_area_sqm"]),
                        zoning=row["zoning"],
                        neighborhood=row["neighborhood"],
                        match_score=max(
                            0.0, 1.0 - (float(row["distance_m"]) / radius_m)
                        ),
                    )
                    for row in rows
                ]
        except asyncpg.PostgresError as e:
            logger.error(f"Database error in search_by_coordinates: {e}")
            raise

    async def fuzzy_address_match(
        self, query: str, limit: int = 10
    ) -> list[ParcelSearchResult]:
        """
        Search parcels using trigram similarity for fuzzy matching.

        Uses PostgreSQL pg_trgm extension (similarity function) to find
        addresses similar to the query even with typos or partial matches.

        Args:
            query: Address search query (can be partial or have typos)
            limit: Maximum number of results

        Returns:
            List of ParcelSearchResult objects ranked by similarity score
        """
        if not query or not query.strip():
            return []

        limit = min(max(1, limit), 100)
        normalized = AddressNormalizer.normalize(query)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        pid,
                        civic_address,
                        ST_Y(ST_Centroid(geom)) as lat,
                        ST_X(ST_Centroid(geom)) as lng,
                        COALESCE(lot_area_sqm, 0) as lot_area_sqm,
                        COALESCE(current_zoning, '') as zoning,
                        COALESCE(geo_local_area, '') as neighborhood,
                        similarity(COALESCE(civic_address, ''), $1) as match_score
                    FROM parcels
                    WHERE COALESCE(civic_address, '') % $1
                    ORDER BY match_score DESC
                    LIMIT $2
                    """,
                    normalized,
                    limit,
                )

                return [
                    ParcelSearchResult(
                        parcel_id=str(row["id"]),
                        pid=row["pid"],
                        civic_address=row["civic_address"] or "",
                        lat=float(row["lat"]),
                        lng=float(row["lng"]),
                        lot_area_sqm=float(row["lot_area_sqm"]),
                        zoning=row["zoning"],
                        neighborhood=row["neighborhood"],
                        match_score=float(row["match_score"]),
                    )
                    for row in rows
                ]
        except asyncpg.PostgresError as e:
            logger.error(f"Database error in fuzzy_address_match: {e}")
            raise


async def get_search_service() -> ParcelSearchService:
    """Dependency to provide ParcelSearchService from the global db pool."""
    from .db import db

    if db.pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return ParcelSearchService(db.pool)


@router.get("/search")
async def search_parcels(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=100),
    service: ParcelSearchService = Depends(get_search_service),
) -> dict:
    """
    Full-text search for parcels by address or PID.

    If the query matches PID format (NNN-NNN-NNN), a direct PID lookup is
    attempted first. Otherwise, full-text address search is performed.

    Returns a structured disambiguation response:
    - ``disambiguation: true`` when multiple matches are found
    - ``disambiguation: false`` when exactly one match is found
    - 404 with PRD-compliant error message when no matches are found

    Query parameters:
        q: Address or PID search query (required, 1-200 chars)
        limit: Max results (1-100, default 10)

    Returns:
        JSON object with results array, count, and disambiguation flag
    """
    results: list[ParcelSearchResult] = []

    # PID format detection: if input matches NNN-NNN-NNN, try direct PID lookup first
    if PID_PATTERN.match(q.strip()):
        pid_result = await service.search_by_pid(q.strip())
        if pid_result:
            results = [pid_result]

    # If no PID match (or not a PID query), fall back to address search
    if not results:
        results = await service.search_by_address(q, limit)

    # Zero results: return 404 with PRD-compliant error message
    if not results:
        raise HTTPException(
            status_code=404,
            detail=(
                "Address could not be resolved to a valid Vancouver parcel. "
                "Please verify the address and try again."
            ),
        )

    return {
        "query": q,
        "limit": limit,
        "count": len(results),
        "disambiguation": len(results) > 1,
        "results": [
            {
                "parcel_id": r.parcel_id,
                "pid": r.pid,
                "civic_address": r.civic_address,
                "lat": r.lat,
                "lng": r.lng,
                "lot_area_sqm": r.lot_area_sqm,
                "zoning": r.zoning,
                "neighborhood": r.neighborhood,
                "match_score": r.match_score,
            }
            for r in results
        ],
    }


@router.get("/by-pid/{pid}")
async def get_parcel_by_pid(
    pid: str, service: ParcelSearchService = Depends(get_search_service)
) -> dict:
    """
    Look up a parcel by Property ID (PID).

    Path parameters:
        pid: Property ID string (format: "XXXX-XXX-XXX")

    Returns:
        JSON object with parcel data or 404 if not found
    """
    result = await service.search_by_pid(pid)

    if not result:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {pid}")

    return {
        "parcel_id": result.parcel_id,
        "pid": result.pid,
        "civic_address": result.civic_address,
        "lat": result.lat,
        "lng": result.lng,
        "lot_area_sqm": result.lot_area_sqm,
        "zoning": result.zoning,
        "neighborhood": result.neighborhood,
        "match_score": result.match_score,
    }


@router.get("/nearby")
async def search_nearby_parcels(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: float = Query(500, ge=1, le=10000),
    service: ParcelSearchService = Depends(get_search_service),
) -> dict:
    """
    Search for parcels near given coordinates.

    Query parameters:
        lat: Latitude (WGS84, -90 to 90, required)
        lng: Longitude (WGS84, -180 to 180, required)
        radius: Search radius in meters (1-10000, default 500)

    Returns:
        JSON object with nearby parcel results
    """
    results = await service.search_by_coordinates(lat, lng, radius)

    return {
        "center": {"lat": lat, "lng": lng},
        "radius_m": radius,
        "count": len(results),
        "results": [
            {
                "parcel_id": r.parcel_id,
                "pid": r.pid,
                "civic_address": r.civic_address,
                "lat": r.lat,
                "lng": r.lng,
                "lot_area_sqm": r.lot_area_sqm,
                "zoning": r.zoning,
                "neighborhood": r.neighborhood,
                "match_score": r.match_score,
            }
            for r in results
        ],
    }
