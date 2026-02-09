"""
VanCity Lens — Protected Tree Analysis Engine (VCL-111: VAL-004)
Analyzes protected and heritage trees on parcels per Vancouver bylaw.

Vancouver Tree Bylaw Rules:
- Trees >= 20cm DBH on private property require removal permit
- Heritage trees: extra protection tier, higher replacement costs ($1K-$15K)
- Significant trees: 10-20cm DBH ($500-$2K removal/replacement)
- Cost estimates: $500-$5K per standard tree, $1K-$15K for heritage replacement

This module provides tree counting, cost estimation, and impact scoring
for Bill 47 (TOA) development scenarios.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProtectionStatus(str, Enum):
    """Tree protection levels under Vancouver bylaw."""
    HERITAGE = "heritage"          # Extra protection, heritage designation
    SIGNIFICANT = "significant"    # 10-20cm DBH
    PROTECTED = "protected"        # 20cm+ DBH (permit required)
    UNPROTECTED = "unprotected"    # <10cm DBH


class ProtectedTree(BaseModel):
    """A single protected or heritage tree on a parcel."""
    id: int = Field(..., description="Unique tree identifier")
    species: str = Field(..., description="Tree species (e.g., Western Red Cedar)")
    dbh_cm: float = Field(..., ge=0, description="Diameter at breast height in cm")
    height_m: float = Field(..., ge=0, description="Tree height in meters")
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    protection_status: ProtectionStatus = Field(
        ..., description="Protection level under bylaw"
    )
    heritage_designation: Optional[str] = Field(
        None, description="Heritage name/date if applicable (e.g., BC Heritage Register)"
    )


class TreeCountResult(BaseModel):
    """Results of protected tree analysis for a parcel."""
    total_trees: int = Field(..., ge=0, description="Total protected trees found")
    heritage_trees: int = Field(..., ge=0, description="Trees with heritage designation")
    significant_trees: int = Field(..., ge=0, description="Trees 10-20cm DBH (significant)")
    protected_trees: int = Field(..., ge=0, description="Trees 20cm+ DBH (permit required)")
    estimated_removal_cost: float = Field(
        ..., ge=0, description="Total estimated removal cost (dollars)"
    )
    impact_score: float = Field(
        ..., ge=0, le=100, description="Tree impact score (0-100, higher = more impact)"
    )


class ProtectedTreeAnalyzer:
    """
    Analyzes protected and heritage trees on development parcels.

    Implements Vancouver tree bylaw rules and cost estimation heuristics
    for Bill 47 (TOA) feasibility analysis.
    """

    # Vancouver bylaw thresholds (cm DBH)
    MIN_PROTECTED_DBH = 20.0
    MIN_SIGNIFICANT_DBH = 10.0

    # Cost estimation ranges (per tree)
    STANDARD_REMOVAL_LOW = 500
    STANDARD_REMOVAL_HIGH = 5_000
    HERITAGE_REPLACEMENT_LOW = 1_000
    HERITAGE_REPLACEMENT_HIGH = 15_000

    def __init__(self):
        """Initialize the tree analyzer."""
        pass

    def count_protected_trees(self, trees: list[ProtectedTree]) -> TreeCountResult:
        """
        Count and analyze protected trees on a parcel.

        Returns TreeCountResult with counts, cost estimate, and impact score.
        """
        if not trees:
            return TreeCountResult(
                total_trees=0,
                heritage_trees=0,
                significant_trees=0,
                protected_trees=0,
                estimated_removal_cost=0.0,
                impact_score=0.0,
            )

        heritage_count = sum(1 for t in trees if t.protection_status == ProtectionStatus.HERITAGE)
        significant_count = sum(1 for t in trees if t.protection_status == ProtectionStatus.SIGNIFICANT)
        protected_count = sum(1 for t in trees if t.protection_status == ProtectionStatus.PROTECTED)

        # Compute removal cost
        removal_cost = self._estimate_total_removal_cost(trees)

        # Compute impact score (for meaningful results)
        impact_score = self.compute_tree_impact_score(
            tree_count=len(trees),
            total_dbh=sum(t.dbh_cm for t in trees),
        )

        return TreeCountResult(
            total_trees=len(trees),
            heritage_trees=heritage_count,
            significant_trees=significant_count,
            protected_trees=protected_count,
            estimated_removal_cost=removal_cost,
            impact_score=impact_score,
        )

    def estimate_removal_cost(self, tree_count: int, avg_dbh: float) -> float:
        """
        Estimate total removal cost for trees on a parcel.

        Heuristics:
        - Standard trees (10-20cm DBH): $500-$2K
        - Protected trees (20cm+ DBH): $2K-$5K
        - Heritage trees: $1K-$15K (use separate method)

        Args:
            tree_count: Number of trees to remove
            avg_dbh: Average diameter at breast height (cm)

        Returns:
            Estimated removal cost in dollars
        """
        if tree_count <= 0:
            return 0.0

        if avg_dbh < self.MIN_SIGNIFICANT_DBH:
            # No protection required
            return 0.0

        if avg_dbh < self.MIN_PROTECTED_DBH:
            # Significant trees: $500-$2K per tree
            cost_per_tree = self.STANDARD_REMOVAL_LOW + (
                (avg_dbh - self.MIN_SIGNIFICANT_DBH)
                / (self.MIN_PROTECTED_DBH - self.MIN_SIGNIFICANT_DBH)
                * (2_000 - self.STANDARD_REMOVAL_LOW)
            )
            return cost_per_tree * tree_count

        # Protected trees (20cm+): $2K-$5K per tree
        # Scale with DBH: 20cm = $2K, 50cm+ = $5K
        cost_per_tree = 2_000 + min(
            3_000,  # Cap at $5K total
            (avg_dbh - self.MIN_PROTECTED_DBH) * 100,
        )
        return cost_per_tree * tree_count

    def compute_tree_impact_score(
        self,
        tree_count: int,
        total_dbh: float,
    ) -> float:
        """
        Compute tree impact score (0-100) based on count and size.

        Factors:
        - Tree count: more trees = higher impact
        - DBH distribution: larger trees = higher impact
        - Heritage designation: already factored in selection

        Result: 0 = no trees, 100 = very significant tree cover.

        Args:
            tree_count: Number of trees on parcel
            total_dbh: Sum of all tree DBH values (cm)

        Returns:
            Impact score in range [0, 100]
        """
        if tree_count <= 0:
            return 0.0

        # Normalize scores
        # 1-3 trees: low impact (0-25)
        # 4-8 trees: moderate impact (25-50)
        # 9+ trees or high DBH: high impact (50-100)

        count_factor = min(100, (tree_count / 10.0) * 50)
        avg_dbh = total_dbh / tree_count if tree_count > 0 else 0
        dbh_factor = min(100, (avg_dbh / 40.0) * 50)  # 40cm avg = 50 points

        impact = count_factor + dbh_factor
        return min(100.0, max(0.0, impact))

    def get_trees_near_parcel(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        all_trees: Optional[list[ProtectedTree]] = None,
    ) -> list[ProtectedTree]:
        """
        Find all protected trees within radius of a geographic point.

        Uses simple Haversine approximation for small radii (<5km).
        In production, would use PostGIS spatial queries.

        Args:
            lat: Center latitude
            lng: Center longitude
            radius_m: Search radius in meters
            all_trees: List of all available trees (mock data for testing)

        Returns:
            List of ProtectedTree objects within radius
        """
        if not all_trees:
            return []

        nearby = []
        for tree in all_trees:
            distance = self._haversine_distance(lat, lng, tree.lat, tree.lng)
            if distance <= radius_m:
                nearby.append(tree)

        return sorted(nearby, key=lambda t: self._haversine_distance(lat, lng, t.lat, t.lng))

    def _estimate_total_removal_cost(self, trees: list[ProtectedTree]) -> float:
        """Sum removal costs across all trees by protection status."""
        total = 0.0

        for tree in trees:
            if tree.protection_status == ProtectionStatus.HERITAGE:
                # Heritage trees: high replacement cost
                cost = self._estimate_heritage_cost(tree)
            elif tree.protection_status == ProtectionStatus.PROTECTED:
                # Protected (20cm+ DBH): $2K-$5K
                cost = self._estimate_protected_cost(tree)
            elif tree.protection_status == ProtectionStatus.SIGNIFICANT:
                # Significant (10-20cm DBH): $500-$2K
                cost = self._estimate_significant_cost(tree)
            else:
                # Unprotected: minimal cost
                cost = 0.0

            total += cost

        return total

    def _estimate_heritage_cost(self, tree: ProtectedTree) -> float:
        """Estimate removal/replacement cost for heritage tree."""
        # Heritage trees: scale from $1K (small) to $15K (large)
        scale = min(1.0, tree.dbh_cm / 50.0)  # 50cm = full scale
        return self.HERITAGE_REPLACEMENT_LOW + (
            scale * (self.HERITAGE_REPLACEMENT_HIGH - self.HERITAGE_REPLACEMENT_LOW)
        )

    def _estimate_protected_cost(self, tree: ProtectedTree) -> float:
        """Estimate removal cost for protected tree (20cm+ DBH)."""
        # Protected: $2K baseline + scale to $5K at 50cm+
        scale = min(1.0, (tree.dbh_cm - self.MIN_PROTECTED_DBH) / 30.0)
        return 2_000 + (scale * 3_000)

    def _estimate_significant_cost(self, tree: ProtectedTree) -> float:
        """Estimate removal cost for significant tree (10-20cm DBH)."""
        # Significant: scale from $500 to $2K
        scale = (tree.dbh_cm - self.MIN_SIGNIFICANT_DBH) / (
            self.MIN_PROTECTED_DBH - self.MIN_SIGNIFICANT_DBH
        )
        return self.STANDARD_REMOVAL_LOW + (scale * (2_000 - self.STANDARD_REMOVAL_LOW))

    @staticmethod
    def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Compute approximate distance between two lat/lng points in meters.

        Uses simplified haversine formula suitable for small distances (<10km).
        For larger distances, error < 0.1%.
        """
        import math

        R_EARTH_M = 6_371_000  # Earth radius in meters

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R_EARTH_M * c

    def classify_tree_status(self, dbh_cm: float, is_heritage: bool = False) -> ProtectionStatus:
        """
        Classify a tree based on DBH and heritage status.

        Args:
            dbh_cm: Diameter at breast height (cm)
            is_heritage: Whether tree has heritage designation

        Returns:
            ProtectionStatus enum value
        """
        if is_heritage:
            return ProtectionStatus.HERITAGE

        if dbh_cm >= self.MIN_PROTECTED_DBH:
            return ProtectionStatus.PROTECTED

        if dbh_cm >= self.MIN_SIGNIFICANT_DBH:
            return ProtectionStatus.SIGNIFICANT

        return ProtectionStatus.UNPROTECTED
