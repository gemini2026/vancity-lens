"""
VanCity Lens — Building Permit Activity & Competing Supply Analysis
Core business logic for analyzing permit pipeline and supply pressure.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

import asyncpg
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────

class PermitType(str, Enum):
    NEW_BUILDING = "new_build"
    RENOVATION = "renovation"
    DEMOLITION = "demolition"


class PermitStatus(str, Enum):
    APPLIED = "applied"
    APPROVED = "approved"
    ISSUED = "issued"
    COMPLETED = "completed"


# ── Models ───────────────────────────────────────────────────

class BuildingPermit(BaseModel):
    """Represents a single building permit record."""
    permit_number: str
    address: str
    permit_type: PermitType
    status: PermitStatus
    project_value: Decimal = Field(default=Decimal("0"), ge=0)
    units_proposed: Optional[int] = Field(default=None, ge=0)
    storeys: Optional[int] = Field(default=None, ge=1)
    sqft: Optional[int] = Field(default=None, ge=0)
    issued_date: Optional[datetime] = None
    applicant: Optional[str] = None


class CompetingSupplyResult(BaseModel):
    """Analysis of competing supply in an area."""
    total_permits: int = Field(ge=0)
    new_build_permits: int = Field(ge=0)
    pipeline_units: int = Field(ge=0)
    total_value: Decimal = Field(default=Decimal("0"), ge=0)
    supply_pressure_score: float = Field(ge=0, le=100)
    avg_units_per_project: float = Field(default=0.0, ge=0)


# ── SQL Queries ──────────────────────────────────────────────

SQL_PERMITS_NEAR_PARCEL = """
    SELECT
        permit_number,
        address,
        type,
        status,
        project_value,
        units,
        storeys,
        sqft,
        issued_date,
        applicant
    FROM building_permits
    WHERE ST_DWithin(
        geom,
        (SELECT geom FROM parcels WHERE pid = $1),
        $2
    )
    AND issued_date >= NOW() - INTERVAL '1 month' * $3
    ORDER BY issued_date DESC
"""

SQL_PERMITS_BY_RADIUS = """
    SELECT
        permit_number,
        address,
        type,
        status,
        project_value,
        units,
        storeys,
        sqft,
        issued_date,
        applicant
    FROM building_permits
    WHERE ST_DWithin(
        geom,
        ST_MakePoint($1, $2),
        $3
    )
    AND issued_date >= NOW() - INTERVAL '1 month' * $4
    ORDER BY issued_date DESC
"""


# ── BuildingPermitAnalyzer ────────────────────────────────────

class BuildingPermitAnalyzer:
    """Analyzes building permits and competing supply dynamics."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def get_permits_near_parcel(
        self,
        parcel_id: str,
        radius_m: int = 500,
        months_back: int = 12,
    ) -> list[BuildingPermit]:
        """
        Fetch permits within radius of a parcel.

        Args:
            parcel_id: The parcel PID
            radius_m: Search radius in meters (default 500)
            months_back: How many months back to search (default 12)

        Returns:
            List of BuildingPermit objects, most recent first
        """
        rows = await self.conn.fetch(
            SQL_PERMITS_NEAR_PARCEL,
            parcel_id,
            radius_m,
            months_back,
        )
        return [self._row_to_permit(row) for row in rows]

    async def get_permits_by_radius(
        self,
        lat: float,
        lng: float,
        radius_m: int = 500,
        months_back: int = 12,
    ) -> list[BuildingPermit]:
        """
        Fetch permits within radius of coordinates.

        Args:
            lat: Latitude
            lng: Longitude
            radius_m: Search radius in meters (default 500)
            months_back: How many months back to search (default 12)

        Returns:
            List of BuildingPermit objects, most recent first
        """
        rows = await self.conn.fetch(
            SQL_PERMITS_BY_RADIUS,
            lng,
            lat,
            radius_m,
            months_back,
        )
        return [self._row_to_permit(row) for row in rows]

    async def compute_competing_supply(
        self,
        lat: float,
        lng: float,
        radius_m: int = 500,
        existing_units: int = 0,
    ) -> CompetingSupplyResult:
        """
        Analyze competing supply in the area.

        Args:
            lat: Latitude
            lng: Longitude
            radius_m: Search radius in meters
            existing_units: Current units on site (for pressure calc)

        Returns:
            CompetingSupplyResult with metrics
        """
        permits = await self.get_permits_by_radius(lat, lng, radius_m)

        total_permits = len(permits)
        new_build_permits = sum(
            1 for p in permits if p.permit_type == PermitType.NEW_BUILDING
        )
        pipeline_units = self.estimate_pipeline_units(permits)
        total_value = sum(p.project_value for p in permits)
        supply_pressure_score = self.compute_supply_pressure_score(
            pipeline_units,
            existing_units,
        )
        avg_units = (
            pipeline_units / total_permits if total_permits > 0 else 0.0
        )

        return CompetingSupplyResult(
            total_permits=total_permits,
            new_build_permits=new_build_permits,
            pipeline_units=pipeline_units,
            total_value=total_value,
            supply_pressure_score=supply_pressure_score,
            avg_units_per_project=avg_units,
        )

    @staticmethod
    def estimate_pipeline_units(permits: list[BuildingPermit]) -> int:
        """
        Estimate total pipeline units from permits.

        Sums units_proposed from permits in pipeline (not completed).

        Args:
            permits: List of permits

        Returns:
            Total estimated units in pipeline
        """
        pipeline = [
            p for p in permits
            if p.status in (PermitStatus.APPLIED, PermitStatus.APPROVED, PermitStatus.ISSUED)
        ]
        total = sum(p.units_proposed or 0 for p in pipeline)
        return int(total)

    @staticmethod
    def compute_supply_pressure_score(
        pipeline_units: int,
        existing_units: int = 0,
    ) -> float:
        """
        Compute supply pressure score (0-100).

        Higher score = more competing supply pressure.
        Ratio-based: pipeline_units / (existing_units + 1) normalized to 0-100.

        Args:
            pipeline_units: Units in pipeline
            existing_units: Current units (default 0)

        Returns:
            Score between 0 and 100
        """
        if existing_units <= 0:
            existing_units = 1

        ratio = pipeline_units / existing_units
        # Map ratio to 0-100 scale: ratio of 1.0 = 50, ratio of 2.0 = 75, etc.
        score = min(100.0, (ratio / (ratio + 1.0)) * 100.0)
        return max(0.0, float(score))

    @staticmethod
    def _row_to_permit(row) -> BuildingPermit:
        """Convert database row to BuildingPermit."""
        return BuildingPermit(
            permit_number=row["permit_number"],
            address=row["address"],
            permit_type=PermitType(row["type"]),
            status=PermitStatus(row["status"]),
            project_value=Decimal(str(row["project_value"] or 0)),
            units_proposed=row["units"],
            storeys=row["storeys"],
            sqft=row["sqft"],
            issued_date=row["issued_date"],
            applicant=row["applicant"],
        )
