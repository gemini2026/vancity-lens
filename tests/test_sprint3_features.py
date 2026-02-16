"""
Sprint 3 — Tests for Bill 44, Community Plans, Clustering, Stage Transitions.

Covers:
  - Bill 44 small-scale multi-unit housing entitlement
  - Community plan density bonus rules
  - Pipeline clustering detection
  - Stage transition alert generation
  - Integration with entitlement engine
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from api.bill44_entitlement import (
    compute_bill44,
    _determine_lot_category,
    Bill44Result,
)
from api.community_plan_rules import (
    compute_community_plan_bonus,
    CommunityPlanResult,
)
from api.intelligence.clustering import (
    detect_clusters,
    DevelopmentCluster,
    CLUSTER_RADIUS_M,
    CLUSTER_WINDOW_DAYS,
    CLUSTER_MIN_APPS,
)
from api.intelligence.supply_pipeline import _generate_stage_transition_alerts


# ════════════════════════════════════════════════════════════════════════════
# Bill 44 — Lot Size Categories
# ════════════════════════════════════════════════════════════════════════════

class TestLotSizeCategory:
    """Test _determine_lot_category thresholds."""

    def test_small_lot_under_280(self):
        cat, units = _determine_lot_category(Decimal("200"))
        assert cat == "small"
        assert units == 3

    def test_small_lot_boundary_279(self):
        cat, units = _determine_lot_category(Decimal("279.99"))
        assert cat == "small"
        assert units == 3

    def test_medium_lot_at_280(self):
        cat, units = _determine_lot_category(Decimal("280"))
        assert cat == "medium"
        assert units == 4

    def test_medium_lot_559(self):
        cat, units = _determine_lot_category(Decimal("559.99"))
        assert cat == "medium"
        assert units == 4

    def test_large_lot_at_560(self):
        cat, units = _determine_lot_category(Decimal("560"))
        assert cat == "large"
        assert units == 6

    def test_large_lot_1000(self):
        cat, units = _determine_lot_category(Decimal("1000"))
        assert cat == "large"
        assert units == 6


# ════════════════════════════════════════════════════════════════════════════
# Bill 44 — Eligibility Computation
# ════════════════════════════════════════════════════════════════════════════

class TestBill44Eligibility:
    """Test compute_bill44 with various zoning and lot scenarios."""

    @pytest.mark.asyncio
    async def test_rs1_eligible_large_lot(self):
        """RS-1 zoning is eligible, large lot → 6 units."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {"zoning_district": "RS-1", "zone_category": "single_family", "is_eligible": True, "notes": "Standard"},
            {"min_distance_m": Decimal("500")},  # within transit
        ]

        result = await compute_bill44(conn, "001-234-567", "RS-1", Decimal("600"))

        assert result.is_eligible is True
        assert result.zone_category == "single_family"
        assert result.lot_size_category == "large"
        assert result.max_units == 6
        assert result.transit_bonus is True
        assert result.effective_max_units == 7

    @pytest.mark.asyncio
    async def test_rs1_small_lot_no_transit(self):
        """RS-1 small lot, far from transit → 3 units, no bonus."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {"zoning_district": "RS-1", "zone_category": "single_family", "is_eligible": True, "notes": None},
            {"min_distance_m": Decimal("1500")},  # beyond 800m
        ]

        result = await compute_bill44(conn, "001-234-567", "RS-1", Decimal("200"))

        assert result.is_eligible is True
        assert result.max_units == 3
        assert result.transit_bonus is False
        assert result.effective_max_units == 3

    @pytest.mark.asyncio
    async def test_rt_duplex_medium_lot(self):
        """RT-1 duplex zoning, medium lot → 4 units."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {"zoning_district": "RT-1", "zone_category": "duplex", "is_eligible": True, "notes": None},
            {"min_distance_m": Decimal("900")},  # beyond 800m
        ]

        result = await compute_bill44(conn, "002-345-678", "RT-1", Decimal("400"))

        assert result.is_eligible is True
        assert result.zone_category == "duplex"
        assert result.max_units == 4
        assert result.transit_bonus is False

    @pytest.mark.asyncio
    async def test_rm4_not_eligible(self):
        """RM-4 zoning is NOT eligible for Bill 44."""
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # Not in eligible zones table

        result = await compute_bill44(conn, "003-456-789", "RM-4", Decimal("500"))

        assert result.is_eligible is False
        assert result.max_units == 0

    @pytest.mark.asyncio
    async def test_cd1_not_eligible(self):
        """CD-1 zoning is NOT eligible for Bill 44."""
        conn = AsyncMock()
        conn.fetchrow.return_value = None

        result = await compute_bill44(conn, "004-567-890", "CD-1", Decimal("2000"))

        assert result.is_eligible is False

    @pytest.mark.asyncio
    async def test_missing_zoning(self):
        """No zoning → not eligible, no DB calls."""
        conn = AsyncMock()
        result = await compute_bill44(conn, "005-678-901", None, Decimal("500"))

        assert result.is_eligible is False
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_lot_area(self):
        """No lot area → not eligible, no DB calls."""
        conn = AsyncMock()
        result = await compute_bill44(conn, "006-789-012", "RS-1", None)

        assert result.is_eligible is False
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_transit_at_boundary_800m(self):
        """Transit at exactly 800m → eligible for bonus."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {"zoning_district": "RS-1", "zone_category": "single_family", "is_eligible": True, "notes": None},
            {"min_distance_m": Decimal("800")},  # exactly at boundary
        ]

        result = await compute_bill44(conn, "007-890-123", "RS-1", Decimal("600"))

        assert result.transit_bonus is True
        assert result.effective_max_units == 7

    @pytest.mark.asyncio
    async def test_transit_just_beyond_800m(self):
        """Transit at 801m → no bonus."""
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {"zoning_district": "RS-1", "zone_category": "single_family", "is_eligible": True, "notes": None},
            {"min_distance_m": Decimal("801")},
        ]

        result = await compute_bill44(conn, "008-901-234", "RS-1", Decimal("600"))

        assert result.transit_bonus is False
        assert result.effective_max_units == 6


# ════════════════════════════════════════════════════════════════════════════
# Community Plan Density Bonuses
# ════════════════════════════════════════════════════════════════════════════

class TestCommunityPlanBonuses:
    """Test community plan density bonus lookup."""

    @pytest.mark.asyncio
    async def test_no_bonus_for_unknown_zoning(self):
        """Unknown zoning → no community plan bonus."""
        conn = AsyncMock()
        conn.fetch.return_value = []

        result = await compute_community_plan_bonus(conn, "RM-99")

        assert result.has_bonus is False
        assert len(result.bonuses) == 0

    @pytest.mark.asyncio
    async def test_no_bonus_for_null_zoning(self):
        """Null zoning → no community plan bonus, no DB call."""
        conn = AsyncMock()
        result = await compute_community_plan_bonus(conn, None)

        assert result.has_bonus is False
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_bonus(self):
        """Single matching community plan bonus."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "plan_name": "Cambie Corridor Plan",
                "plan_area": "Phase 3 - Cambie Village",
                "bonus_fsr": Decimal("1.50"),
                "bonus_storeys": 4,
                "max_fsr": Decimal("6.00"),
                "max_storeys": 24,
                "conditions": "20% below-market rental required",
            }
        ]

        result = await compute_community_plan_bonus(conn, "RS-1")

        assert result.has_bonus is True
        assert len(result.bonuses) == 1
        assert result.best_bonus.plan_name == "Cambie Corridor Plan"
        assert result.effective_max_fsr == Decimal("6.00")
        assert result.effective_max_storeys == 24

    @pytest.mark.asyncio
    async def test_multiple_bonuses_best_selected(self):
        """Multiple bonuses → best (highest FSR) selected."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "plan_name": "Cambie Corridor Plan",
                "plan_area": "Oakridge Town Centre",
                "bonus_fsr": Decimal("2.00"),
                "bonus_storeys": 8,
                "max_fsr": Decimal("7.50"),
                "max_storeys": 28,
                "conditions": "Mixed-use; 25% rental",
            },
            {
                "plan_name": "Cambie Corridor Plan",
                "plan_area": "Marine Landing",
                "bonus_fsr": Decimal("1.00"),
                "bonus_storeys": 2,
                "max_fsr": Decimal("5.00"),
                "max_storeys": 18,
                "conditions": "Community amenity contribution",
            },
        ]

        result = await compute_community_plan_bonus(conn, "RS-1")

        assert result.has_bonus is True
        assert len(result.bonuses) == 2
        # Best = highest max_fsr (SQL sorts DESC)
        assert result.best_bonus.max_fsr == Decimal("7.50")
        assert result.effective_max_storeys == 28

    @pytest.mark.asyncio
    async def test_bonus_conditions_preserved(self):
        """Conditions string is passed through."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            {
                "plan_name": "West End Plan",
                "plan_area": "Davie Village",
                "bonus_fsr": Decimal("1.00"),
                "bonus_storeys": 3,
                "max_fsr": Decimal("6.50"),
                "max_storeys": 22,
                "conditions": "Heritage density transfer; 30% social housing",
            }
        ]

        result = await compute_community_plan_bonus(conn, "RM-5")

        assert "heritage density transfer" in result.best_bonus.conditions.lower()


