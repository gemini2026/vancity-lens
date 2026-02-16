"""
Tests for Parcel Click Enrichment (Task 1)

Covers:
- ILR (improvement-to-land ratio) computation edge cases
- Comparable sales PostGIS spatial query (mocked DB)
- Contamination proximity fetch
- ParcelEntitlementResponse model with new fields
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.models import ParcelEntitlementResponse, StationEntitlement, ValueEstimate, TOATier


# ════════════════════════════════════════════════════════════════════════════
# ILR COMPUTATION TESTS
# ════════════════════════════════════════════════════════════════════════════


class TestILRModel:
    """Test improvement_to_land_ratio field on ParcelEntitlementResponse."""

    def test_ilr_field_present_on_model(self):
        """Verify improvement_to_land_ratio field exists on the model."""
        fields = ParcelEntitlementResponse.model_fields
        assert "improvement_to_land_ratio" in fields
        assert "land_value" in fields
        assert "improvement_value" in fields
        assert "year_built" in fields

    def test_ilr_none_by_default(self):
        """Test ILR fields default to None."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
        )
        assert resp.improvement_to_land_ratio is None
        assert resp.land_value is None
        assert resp.improvement_value is None
        assert resp.year_built is None

    def test_ilr_typical_values(self):
        """Test ILR with typical land/improvement values."""
        # improvement = 700k, total = 2.5M → ILR = 0.28
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            land_value=1_800_000,
            improvement_value=700_000,
            improvement_to_land_ratio=0.28,
        )
        assert resp.improvement_to_land_ratio == 0.28
        assert resp.land_value == 1_800_000
        assert resp.improvement_value == 700_000

    def test_ilr_teardown_candidate(self):
        """Test ILR < 0.25 indicates teardown candidate."""
        # improvement = 200k, land = 1.8M → ILR = 0.1
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            land_value=1_800_000,
            improvement_value=200_000,
            improvement_to_land_ratio=0.1,
        )
        assert resp.improvement_to_land_ratio < 0.25

    def test_ilr_high_improvement(self):
        """Test ILR with high improvement value (new building)."""
        # improvement = 3M, land = 1M → ILR = 0.75
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            land_value=1_000_000,
            improvement_value=3_000_000,
            improvement_to_land_ratio=0.75,
        )
        assert resp.improvement_to_land_ratio == 0.75

    def test_year_built_stored(self):
        """Test year_built field stored correctly."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            year_built=1975,
        )
        assert resp.year_built == 1975


class TestILRComputation:
    """Test the ILR computation logic in entitlement.py."""

    def _compute_ilr(self, land_value, improvement_value):
        """Replicate the ILR computation logic from entitlement.py."""
        land_val = land_value if land_value else None
        improvement_val = improvement_value if improvement_value else None
        ilr = None
        if land_val is not None and improvement_val is not None:
            total = land_val + improvement_val
            if total > 0:
                ilr = round(improvement_val / total, 4)
        return ilr

    def test_ilr_both_positive(self):
        """Standard case: both values positive."""
        ilr = self._compute_ilr(1_800_000, 700_000)
        assert ilr == round(700_000 / 2_500_000, 4)

    def test_ilr_land_none(self):
        """land_value is None → ILR should be None."""
        ilr = self._compute_ilr(None, 700_000)
        assert ilr is None

    def test_ilr_improvement_none(self):
        """improvement_value is None → ILR should be None."""
        ilr = self._compute_ilr(1_800_000, None)
        assert ilr is None

    def test_ilr_both_none(self):
        """Both None → ILR should be None."""
        ilr = self._compute_ilr(None, None)
        assert ilr is None

    def test_ilr_both_zero(self):
        """Both zero → total is zero, division avoided, ILR should be None."""
        # 0 is falsy, so the `or None` pattern makes it None
        ilr = self._compute_ilr(0, 0)
        assert ilr is None

    def test_ilr_land_zero_improvement_positive(self):
        """land_value = 0, improvement positive → 0 is falsy → None."""
        ilr = self._compute_ilr(0, 500_000)
        assert ilr is None

    def test_ilr_improvement_zero_land_positive(self):
        """improvement_value = 0, land positive → 0 is falsy → None."""
        ilr = self._compute_ilr(1_000_000, 0)
        assert ilr is None

    def test_ilr_very_low(self):
        """Very low improvement → ILR close to 0 (vacant lot with minimal structure)."""
        ilr = self._compute_ilr(2_000_000, 50_000)
        expected = round(50_000 / 2_050_000, 4)
        assert ilr == expected
        assert ilr < 0.05

    def test_ilr_equal_values(self):
        """Equal land and improvement → ILR = 0.5."""
        ilr = self._compute_ilr(1_000_000, 1_000_000)
        assert ilr == 0.5

    def test_ilr_precision(self):
        """Test that ILR is rounded to 4 decimal places."""
        ilr = self._compute_ilr(3_000_000, 1_000_001)
        assert ilr is not None
        # Check it's rounded to 4 decimal places
        assert ilr == round(ilr, 4)


class TestILRInEntitlement:
    """Test ILR computation wired through compute_entitlement."""

    @pytest.fixture
    def mock_conn(self):
        """Mock asyncpg.Connection."""
        conn = AsyncMock()
        return conn

    @pytest.fixture
    def base_parcel_row(self):
        """Base parcel row dict simulating asyncpg fetchrow result."""
        return {
            "pid": "001-234-567",
            "civic_address": "1234 Main Street, Vancouver, BC",
            "current_zoning": "RM-4",
            "current_height": 6,
            "current_fsr": Decimal("2.5"),
            "lot_area_sqm": Decimal("500"),
            "assessed_value": 2_500_000,
            "assessed_year": 2024,
            "asking_price": 3_200_000,
            "land_value": 1_800_000,
            "improvement_value": 700_000,
            "year_built": 1975,
            "geo_local_area": "Mount Pleasant",
        }

    @pytest.mark.asyncio
    async def test_ilr_passed_through_entitlement(self, mock_conn, base_parcel_row):
        """Test that compute_entitlement passes ILR fields to response."""
        mock_conn.fetchrow.side_effect = [
            base_parcel_row,            # SQL_PARCEL_INFO
            None,                        # SQL_VIEW_CONE_CAP
            None,                        # SQL_HERITAGE_CHECK
            None,                        # SQL_MARKET_BENCHMARK
        ]
        mock_conn.fetch.return_value = []  # SQL_ENTITLEMENTS (no TOA)

        # Mock validation and sub-computations
        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):

            from api.entitlement import compute_entitlement
            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.land_value == 1_800_000
        assert result.improvement_value == 700_000
        assert result.year_built == 1975
        expected_ilr = round(700_000 / 2_500_000, 4)
        assert result.improvement_to_land_ratio == expected_ilr

    @pytest.mark.asyncio
    async def test_ilr_null_values_in_db(self, mock_conn, base_parcel_row):
        """Test ILR when land_value/improvement_value are NULL in DB."""
        base_parcel_row["land_value"] = None
        base_parcel_row["improvement_value"] = None
        base_parcel_row["year_built"] = None

        mock_conn.fetchrow.side_effect = [
            base_parcel_row,
            None,
            None,
            None,
        ]
        mock_conn.fetch.return_value = []

        with patch("api.entitlement.compute_validation", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_setbacks", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_bill44", new_callable=AsyncMock, return_value=None), \
             patch("api.entitlement.compute_community_plan_bonus", new_callable=AsyncMock, return_value=None):

            from api.entitlement import compute_entitlement
            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.land_value is None
        assert result.improvement_value is None
        assert result.year_built is None
        assert result.improvement_to_land_ratio is None


# ════════════════════════════════════════════════════════════════════════════
# COMPARABLE SALES POSTGIS QUERY TESTS
# ════════════════════════════════════════════════════════════════════════════


class TestComparableSalesRealQuery:
    """Test _fetch_real_comparables with mocked DB."""

    @pytest.mark.asyncio
    async def test_real_query_returns_results(self):
        """Test real PostGIS query returns comparable sales."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = [
            {
                "address": "100 Real St, Vancouver, BC",
                "price": Decimal("950000"),
                "sale_date": datetime(2025, 6, 15),
                "sqft": Decimal("2200"),
                "price_per_sqft": Decimal("431.82"),
                "distance_m": Decimal("150.5"),
                "property_type": "residential",
                "bedrooms": 3,
                "year_built": 2000,
            },
            {
                "address": "200 Real Ave, Vancouver, BC",
                "price": Decimal("1100000"),
                "sale_date": datetime(2025, 8, 1),
                "sqft": Decimal("2800"),
                "price_per_sqft": Decimal("392.86"),
                "distance_m": Decimal("400.2"),
                "property_type": "residential",
                "bedrooms": 4,
                "year_built": 2010,
            },
        ]

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.db.db", mock_db):
            # Need to import _after_ patching the module-level import
            # But since _fetch_real_comparables imports from .db, we patch the reference
            from api.comparable_sales_routes import _fetch_real_comparables
            results = await _fetch_real_comparables("001-234-567", 1000, 10, 12)

        assert results is not None
        assert len(results) == 2
        assert results[0].address == "100 Real St, Vancouver, BC"
        assert results[0].distance_m == 150.5

    @pytest.mark.asyncio
    async def test_real_query_parcel_not_found(self):
        """Test real query returns None when parcel not found."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.db.db", mock_db):
            from api.comparable_sales_routes import _fetch_real_comparables
            results = await _fetch_real_comparables("999-999-999", 1000, 10, 12)

        assert results is None

    @pytest.mark.asyncio
    async def test_real_query_no_results(self):
        """Test real query returns None when no comps found."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = []

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.db.db", mock_db):
            from api.comparable_sales_routes import _fetch_real_comparables
            results = await _fetch_real_comparables("001-234-567", 1000, 10, 12)

        assert results is None

    @pytest.mark.asyncio
    async def test_real_query_db_unavailable(self):
        """Test real query returns None when DB pool is unavailable."""
        mock_db = MagicMock()
        mock_db.acquire.side_effect = RuntimeError("Database not connected")

        with patch("api.db.db", mock_db):
            from api.comparable_sales_routes import _fetch_real_comparables
            results = await _fetch_real_comparables("001-234-567", 1000, 10, 12)

        assert results is None

    @pytest.mark.asyncio
    async def test_real_query_property_type_filter(self):
        """Test real query filters by property_type."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = [
            {
                "address": "100 Condo Ave",
                "price": Decimal("650000"),
                "sale_date": datetime(2025, 7, 1),
                "sqft": Decimal("900"),
                "price_per_sqft": Decimal("722.22"),
                "distance_m": Decimal("200"),
                "property_type": "condo",
                "bedrooms": 2,
                "year_built": 2015,
            },
            {
                "address": "200 House St",
                "price": Decimal("1200000"),
                "sale_date": datetime(2025, 8, 1),
                "sqft": Decimal("3000"),
                "price_per_sqft": Decimal("400"),
                "distance_m": Decimal("300"),
                "property_type": "residential",
                "bedrooms": 4,
                "year_built": 2005,
            },
        ]

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.db.db", mock_db):
            from api.comparable_sales_routes import _fetch_real_comparables
            results = await _fetch_real_comparables(
                "001-234-567", 1000, 10, 12, property_type="condo"
            )

        assert results is not None
        assert len(results) == 1
        assert results[0].property_type == "condo"

    @pytest.mark.asyncio
    async def test_fallback_to_mock_on_db_error(self):
        """Test that get_parcel_comparables falls back to mock data on DB error."""
        from api.comparable_sales_routes import get_parcel_comparables

        # _fetch_real_comparables will fail (no .db module connected), returning None
        with patch("api.comparable_sales_routes._fetch_real_comparables", new_callable=AsyncMock, return_value=None):
            result = await get_parcel_comparables(parcel_id="001-234-567")

        assert isinstance(result, list)
        assert len(result) > 0
        # These are from the mock data
        assert result[0].address == "123 Main St, Vancouver, BC"


# ════════════════════════════════════════════════════════════════════════════
# CONTAMINATION PROXIMITY FETCH TESTS
# ════════════════════════════════════════════════════════════════════════════


class TestContaminationProximityFetch:
    """Test the contaminated-sites parcel endpoint logic."""

    @pytest.mark.asyncio
    async def test_contamination_endpoint_response_shape(self):
        """Test the contamination endpoint returns expected structure."""
        # The endpoint is at api/data_sources_routes.py: parcel_contaminated_sites
        # We test the response shape by calling the function with a mocked DB
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = [
            {
                "id": 1,
                "site_id": "CS-001",
                "site_name": "Former Gas Station",
                "address": "500 Gas St, Vancouver, BC",
                "classification": "contaminated",
                "status": "active",
                "contamination_type": "petroleum",
                "date_reported": datetime(2020, 3, 15),
                "date_updated": datetime(2023, 6, 1),
                "distance_m": Decimal("35.2"),
            }
        ]

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.data_sources_routes.db", mock_db):
            from api.data_sources_routes import parcel_contaminated_sites
            result = await parcel_contaminated_sites(pid="001-234-567", radius_m=50)

        assert result["pid"] == "001-234-567"
        assert result["radius_m"] == 50
        assert result["has_contaminated_sites"] is True
        assert result["count"] == 1
        assert len(result["sites"]) == 1
        assert result["sites"][0]["site_name"] == "Former Gas Station"

    @pytest.mark.asyncio
    async def test_contamination_no_sites_found(self):
        """Test contamination endpoint when no sites are nearby."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = []

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.data_sources_routes.db", mock_db):
            from api.data_sources_routes import parcel_contaminated_sites
            result = await parcel_contaminated_sites(pid="001-234-567", radius_m=50)

        assert result["has_contaminated_sites"] is False
        assert result["count"] == 0
        assert result["sites"] == []

    @pytest.mark.asyncio
    async def test_contamination_parcel_not_found(self):
        """Test contamination endpoint when parcel PID is invalid."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        from fastapi import HTTPException
        with patch("api.data_sources_routes.db", mock_db):
            from api.data_sources_routes import parcel_contaminated_sites
            with pytest.raises(HTTPException) as exc_info:
                await parcel_contaminated_sites(pid="999-999-999", radius_m=50)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_contamination_multiple_sites(self):
        """Test contamination endpoint with multiple nearby sites."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"lng": -123.1, "lat": 49.28}
        mock_conn.fetch.return_value = [
            {
                "id": 1, "site_id": "CS-001", "site_name": "Site A",
                "address": "100 A St", "classification": "contaminated",
                "status": "active", "contamination_type": "petroleum",
                "date_reported": datetime(2020, 1, 1),
                "date_updated": datetime(2023, 1, 1),
                "distance_m": Decimal("10.5"),
            },
            {
                "id": 2, "site_id": "CS-002", "site_name": "Site B",
                "address": "200 B St", "classification": "suspected",
                "status": "under_review", "contamination_type": "heavy_metals",
                "date_reported": datetime(2021, 6, 1),
                "date_updated": datetime(2024, 1, 1),
                "distance_m": Decimal("42.3"),
            },
        ]

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.data_sources_routes.db", mock_db):
            from api.data_sources_routes import parcel_contaminated_sites
            result = await parcel_contaminated_sites(pid="001-234-567", radius_m=50)

        assert result["has_contaminated_sites"] is True
        assert result["count"] == 2


# ════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS: MODEL SERIALIZATION
# ════════════════════════════════════════════════════════════════════════════


class TestParcelEnrichmentSerialization:
    """Test that enriched ParcelEntitlementResponse serializes correctly."""

    def test_full_response_with_ilr_serializes(self):
        """Test model with all ILR fields serializes to JSON."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            land_value=1_800_000,
            improvement_value=700_000,
            year_built=1975,
            improvement_to_land_ratio=0.28,
        )
        json_data = resp.model_dump_json()
        assert "1800000" in json_data
        assert "700000" in json_data
        assert "1975" in json_data
        assert "0.28" in json_data

    def test_response_with_null_ilr_serializes(self):
        """Test model with null ILR fields serializes cleanly."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
        )
        data = resp.model_dump()
        assert data["land_value"] is None
        assert data["improvement_value"] is None
        assert data["year_built"] is None
        assert data["improvement_to_land_ratio"] is None
