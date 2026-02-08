from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from functools import lru_cache
import time
import os

router = APIRouter(prefix="/api/v1", tags=["geocoding"])

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "")
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
        self.requests[identifier] = [
            t for t in self.requests[identifier] if t > cutoff
        ]

        if len(self.requests[identifier]) >= self.max_requests:
            return False

        self.requests[identifier].append(now)
        return True


rate_limiter = RateLimiter(max_requests=10, window_seconds=1)


@lru_cache(maxsize=256)
def cached_mapbox_geocode(query: str) -> Optional[dict]:
    if not MAPBOX_TOKEN:
        return None

    try:
        import requests

        url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
            f"{query}.json?access_token={MAPBOX_TOKEN}&proximity="
            f"-123.1148,49.2632&bbox=-123.3,49.0,-122.9,49.4"
        )
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Mapbox error: {e}")

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
        data = cached_mapbox_geocode(q)
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
        print(f"Geocode error: {e}")
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
        if not MAPBOX_TOKEN:
            return GeocodingResult(
                address=f"{lat:.4f}, {lng:.4f}",
                lat=lat,
                lng=lng,
                confidence=0.5,
            )

        import requests

        url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
            f"{lng},{lat}.json?access_token={MAPBOX_TOKEN}"
        )
        response = requests.get(url, timeout=5)
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
        print(f"Reverse geocode error: {e}")
        raise HTTPException(status_code=500, detail="Reverse geocoding failed")