# ════════════════════════════════════════════════════════════════════════════
# Clustering Detection
# ════════════════════════════════════════════════════════════════════════════

class TestClusteringConfig:
    """Test clustering detection configuration constants."""

    def test_default_radius(self):
        assert CLUSTER_RADIUS_M == 500

    def test_default_window(self):
        assert CLUSTER_WINDOW_DAYS == 90

    def test_default_min_apps(self):
        assert CLUSTER_MIN_APPS == 3


class TestClusteringDetection:
    """Test clustering alert detection."""

    @pytest.mark.asyncio
    async def test_no_clusters_empty_pipeline(self):
        """Empty pipeline → no clusters."""
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        clusters = await detect_clusters(pool)
        assert len(clusters) == 0

    @pytest.mark.asyncio
    async def test_cluster_detected(self):
        """Pipeline with 3+ nearby entries → cluster detected."""
        import json
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        members = [
            {
                "pipeline_id": 2,
                "parcel_pid": "002-002-002",
                "address": "200 Main St",
                "pipeline_stage": "rezoning_application",
                "proposed_storeys": 15,
                "proposed_units": 100,
                "distance_m": 150.0,
            },
            {
                "pipeline_id": 3,
                "parcel_pid": "003-003-003",
                "address": "300 Main St",
                "pipeline_stage": "development_permit",
                "proposed_storeys": 20,
                "proposed_units": 200,
                "distance_m": 300.0,
            },
        ]

        conn.fetch.return_value = [
            {
                "center_pid": "001-001-001",
                "center_address": "100 Main St",
                "center_lat": 49.27,
                "center_lng": -123.10,
                "center_neighborhood": "Mount Pleasant",
                "cluster_size": 3,
                "members": json.dumps(members),
            }
        ]

        clusters = await detect_clusters(pool)
        assert len(clusters) == 1
        assert clusters[0].center_pid == "001-001-001"
        assert clusters[0].member_count == 3
        assert len(clusters[0].members) == 2
        assert clusters[0].total_proposed_units == 300

    @pytest.mark.asyncio
    async def test_cluster_members_as_list(self):
        """Members returned as list (not JSON string) also works."""
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        members_list = [
            {
                "pipeline_id": 10,
                "parcel_pid": "010-010-010",
                "address": "10 Test St",
                "pipeline_stage": "building_permit",
                "proposed_storeys": None,
                "proposed_units": None,
                "distance_m": 200.0,
            },
        ]

        conn.fetch.return_value = [
            {
                "center_pid": "009-009-009",
                "center_address": "9 Test St",
                "center_lat": 49.28,
                "center_lng": -123.11,
                "center_neighborhood": None,
                "cluster_size": 2,
                "members": members_list,  # Already a list
            }
        ]

        clusters = await detect_clusters(pool, min_apps=2)
        assert len(clusters) == 1
        assert clusters[0].member_count == 2

    @pytest.mark.asyncio
    async def test_deduplication_of_overlapping_clusters(self):
        """Overlapping clusters are deduplicated — center PID seen once."""
        import json
        pool = MagicMock()
        conn = AsyncMock()
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        m1 = [{"pipeline_id": 2, "parcel_pid": "002-002-002", "address": "B",
                "pipeline_stage": "rezoning_application", "proposed_storeys": 10,
                "proposed_units": 50, "distance_m": 100.0}]
        m2 = [{"pipeline_id": 1, "parcel_pid": "001-001-001", "address": "A",
                "pipeline_stage": "rezoning_application", "proposed_storeys": 10,
                "proposed_units": 50, "distance_m": 100.0}]

        conn.fetch.return_value = [
            {"center_pid": "001-001-001", "center_address": "A", "center_lat": 49.27,
             "center_lng": -123.10, "center_neighborhood": "Downtown", "cluster_size": 3,
             "members": json.dumps(m1)},
            {"center_pid": "002-002-002", "center_address": "B", "center_lat": 49.27,
             "center_lng": -123.10, "center_neighborhood": "Downtown", "cluster_size": 3,
             "members": json.dumps(m2)},
        ]

        clusters = await detect_clusters(pool)
        # Second cluster center (002-002-002) was a member of the first, so deduplicated
        assert len(clusters) == 1


