"""
VanCity Lens — Protected Tree Analysis Tests (VCL-111: VAL-004)
Comprehensive test suite for protected and heritage tree analysis.

Tests cover:
- Tree counting and classification
- Cost estimation (standard, protected, heritage)
- Impact score calculation (0-100 bounds)
- Vancouver bylaw rules (20cm DBH threshold)
- Geographic proximity queries (Haversine distance)
- Edge cases and boundary conditions
"""

import math
import pytest

from api.protected_trees import (
    ProtectedTree,
    ProtectedTreeAnalyzer,
    ProtectionStatus,
    TreeCountResult,
)


class TestProtectionStatusEnum:
    """Test ProtectionStatus enum and values."""

    def test_protection_status_heritage(self):
        """Heritage status should exist."""
        assert ProtectionStatus.HERITAGE == "heritage"

    def test_protection_status_significant(self):
        """Significant status should exist."""
        assert ProtectionStatus.SIGNIFICANT == "significant"

    def test_protection_status_protected(self):
        """Protected status should exist."""
        assert ProtectionStatus.PROTECTED == "protected"

    def test_protection_status_unprotected(self):
        """Unprotected status should exist."""
        assert ProtectionStatus.UNPROTECTED == "unprotected"


class TestProtectedTreeModel:
    """Test ProtectedTree Pydantic model."""

    def test_tree_creation_valid(self):
        """Create a valid tree with all fields."""
        tree = ProtectedTree(
            id=1,
            species="Western Red Cedar",
            dbh_cm=35.5,
            height_m=25.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
            heritage_designation=None,
        )
        assert tree.id == 1
        assert tree.species == "Western Red Cedar"
        assert tree.dbh_cm == 35.5
        assert tree.height_m == 25.0
        assert tree.lat == 49.2827
        assert tree.lng == -123.1207
        assert tree.protection_status == ProtectionStatus.PROTECTED

    def test_tree_with_heritage_designation(self):
        """Tree can include heritage designation."""
        tree = ProtectedTree(
            id=2,
            species="Douglas Fir",
            dbh_cm=50.0,
            height_m=35.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.HERITAGE,
            heritage_designation="BC Heritage Register #12345",
        )
        assert tree.heritage_designation == "BC Heritage Register #12345"

    def test_tree_lat_bounds(self):
        """Latitude must be in [-90, 90]."""
        with pytest.raises(ValueError):
            ProtectedTree(
                id=3,
                species="Oak",
                dbh_cm=25.0,
                height_m=20.0,
                lat=91.0,  # Invalid
                lng=-123.0,
                protection_status=ProtectionStatus.PROTECTED,
            )

    def test_tree_lng_bounds(self):
        """Longitude must be in [-180, 180]."""
        with pytest.raises(ValueError):
            ProtectedTree(
                id=4,
                species="Oak",
                dbh_cm=25.0,
                height_m=20.0,
                lat=49.0,
                lng=181.0,  # Invalid
                protection_status=ProtectionStatus.PROTECTED,
            )

    def test_tree_dbh_non_negative(self):
        """DBH must be >= 0."""
        with pytest.raises(ValueError):
            ProtectedTree(
                id=5,
                species="Oak",
                dbh_cm=-5.0,  # Invalid
                height_m=20.0,
                lat=49.0,
                lng=-123.0,
                protection_status=ProtectionStatus.PROTECTED,
            )

    def test_tree_height_non_negative(self):
        """Height must be >= 0."""
        with pytest.raises(ValueError):
            ProtectedTree(
                id=6,
                species="Oak",
                dbh_cm=25.0,
                height_m=-10.0,  # Invalid
                lat=49.0,
                lng=-123.0,
                protection_status=ProtectionStatus.PROTECTED,
            )


