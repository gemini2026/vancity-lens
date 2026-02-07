"""
VanCity Lens — Broadway Plan Pipeline Domain Models

The Broadway Plan is a specific upzoning plan for the Broadway Corridor
(roughly Vine St to Clark Dr, 1st Ave to 16th Ave). It defines sub-areas
with unique height/FSR/use rules that OVERLAY on top of Bill 47.

The pipeline:
1. Vision AI (Gemini) parses the Broadway Plan PDF map images
2. GPT-4o extracts structured bylaw rules from text sections
3. Geospatial Anchoring snaps fuzzy AI boundaries to real parcel fabric
"""

from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class BroadwaySubArea(str, Enum):
    """Broadway Plan sub-areas with distinct zoning rules."""
    C1 = "C1"   # Broadway Station Precinct
    C2 = "C2"   # City Hall Station Precinct
    C3 = "C3"   # South Granville
    C4 = "C4"   # Arbutus Station Precinct
    SHOULDER_N = "Shoulder_North"
    SHOULDER_S = "Shoulder_South"
    INDUSTRIAL = "Industrial"
    RESIDENTIAL_TRANSITION = "Residential_Transition"


class LandUse(str, Enum):
    MIXED_USE = "mixed_use"
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    INSTITUTIONAL = "institutional"


class ExtractedZoneRule(BaseModel):
    """A single zoning rule extracted by GPT-4o from bylaw text."""
    sub_area: BroadwaySubArea
    land_use: LandUse
    max_height_m: Optional[float] = None
    max_storeys: Optional[int] = None
    max_fsr: Optional[Decimal] = None
    min_social_housing_pct: Optional[float] = Field(
        None, description="Minimum % of units as social/below-market"
    )
    requires_community_amenity: bool = False
    source_page: Optional[int] = None
    source_text: Optional[str] = Field(
        None, description="Verbatim excerpt from bylaw for audit trail"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Model confidence in this extraction"
    )


class ExtractedBoundary(BaseModel):
    """A geographic boundary extracted by Gemini Vision from a map image."""
    sub_area: BroadwaySubArea
    raw_polygon_coords: list[list[float]] = Field(
        ..., description="[[lng, lat], ...] from Vision AI (before anchoring)"
    )
    anchored_polygon_wkt: Optional[str] = Field(
        None, description="WKT after snapping to parcel fabric"
    )
    source_page: int
    confidence: float = Field(..., ge=0.0, le=1.0)


class AnchoredZone(BaseModel):
    """A fully processed Broadway Plan zone ready for DB insertion."""
    sub_area: BroadwaySubArea
    polygon_wkt: str
    rules: list[ExtractedZoneRule]
    parcel_count: int = Field(
        ..., description="Number of parcels this zone overlaps"
    )
    total_lot_area_sqm: Decimal