# ════════════════════════════════════════════════════════════════════════════
# Stage Transition Alerts
# ════════════════════════════════════════════════════════════════════════════

class TestStageTransitionAlerts:
    """Test alert generation on pipeline stage transitions."""

    @pytest.mark.asyncio
    async def test_alert_generated_for_matching_watchlist(self):
        """Matching neighborhood watchlist → alert created."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 1,
            "address": "100 Main St",
            "neighborhood": "Mount Pleasant",
            "proposed_zoning": "CD-1",
            "current_zoning": "RS-1",
        }

        # Watchlist matches neighborhood
        conn.fetch.return_value = [{"watchlist_id": 42}]
        conn.execute.return_value = "INSERT 0 1"

        await _generate_stage_transition_alerts(
            conn, pipeline_row, "rezoning_application", "public_hearing"
        )

        # Should have queried watchlists and inserted an alert
        conn.fetch.assert_called_once()
        conn.execute.assert_called_once()
        # Verify the alert headline contains stage names
        call_args = conn.execute.call_args[0]
        assert "rezoning_application" in call_args[2]
        assert "public_hearing" in call_args[2]

    @pytest.mark.asyncio
    async def test_no_alert_when_no_matching_watchlist(self):
        """No matching watchlist → no alert created."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 2,
            "address": "200 Granville St",
            "neighborhood": "Kitsilano",
            "proposed_zoning": None,
            "current_zoning": "RS-1",
        }

        conn.fetch.return_value = []  # No matching watchlists

        await _generate_stage_transition_alerts(
            conn, pipeline_row, "development_permit", "building_permit"
        )

        conn.fetch.assert_called_once()
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_severity_high_for_construction(self):
        """under_construction or completed → severity 'high'."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 3,
            "address": "300 Cambie St",
            "neighborhood": "Fairview",
            "proposed_zoning": "RM-4",
            "current_zoning": "RS-1",
        }

        conn.fetch.return_value = [{"watchlist_id": 10}]
        conn.execute.return_value = "INSERT 0 1"

        await _generate_stage_transition_alerts(
            conn, pipeline_row, "building_permit", "under_construction"
        )

        call_args = conn.execute.call_args[0]
        severity = call_args[4]  # 5th positional arg
        assert severity == "high"

    @pytest.mark.asyncio
    async def test_alert_severity_medium_for_permit(self):
        """development_permit or building_permit → severity 'medium'."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 4,
            "address": "400 Broadway",
            "neighborhood": "Mount Pleasant",
            "proposed_zoning": "CD-1",
            "current_zoning": "RS-1",
        }

        conn.fetch.return_value = [{"watchlist_id": 20}]
        conn.execute.return_value = "INSERT 0 1"

        await _generate_stage_transition_alerts(
            conn, pipeline_row, "council_decision", "development_permit"
        )

        call_args = conn.execute.call_args[0]
        severity = call_args[4]
        assert severity == "medium"

    @pytest.mark.asyncio
    async def test_alert_not_fail_on_db_error(self):
        """DB error during alert generation should not raise."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 5,
            "address": "500 Hastings",
            "neighborhood": "Downtown",
            "proposed_zoning": None,
            "current_zoning": "C-2",
        }

        conn.fetch.side_effect = Exception("DB connection lost")

        # Should not raise
        await _generate_stage_transition_alerts(
            conn, pipeline_row, "rezoning_application", "public_hearing"
        )

    @pytest.mark.asyncio
    async def test_multiple_watchlists_generate_multiple_alerts(self):
        """Multiple matching watchlists → one alert per watchlist."""
        conn = AsyncMock()
        pipeline_row = {
            "id": 6,
            "address": "600 Main St",
            "neighborhood": "Strathcona",
            "proposed_zoning": "RM-4",
            "current_zoning": "RS-1",
        }

        conn.fetch.return_value = [
            {"watchlist_id": 1},
            {"watchlist_id": 2},
            {"watchlist_id": 3},
        ]
        conn.execute.return_value = "INSERT 0 1"

        await _generate_stage_transition_alerts(
            conn, pipeline_row, "public_hearing", "council_decision"
        )

        assert conn.execute.call_count == 3


# ════════════════════════════════════════════════════════════════════════════
# Integration: Bill 44 + Community Plan in Entitlement Response
# ════════════════════════════════════════════════════════════════════════════

class TestEntitlementIntegration:
    """Test that Bill 44 and community plan data appear in entitlement response."""

    @pytest.mark.asyncio
    async def test_bill44_included_in_response(self):
        """Entitlement response includes bill44 dict."""
        from api.entitlement import compute_entitlement
        from api.models import DealValidation

        conn = AsyncMock()
        parcel = {
            "pid": "001-234-567",
            "civic_address": "1234 Main St",
            "current_zoning": "RS-1",
            "current_height": 3,
            "current_fsr": Decimal("0.5"),
            "lot_area_sqm": Decimal("600"),
            "assessed_value": 1_800_000,
            "asking_price": None,
            "land_value": 1_600_000,
            "improvement_value": 200_000,
            "year_built": 2005,
            "geo_local_area": "South Vancouver",
        }
        ent = {
            "station_name": "Main Street Station",
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("4.0"),
            "distance_m": Decimal("150"),
            "current_height": 3,
            "current_fsr": Decimal("0.5"),
        }

        # fetchrow calls: parcel, view_cone, setback, bill44_eligibility
        bill44_eligible = {
            "zoning_district": "RS-1",
            "zone_category": "single_family",
            "is_eligible": True,
            "notes": "Standard",
        }
        transit_distance = {"min_distance_m": Decimal("150")}

        conn.fetchrow.side_effect = [parcel, None, None, None, None, bill44_eligible, transit_distance]  # parcel + view cone + heritage + benchmark + setback + bill44_eligibility + transit
        conn.fetch.side_effect = [[ent], []]  # entitlements + no community plan
        conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(conn, "001-234-567")

        assert result.bill44 is not None
        assert result.bill44["is_eligible"] is True
        assert result.bill44["zone_category"] == "single_family"
        assert result.bill44["max_units"] == 6  # large lot
        assert result.bill44["transit_bonus"] is True

    @pytest.mark.asyncio
    async def test_community_plan_included_when_applicable(self):
        """Entitlement response includes community_plan dict when bonus applies."""
        from api.entitlement import compute_entitlement
        from api.models import DealValidation

        conn = AsyncMock()
        parcel = {
            "pid": "002-345-678",
            "civic_address": "5678 Cambie St",
            "current_zoning": "RS-1",
            "current_height": 3,
            "current_fsr": Decimal("0.5"),
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 2_000_000,
            "asking_price": None,
            "land_value": 1_800_000,
            "improvement_value": 200_000,
            "year_built": 1990,
            "geo_local_area": "Riley Park",
        }
        ent = {
            "station_name": "King Edward Station",
            "tier": 2,
            "max_storeys": 12,
            "max_fsr": Decimal("2.5"),
            "distance_m": Decimal("350"),
            "current_height": 3,
            "current_fsr": Decimal("0.5"),
        }

        community_plan_row = {
            "plan_name": "Cambie Corridor Plan",
            "plan_area": "Phase 3 - Cambie Village",
            "bonus_fsr": Decimal("1.50"),
            "bonus_storeys": 4,
            "max_fsr": Decimal("6.00"),
            "max_storeys": 24,
            "conditions": "20% below-market rental required",
        }

        conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        conn.fetch.side_effect = [[ent], [community_plan_row]]  # entitlements + community plan
        conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(conn, "002-345-678")

        assert result.community_plan is not None
        assert result.community_plan["has_bonus"] is True
        assert result.community_plan["best_bonus"]["plan_name"] == "Cambie Corridor Plan"
        assert result.community_plan["effective_max_fsr"] == Decimal("6.00")

    @pytest.mark.asyncio
    async def test_no_community_plan_returns_none(self):
        """Entitlement response has community_plan=None when no bonus."""
        from api.entitlement import compute_entitlement
        from api.models import DealValidation

        conn = AsyncMock()
        parcel = {
            "pid": "003-456-789",
            "civic_address": "9999 Distant Ave",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.5"),
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 2_500_000,
            "asking_price": 3_200_000,
            "land_value": 1_800_000,
            "improvement_value": 700_000,
            "year_built": 1975,
            "geo_local_area": "Mount Pleasant",
        }
        ent = {
            "station_name": "Main Street Station",
            "tier": 1,
            "max_storeys": 20,
            "max_fsr": Decimal("4.0"),
            "distance_m": Decimal("150"),
            "current_height": 6,
            "current_fsr": Decimal("2.5"),
        }

        conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        conn.fetch.side_effect = [[ent], []]  # entitlements + no community plan
        conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(conn, "003-456-789")

        assert result.community_plan is None