class TestTreeCountResultModel:
    """Test TreeCountResult Pydantic model."""

    def test_result_creation_valid(self):
        """Create valid TreeCountResult."""
        result = TreeCountResult(
            total_trees=5,
            heritage_trees=1,
            significant_trees=2,
            protected_trees=2,
            estimated_removal_cost=15_000.0,
            impact_score=65.5,
        )
        assert result.total_trees == 5
        assert result.heritage_trees == 1
        assert result.significant_trees == 2
        assert result.protected_trees == 2
        assert result.estimated_removal_cost == 15_000.0
        assert result.impact_score == 65.5

    def test_result_impact_score_bounds(self):
        """Impact score must be in [0, 100]."""
        # Valid at boundaries
        result_low = TreeCountResult(
            total_trees=0,
            heritage_trees=0,
            significant_trees=0,
            protected_trees=0,
            estimated_removal_cost=0.0,
            impact_score=0.0,
        )
        assert result_low.impact_score == 0.0

        result_high = TreeCountResult(
            total_trees=20,
            heritage_trees=5,
            significant_trees=8,
            protected_trees=7,
            estimated_removal_cost=100_000.0,
            impact_score=100.0,
        )
        assert result_high.impact_score == 100.0

        # Invalid above 100
        with pytest.raises(ValueError):
            TreeCountResult(
                total_trees=1,
                heritage_trees=0,
                significant_trees=0,
                protected_trees=1,
                estimated_removal_cost=5_000.0,
                impact_score=101.0,  # Invalid
            )

        # Invalid below 0
        with pytest.raises(ValueError):
            TreeCountResult(
                total_trees=1,
                heritage_trees=0,
                significant_trees=0,
                protected_trees=1,
                estimated_removal_cost=5_000.0,
                impact_score=-1.0,  # Invalid
            )

    def test_result_cost_non_negative(self):
        """Removal cost must be >= 0."""
        with pytest.raises(ValueError):
            TreeCountResult(
                total_trees=1,
                heritage_trees=0,
                significant_trees=0,
                protected_trees=1,
                estimated_removal_cost=-100.0,  # Invalid
                impact_score=50.0,
            )


class TestProtectedTreeAnalyzerBasics:
    """Test ProtectedTreeAnalyzer initialization and basic properties."""

    def test_analyzer_creation(self):
        """Create ProtectedTreeAnalyzer instance."""
        analyzer = ProtectedTreeAnalyzer()
        assert analyzer is not None

    def test_analyzer_constants(self):
        """Check analyzer constants match Vancouver bylaw."""
        analyzer = ProtectedTreeAnalyzer()
        assert analyzer.MIN_PROTECTED_DBH == 20.0
        assert analyzer.MIN_SIGNIFICANT_DBH == 10.0
        assert analyzer.STANDARD_REMOVAL_LOW == 500
        assert analyzer.STANDARD_REMOVAL_HIGH == 5_000
        assert analyzer.HERITAGE_REPLACEMENT_LOW == 1_000
        assert analyzer.HERITAGE_REPLACEMENT_HIGH == 15_000


