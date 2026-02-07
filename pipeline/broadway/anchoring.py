"""
VanCity Lens — Geospatial Anchoring Engine

The critical step between "AI guess" and "investment-grade data":
Takes fuzzy polygon boundaries from Vision AI and snaps them to
real cadastral (parcel fabric) boundaries in PostGIS.

Why this matters:
- Gemini Vision might say a boundary runs "along 8th Avenue"
- But the actual legal boundary follows parcel lot lines
- We snap the fuzzy polygon to the nearest parcel edges
- Result: every parcel is definitively IN or OUT of the zone

Algorithm:
1. Take raw polygon from Vision AI
2. Buffer it slightly (10m) to catch edge parcels
3. Find all parcels whose centroids fall within the polygon
4. Build a "dissolved" boundary from the union of matched parcels
5. This gives us a legally precise zone boundary
"""

from decimal import Decimal
from typing import Optional

import asyncpg
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import unary_union
from pyproj import Transformer

from .models import (
    AnchoredZone,
    BroadwaySubArea,
    ExtractedBoundary,
    ExtractedZoneRule,
)

# WGS84 <-> BC Albers projection (same as our PostGIS setup)
WGS84_TO_BCALBERS = Transformer.from_crs("EPSG:4326", "EPSG:3005", always_xy=True)
BCALBERS_TO_WGS84 = Transformer.from_crs("EPSG:3005", "EPSG:4326", always_xy=True)


# SQL: Find parcels whose centroids fall within a given polygon
SQL_PARCELS_IN_POLYGON = """
    WITH zone AS (
        SELECT ST_SetSRID(ST_GeomFromText($1), 4326) AS geom
    ),
    buffered AS (
        -- Buffer by 10m in projected CRS to catch edge parcels
        SELECT ST_Transform(
            ST_Buffer(ST_Transform(z.geom, 3005), $2),
            4326
        ) AS geom
        FROM zone z
    )
    SELECT
        p.pid,
        p.civic_address,
        p.lot_area_sqm,
        p.current_zoning,
        ST_AsText(p.geom) AS parcel_wkt,
        ST_Distance(
            ST_Transform(ST_Centroid(p.geom), 3005),
            ST_Transform((SELECT geom FROM zone), 3005)
        ) AS dist_to_center_m
    FROM parcels p, buffered b
    WHERE ST_Within(ST_Centroid(p.geom), b.geom)
    ORDER BY dist_to_center_m
"""

# SQL: Build dissolved boundary from selected parcels
SQL_DISSOLVE_PARCELS = """
    SELECT ST_AsText(
        ST_Union(p.geom)
    ) AS dissolved_wkt,
    COUNT(*) AS parcel_count,
    SUM(p.lot_area_sqm) AS total_area
    FROM parcels p
    WHERE p.pid = ANY($1::text[])
"""


class GeoAnchor:
    """
    Snaps fuzzy AI-extracted boundaries to the real parcel fabric.

    This is the "trust layer" — Colin can't invest $5M based on
    a polygon Gemini guessed from a PDF. He needs parcel-level precision.
    """

    def __init__(self, conn: asyncpg.Connection, buffer_m: float = 10.0):
        self.conn = conn
        self.buffer_m = buffer_m

    def _coords_to_wkt(self, coords: list[list[float]]) -> str:
        """Convert [[lng, lat], ...] to WKT POLYGON string."""
        # Ensure polygon is closed
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        coord_str = ", ".join(f"{c[0]} {c[1]}" for c in coords)
        return f"POLYGON(({coord_str}))"

    async def anchor_boundary(
        self,
        boundary: ExtractedBoundary,
        rules: list[ExtractedZoneRule],
    ) -> Optional[AnchoredZone]:
        """
        Take a single Vision AI boundary and anchor it to parcels.

        Steps:
        1. Convert raw coords to WKT polygon
        2. Query PostGIS for all parcels within (with buffer)
        3. Dissolve matched parcels into a clean boundary
        4. Return AnchoredZone with parcel-snapped geometry
        """
        raw_wkt = self._coords_to_wkt(boundary.raw_polygon_coords)

        # Step 1: Find all parcels within the fuzzy boundary
        rows = await self.conn.fetch(
            SQL_PARCELS_IN_POLYGON,
            raw_wkt,
            self.buffer_m,
        )

        if not rows:
            print(f"  WARNING: No parcels found in {boundary.sub_area} zone")
            return None

        pids = [r["pid"] for r in rows]
        print(f"  Anchoring {boundary.sub_area}: {len(pids)} parcels matched")

        # Step 2: Dissolve matched parcels into a single boundary
        dissolved = await self.conn.fetchrow(SQL_DISSOLVE_PARCELS, pids)

        if not dissolved or not dissolved["dissolved_wkt"]:
            return None

        # Store the anchored WKT back on the boundary
        boundary.anchored_polygon_wkt = dissolved["dissolved_wkt"]

        return AnchoredZone(
            sub_area=boundary.sub_area,
            polygon_wkt=dissolved["dissolved_wkt"],
            rules=[r for r in rules if r.sub_area == boundary.sub_area],
            parcel_count=dissolved["parcel_count"],
            total_lot_area_sqm=Decimal(str(dissolved["total_area"] or 0)),
        )
