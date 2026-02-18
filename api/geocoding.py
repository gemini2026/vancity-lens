from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from functools import lru_cache
from urllib.parse import quote
import logging
import time
import os

router = APIRouter(prefix="/api/v1", tags=["geocoding"])

logger = logging.getLogger(__name__)


def _get_mapbox_token() -> str:
    """Resolve Mapbox token from env.

    We support both:
    - MAPBOX_TOKEN (preferred for backend)
    - NEXT_PUBLIC_MAPBOX_TOKEN (legacy/dev convenience)
    """
    return os.getenv("MAPBOX_TOKEN") or os.getenv("NEXT_PUBLIC_MAPBOX_TOKEN") or ""


VANCOUVER_BOUNDS = {
    "min_lat": 49.0,
    "max_lat": 49.4,
    "min_lng": -123.3,
    "max_lng": -122.9,
}


class GeocodingResult(BaseModel):
    address: str
    lat: float
    lng: float
    neighborhood: Optional[str] = None
    postal_code: Optional[str] = None
    confidence: float


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 1):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        if identifier not in self.requests:
            self.requests[identifier] = []

        cutoff = now - self.window_seconds
        self.requests[identifier] = [t for t in self.requests[identifier] if t > cutoff]

        if len(self.requests[identifier]) >= self.max_requests:
            return False

        self.requests[identifier].append(now)
        return True


rate_limiter = RateLimiter(max_requests=10, window_seconds=1)


@lru_cache(maxsize=256)
def cached_mapbox_geocode(query: str, token: str) -> Optional[dict]:
    if not token:
        return None

    try:
        import requests

        encoded_query = quote(query.strip(), safe="")
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded_query}.json"
        response = requests.get(
            url,
            params={
                "access_token": token,
                "proximity": "-123.1148,49.2632",
                "bbox": "-123.3,49.0,-122.9,49.4",
            },
            timeout=5,
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.warning(f"Mapbox error: {e}")

    return None


def validate_bounds(lat: float, lng: float) -> bool:
    return (
        VANCOUVER_BOUNDS["min_lat"] <= lat <= VANCOUVER_BOUNDS["max_lat"]
        and VANCOUVER_BOUNDS["min_lng"] <= lng <= VANCOUVER_BOUNDS["max_lng"]
    )


@router.get("/geocode", response_model=List[GeocodingResult])
async def geocode(q: str = Query(..., min_length=2), user_id: Optional[str] = None):
    identifier = user_id or "anonymous"
    if not rate_limiter.is_allowed(identifier):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        # Prefer local authoritative parcel matches when available
        try:
            from .db import db

            if db.pool is not None:
                from .parcel_search import ParcelSearchService

                service = ParcelSearchService(db.pool)
                parcel_results = await service.search_by_address(q, limit=5)
                results = []
                for r in parcel_results:
                    if not validate_bounds(r.lat, r.lng):
                        continue
                    results.append(
                        GeocodingResult(
                            address=r.civic_address,
                            lat=r.lat,
                            lng=r.lng,
                            neighborhood=r.neighborhood or None,
                            postal_code=None,
                            confidence=0.95,
                        )
                    )
                if results:
                    return results
        except Exception as e:
            logger.info(f"Parcel geocode fallback skipped/failed: {e}")

        token = _get_mapbox_token()
        data = cached_mapbox_geocode(q, token)
        if not data or "features" not in data:
            return []

        results = []
        for feature in data.get("features", [])[:5]:
            coords = feature.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue

            lng, lat = coords[0], coords[1]
            if not validate_bounds(lat, lng):
                continue

            place_name = feature.get("place_name", "")
            context = feature.get("context", [])

            neighborhood = None
            postal_code = None
            for ctx in context:
                if ctx.get("id", "").startswith("place."):
                    neighborhood = ctx.get("text")
                if ctx.get("id", "").startswith("postcode."):
                    postal_code = ctx.get("text")

            results.append(
                GeocodingResult(
                    address=place_name,
                    lat=lat,
                    lng=lng,
                    neighborhood=neighborhood,
                    postal_code=postal_code,
                    confidence=0.95,
                )
            )

        return results
    except Exception as e:
        logger.exception(f"Geocode error: {e}")
        raise HTTPException(status_code=500, detail="Geocoding failed")


@router.get("/reverse-geocode", response_model=GeocodingResult)
async def reverse_geocode(
    lat: float = Query(...), lng: float = Query(...), user_id: Optional[str] = None
):
    identifier = user_id or "anonymous"
    if not rate_limiter.is_allowed(identifier):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not validate_bounds(lat, lng):
        raise HTTPException(status_code=400, detail="Coordinates outside Vancouver")

    try:
        token = _get_mapbox_token()
        if not token:
            return GeocodingResult(
                address=f"{lat:.4f}, {lng:.4f}",
                lat=lat,
                lng=lng,
                confidence=0.5,
            )

        import requests

        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lng},{lat}.json"
        response = requests.get(url, params={"access_token": token}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            feature = data.get("features", [{}])[0]
            place_name = feature.get("place_name", f"{lat:.4f}, {lng:.4f}")
            context = feature.get("context", [])

            neighborhood = None
            postal_code = None
            for ctx in context:
                if ctx.get("id", "").startswith("place."):
                    neighborhood = ctx.get("text")
                if ctx.get("id", "").startswith("postcode."):
                    postal_code = ctx.get("text")

            return GeocodingResult(
                address=place_name,
                lat=lat,
                lng=lng,
                neighborhood=neighborhood,
                postal_code=postal_code,
                confidence=0.9,
            )

        return GeocodingResult(
            address=f"{lat:.4f}, {lng:.4f}",
            lat=lat,
            lng=lng,
            confidence=0.5,
        )
    except Exception as e:
        logger.exception(f"Reverse geocode error: {e}")
        raise HTTPException(status_code=500, detail="Reverse geocoding failed")