class TestTreeClassification:
    """Test tree protection status classification."""

    def test_classify_heritage_tree(self):
        """Heritage flag overrides DBH classification."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=35.0, is_heritage=True)
        assert status == ProtectionStatus.HERITAGE

    def test_classify_protected_tree(self):
        """Tree with DBH >= 20cm is protected."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=25.0, is_heritage=False)
        assert status == ProtectionStatus.PROTECTED

    def test_classify_protected_tree_boundary(self):
        """Tree with DBH exactly 20cm is protected."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=20.0, is_heritage=False)
        assert status == ProtectionStatus.PROTECTED

    def test_classify_significant_tree(self):
        """Tree with 10 <= DBH < 20cm is significant."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=15.0, is_heritage=False)
        assert status == ProtectionStatus.SIGNIFICANT

    def test_classify_significant_tree_boundary(self):
        """Tree with DBH exactly 10cm is significant."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=10.0, is_heritage=False)
        assert status == ProtectionStatus.SIGNIFICANT

    def test_classify_unprotected_tree(self):
        """Tree with DBH < 10cm is unprotected."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=5.0, is_heritage=False)
        assert status == ProtectionStatus.UNPROTECTED

    def test_classify_small_tree(self):
        """Very small tree is unprotected."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=0.5, is_heritage=False)
        assert status == ProtectionStatus.UNPROTECTED


class TestCostEstimation:
    """Test removal cost estimation formulas."""

    def test_estimate_removal_cost_zero_trees(self):
        """Zero trees should cost zero."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=0, avg_dbh=25.0)
        assert cost == 0.0

    def test_estimate_removal_cost_unprotected_trees(self):
        """Unprotected trees (< 10cm DBH) cost nothing."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=5, avg_dbh=5.0)
        assert cost == 0.0

    def test_estimate_removal_cost_significant_single(self):
        """Single significant tree (15cm DBH) in mid-range."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=15.0)
        # Should be between $500 and $2K
        assert 500 <= cost <= 2_000

    def test_estimate_removal_cost_significant_minimum(self):
        """Significant tree at minimum (10cm) should be near $500."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=10.0)
        assert 400 <= cost <= 600

    def test_estimate_removal_cost_significant_maximum(self):
        """Significant tree at maximum (20cm) should be near $2K."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=20.0)
        assert 1_900 <= cost <= 2_100

    def test_estimate_removal_cost_protected_minimum(self):
        """Protected tree at minimum (20cm) should be around $2K."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=20.0)
        assert 1_900 <= cost <= 2_100

    def test_estimate_removal_cost_protected_large(self):
        """Large protected tree (50cm) should be in upper range."""
        analyzer = ProtectedTreeAnalyzer()
        cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=50.0)
        assert cost >= 4_000  # Near $5K cap

    def test_estimate_removal_cost_multiple_trees(self):
        """Multiple trees should scale linearly."""
        analyzer = ProtectedTreeAnalyzer()
        single_cost = analyzer.estimate_removal_cost(tree_count=1, avg_dbh=25.0)
        multi_cost = analyzer.estimate_removal_cost(tree_count=3, avg_dbh=25.0)
        assert abs(multi_cost - (single_cost * 3)) < 10  # Allow small floating point error


class TestTreeCountAndAnalysis:
    """Test count_protected_trees method."""

    def test_count_empty_parcel(self):
        """Parcel with no trees should return zeros."""
        analyzer = ProtectedTreeAnalyzer()
        result = analyzer.count_protected_trees([])
        assert result.total_trees == 0
        assert result.heritage_trees == 0
        assert result.significant_trees == 0
        assert result.protected_trees == 0
        assert result.estimated_removal_cost == 0.0
        assert result.impact_score == 0.0

    def test_count_single_heritage_tree(self):
        """Single heritage tree should be counted correctly."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=1,
                species="Douglas Fir",
                dbh_cm=45.0,
                height_m=30.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.HERITAGE,
                heritage_designation="Heritage #001",
            )
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.total_trees == 1
        assert result.heritage_trees == 1
        assert result.significant_trees == 0
        assert result.protected_trees == 0
        assert result.estimated_removal_cost > 0
        assert 0 <= result.impact_score <= 100

    def test_count_mixed_protection_levels(self):
        """Parcel with mixed protection levels."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=1,
                species="Douglas Fir",
                dbh_cm=45.0,
                height_m=30.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.HERITAGE,
            ),
            ProtectedTree(
                id=2,
                species="Western Red Cedar",
                dbh_cm=35.0,
                height_m=25.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.PROTECTED,
            ),
            ProtectedTree(
                id=3,
                species="Oak",
                dbh_cm=15.0,
                height_m=18.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.SIGNIFICANT,
            ),
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.total_trees == 3
        assert result.heritage_trees == 1
        assert result.significant_trees == 1
        assert result.protected_trees == 1

    def test_count_multiple_heritage_trees(self):
        """Multiple heritage trees are counted correctly."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=i,
                species="Heritage Species",
                dbh_cm=40.0,
                height_m=25.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.HERITAGE,
            )
            for i in range(1, 4)
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.heritage_trees == 3
        assert result.total_trees == 3


class TestImpactScoreCalculation:
    """Test tree impact score (0-100 scale)."""

    def test_impact_score_zero_trees(self):
        """No trees should give zero impact."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=0, total_dbh=0.0)
        assert score == 0.0

    def test_impact_score_single_small_tree(self):
        """Single small tree should give low impact."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=1, total_dbh=10.0)
        assert 0 <= score < 25

    def test_impact_score_single_large_tree(self):
        """Single large tree should give moderate impact."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=1, total_dbh=50.0)
        assert 20 <= score <= 80

    def test_impact_score_multiple_moderate_trees(self):
        """Multiple moderate trees should give higher impact."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=5, total_dbh=100.0)
        assert 25 <= score <= 100

    def test_impact_score_many_large_trees(self):
        """Many large trees should give high impact."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=15, total_dbh=600.0)
        assert score > 50
        assert score <= 100

    def test_impact_score_bounds(self):
        """Impact score should never exceed 100."""
        analyzer = ProtectedTreeAnalyzer()
        # Extreme case: very many very large trees
        score = analyzer.compute_tree_impact_score(tree_count=1000, total_dbh=100_000.0)
        assert score <= 100.0

    def test_impact_score_bounds_minimum(self):
        """Impact score should never be negative."""
        analyzer = ProtectedTreeAnalyzer()
        score = analyzer.compute_tree_impact_score(tree_count=-1, total_dbh=-100.0)
        assert score >= 0.0


class TestHaversineDistance:
    """Test geographic distance calculation."""

    def test_haversine_same_point(self):
        """Distance to same point is zero."""
        analyzer = ProtectedTreeAnalyzer()
        distance = analyzer._haversine_distance(49.2827, -123.1207, 49.2827, -123.1207)
        assert abs(distance) < 0.1  # Allow tiny floating point error

    def test_haversine_distance_vancouver_to_burnaby(self):
        """Distance between Vancouver and Burnaby landmarks."""
        analyzer = ProtectedTreeAnalyzer()
        # Roughly 7 km difference
        distance = analyzer._haversine_distance(
            49.2827, -123.1207,  # Vancouver downtown
            49.2819, -122.9897,  # Burnaby
        )
        assert 5_000 < distance < 10_000  # Roughly 7 km

    def test_haversine_distance_symmetry(self):
        """Distance A->B should equal distance B->A."""
        analyzer = ProtectedTreeAnalyzer()
        dist_ab = analyzer._haversine_distance(49.2827, -123.1207, 49.3, -123.2)
        dist_ba = analyzer._haversine_distance(49.3, -123.2, 49.2827, -123.1207)
        assert abs(dist_ab - dist_ba) < 0.01

    def test_haversine_distance_small_offset(self):
        """Small lat/lng offset should give proportional distance."""
        analyzer = ProtectedTreeAnalyzer()
        # 0.001 degrees is approximately 111 meters
        distance = analyzer._haversine_distance(
            49.2827, -123.1207,
            49.2837, -123.1207,  # 0.001 degrees north
        )
        assert 100 < distance < 120  # Roughly 111 meters


class TestGetTreesNearParcel:
    """Test geographic proximity queries."""

    def test_get_trees_empty_list(self):
        """Empty tree list returns empty result."""
        analyzer = ProtectedTreeAnalyzer()
        trees = analyzer.get_trees_near_parcel(
            lat=49.2827,
            lng=-123.1207,
            radius_m=100,
            all_trees=[],
        )
        assert trees == []

    def test_get_trees_none_provided(self):
        """None tree list returns empty result."""
        analyzer = ProtectedTreeAnalyzer()
        trees = analyzer.get_trees_near_parcel(
            lat=49.2827,
            lng=-123.1207,
            radius_m=100,
            all_trees=None,
        )
        assert trees == []

    def test_get_trees_single_within_radius(self):
        """Single tree within radius is found."""
        analyzer = ProtectedTreeAnalyzer()
        tree = ProtectedTree(
            id=1,
            species="Oak",
            dbh_cm=25.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
        )
        result = analyzer.get_trees_near_parcel(
            lat=49.2827,
            lng=-123.1207,
            radius_m=100,
            all_trees=[tree],
        )
        assert len(result) == 1
        assert result[0].id == 1

    def test_get_trees_outside_radius(self):
        """Tree outside radius is not found."""
        analyzer = ProtectedTreeAnalyzer()
        tree = ProtectedTree(
            id=1,
            species="Oak",
            dbh_cm=25.0,
            height_m=20.0,
            lat=49.3,  # ~10km away
            lng=-123.0,
            protection_status=ProtectionStatus.PROTECTED,
        )
        result = analyzer.get_trees_near_parcel(
            lat=49.2827,
            lng=-123.1207,
            radius_m=5_000,  # 5km radius
            all_trees=[tree],
        )
        # Roughly 10km, outside 5km radius
        assert len(result) == 0

    def test_get_trees_multiple_sorted_by_distance(self):
        """Multiple trees within radius are sorted by distance."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=1,
                species="Oak",
                dbh_cm=25.0,
                height_m=20.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.PROTECTED,
            ),
            ProtectedTree(
                id=2,
                species="Cedar",
                dbh_cm=30.0,
                height_m=25.0,
                lat=49.2837,
                lng=-123.1207,
                protection_status=ProtectionStatus.PROTECTED,
            ),
            ProtectedTree(
                id=3,
                species="Fir",
                dbh_cm=35.0,
                height_m=30.0,
                lat=49.2827,
                lng=-123.1217,
                protection_status=ProtectionStatus.PROTECTED,
            ),
        ]
        result = analyzer.get_trees_near_parcel(
            lat=49.2827,
            lng=-123.1207,
            radius_m=2_000,
            all_trees=trees,
        )
        assert len(result) >= 1
        # Results should be sorted by distance (closest first)
        if len(result) > 1:
            for i in range(len(result) - 1):
                dist_i = analyzer._haversine_distance(
                    49.2827, -123.1207,
                    result[i].lat, result[i].lng,
                )
                dist_next = analyzer._haversine_distance(
                    49.2827, -123.1207,
                    result[i + 1].lat, result[i + 1].lng,
                )
                assert dist_i <= dist_next


class TestVancouverBylawRules:
    """Test Vancouver tree bylaw enforcement."""

    def test_bylaw_20cm_threshold(self):
        """Trees >= 20cm DBH require permit (protected)."""
        analyzer = ProtectedTreeAnalyzer()
        # Exactly 20cm
        status = analyzer.classify_tree_status(dbh_cm=20.0)
        assert status == ProtectionStatus.PROTECTED

        # Just below 20cm
        status = analyzer.classify_tree_status(dbh_cm=19.9)
        assert status == ProtectionStatus.SIGNIFICANT

    def test_bylaw_10cm_threshold(self):
        """Trees >= 10cm DBH are significant."""
        analyzer = ProtectedTreeAnalyzer()
        # Exactly 10cm
        status = analyzer.classify_tree_status(dbh_cm=10.0)
        assert status == ProtectionStatus.SIGNIFICANT

        # Just below 10cm
        status = analyzer.classify_tree_status(dbh_cm=9.9)
        assert status == ProtectionStatus.UNPROTECTED

    def test_bylaw_private_property_permit(self):
        """Protected trees on private property need permit."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=1,
                species="Cedar",
                dbh_cm=25.0,
                height_m=20.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.PROTECTED,
            )
        ]
        result = analyzer.count_protected_trees(trees)
        # Should have removal cost (removal permit required)
        assert result.estimated_removal_cost > 0
        assert result.protected_trees == 1


class TestHeritageTrees:
    """Test heritage tree special handling."""

    def test_heritage_tree_override(self):
        """Heritage designation overrides DBH classification."""
        analyzer = ProtectedTreeAnalyzer()
        status = analyzer.classify_tree_status(dbh_cm=8.0, is_heritage=True)
        assert status == ProtectionStatus.HERITAGE

    def test_heritage_tree_higher_cost(self):
        """Heritage trees have higher replacement cost."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=1,
                species="Heritage Oak",
                dbh_cm=40.0,
                height_m=25.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.HERITAGE,
                heritage_designation="Heritage Register",
            ),
            ProtectedTree(
                id=2,
                species="Standard Cedar",
                dbh_cm=40.0,
                height_m=25.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.PROTECTED,
            ),
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.heritage_trees == 1
        # Heritage tree should have higher total cost
        assert result.estimated_removal_cost >= 2_500

    def test_heritage_tree_cost_range(self):
        """Heritage tree cost is in expected range."""
        analyzer = ProtectedTreeAnalyzer()
        small_tree = ProtectedTree(
            id=1,
            species="Small Heritage",
            dbh_cm=10.0,
            height_m=15.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.HERITAGE,
        )
        large_tree = ProtectedTree(
            id=2,
            species="Large Heritage",
            dbh_cm=60.0,
            height_m=40.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.HERITAGE,
        )
        small_result = analyzer.count_protected_trees([small_tree])
        large_result = analyzer.count_protected_trees([large_tree])

        assert 1_000 <= small_result.estimated_removal_cost <= 15_000
        assert 1_000 <= large_result.estimated_removal_cost <= 15_000
        # Larger tree should cost more
        assert large_result.estimated_removal_cost > small_result.estimated_removal_cost


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_tree(self):
        """Very small tree (1mm DBH)."""
        analyzer = ProtectedTreeAnalyzer()
        tree = ProtectedTree(
            id=1,
            species="Seedling",
            dbh_cm=0.1,
            height_m=0.5,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.UNPROTECTED,
        )
        result = analyzer.count_protected_trees([tree])
        assert result.estimated_removal_cost == 0.0

    def test_very_large_tree(self):
        """Very large tree (150cm DBH, rare but possible)."""
        analyzer = ProtectedTreeAnalyzer()
        tree = ProtectedTree(
            id=1,
            species="Ancient Cedar",
            dbh_cm=150.0,
            height_m=50.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
        )
        result = analyzer.count_protected_trees([tree])
        assert result.estimated_removal_cost > 0
        assert 0 <= result.impact_score <= 100

    def test_many_trees_on_parcel(self):
        """Parcel with many trees (100+)."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=i,
                species="Tree species " + str(i % 5),
                dbh_cm=20.0 + (i % 30),
                height_m=20.0 + (i % 20),
                lat=49.2827 + (i % 10) * 0.001,
                lng=-123.1207 + (i % 10) * 0.001,
                protection_status=ProtectionStatus.PROTECTED,
            )
            for i in range(1, 101)
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.total_trees == 100
        assert result.protected_trees == 100
        assert result.estimated_removal_cost > 0
        assert 0 <= result.impact_score <= 100

    def test_zero_removal_cost_with_trees(self):
        """Tree list with only unprotected trees."""
        analyzer = ProtectedTreeAnalyzer()
        trees = [
            ProtectedTree(
                id=i,
                species="Seedling",
                dbh_cm=5.0,
                height_m=5.0,
                lat=49.2827,
                lng=-123.1207,
                protection_status=ProtectionStatus.UNPROTECTED,
            )
            for i in range(1, 6)
        ]
        result = analyzer.count_protected_trees(trees)
        assert result.total_trees == 5
        assert result.estimated_removal_cost == 0.0


class TestEstimateInternalMethods:
    """Test private cost estimation methods."""

    def test_estimate_heritage_cost_scaling(self):
        """Heritage cost scales with DBH."""
        analyzer = ProtectedTreeAnalyzer()
        small = ProtectedTree(
            id=1,
            species="Heritage",
            dbh_cm=15.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.HERITAGE,
        )
        large = ProtectedTree(
            id=2,
            species="Heritage",
            dbh_cm=60.0,
            height_m=40.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.HERITAGE,
        )
        small_cost = analyzer._estimate_heritage_cost(small)
        large_cost = analyzer._estimate_heritage_cost(large)
        assert small_cost < large_cost
        assert 1_000 <= small_cost <= 15_000
        assert 1_000 <= large_cost <= 15_000

    def test_estimate_protected_cost_scaling(self):
        """Protected cost scales with DBH above 20cm."""
        analyzer = ProtectedTreeAnalyzer()
        small = ProtectedTree(
            id=1,
            species="Protected",
            dbh_cm=20.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
        )
        large = ProtectedTree(
            id=2,
            species="Protected",
            dbh_cm=50.0,
            height_m=35.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
        )
        small_cost = analyzer._estimate_protected_cost(small)
        large_cost = analyzer._estimate_protected_cost(large)
        assert small_cost < large_cost
        assert 2_000 <= small_cost <= 5_000
        assert 2_000 <= large_cost <= 5_000

    def test_estimate_significant_cost_scaling(self):
        """Significant cost scales between 10-20cm DBH."""
        analyzer = ProtectedTreeAnalyzer()
        small = ProtectedTree(
            id=1,
            species="Significant",
            dbh_cm=10.0,
            height_m=15.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.SIGNIFICANT,
        )
        large = ProtectedTree(
            id=2,
            species="Significant",
            dbh_cm=20.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.SIGNIFICANT,
        )
        small_cost = analyzer._estimate_significant_cost(small)
        large_cost = analyzer._estimate_significant_cost(large)
        assert small_cost < large_cost
        assert 500 <= small_cost <= 2_000
        assert 500 <= large_cost <= 2_000


class TestDatabaseSchema:
    """Test expectations for protected_trees table schema."""

    def test_protected_tree_model_has_all_columns(self):
        """ProtectedTree model includes all expected columns."""
        tree = ProtectedTree(
            id=1,
            species="Oak",
            dbh_cm=25.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
            heritage_designation="Example",
        )
        # These should all be accessible
        assert hasattr(tree, "id")
        assert hasattr(tree, "species")
        assert hasattr(tree, "dbh_cm")
        assert hasattr(tree, "height_m")
        assert hasattr(tree, "lat")
        assert hasattr(tree, "lng")
        assert hasattr(tree, "protection_status")
        assert hasattr(tree, "heritage_designation")

    def test_protected_tree_geometry_fields(self):
        """Latitude and longitude are valid geometric coordinates."""
        tree = ProtectedTree(
            id=1,
            species="Oak",
            dbh_cm=25.0,
            height_m=20.0,
            lat=49.2827,
            lng=-123.1207,
            protection_status=ProtectionStatus.PROTECTED,
        )
        # In database: GEOMETRY(Point, 4326) means WGS84 lat/lng
        assert -90 <= tree.lat <= 90
        assert -180 <= tree.lng <= 180
