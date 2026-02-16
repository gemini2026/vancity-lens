"""
Sprint 2 — Tests for Setbacks, Site Coverage, Pipeline Filters,
Developer Entity Resolution, and Pipeline Data Validation.
"""

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from api.setback_rules import (
    compute_setbacks,
    _estimate_net_area,
    SetbackResult,
)
from api.intelligence.developer_resolution import (
    normalize_developer_name,
    resolve_developer,
    search_developers,
    _similarity_score,
)
from api.intelligence.supply_pipeline import (
    PipelineEntryCreate,
    PipelineStage,
    SupplyPipelineTracker,
)


# ════════════════════════════════════════════════════════════════════════════
# SETBACK RULES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_conn():
    return AsyncMock()


class TestSetbackCalculation:
    """FR-HBU-008: Setback distance and site coverage calculation."""

    @pytest.mark.asyncio
    async def test_known_zoning_returns_correct_setbacks(self, mock_conn):
        """RS-1 zoning should return RS-1 specific setback values."""
        mock_conn.fetchrow.return_value = {
            "front_setback_m": Decimal("7.3"),
            "rear_setback_m": Decimal("7.9"),
            "side_setback_m": Decimal("1.2"),
            "max_site_coverage": Decimal("0.45"),
        }

        result = await compute_setbacks(mock_conn, "RS-1", Decimal("500"))

        assert result is not None
        assert result.front_setback_m == Decimal("7.3")
        assert result.rear_setback_m == Decimal("7.9")
        assert result.side_setback_m == Decimal("1.2")
        assert result.max_site_coverage == Decimal("0.45")
        assert result.is_default is False

    @pytest.mark.asyncio
    async def test_unknown_zoning_returns_defaults(self, mock_conn):
        """Unknown zoning should return default setback values."""
        mock_conn.fetchrow.return_value = None  # Not found in rules table

        result = await compute_setbacks(mock_conn, "UNKNOWN-99", Decimal("500"))

        assert result is not None
        assert result.front_setback_m == Decimal("6.0")
        assert result.rear_setback_m == Decimal("7.5")
        assert result.side_setback_m == Decimal("1.2")
        assert result.is_default is True

    @pytest.mark.asyncio
    async def test_null_zoning_returns_defaults(self, mock_conn):
        """None zoning should return defaults without DB call."""
        result = await compute_setbacks(mock_conn, None, Decimal("500"))

        assert result is not None
        assert result.is_default is True
        # Should not have queried the DB
        mock_conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_lot_area_returns_none(self, mock_conn):
        """No lot area means we can't compute setbacks."""
        result = await compute_setbacks(mock_conn, "RS-1", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_lot_area_returns_none(self, mock_conn):
        result = await compute_setbacks(mock_conn, "RS-1", Decimal("0"))
        assert result is None

    @pytest.mark.asyncio
    async def test_max_footprint_calculation(self, mock_conn):
        """max_footprint_sqm = lot_area × max_site_coverage."""
        mock_conn.fetchrow.return_value = {
            "front_setback_m": Decimal("3.7"),
            "rear_setback_m": Decimal("7.6"),
            "side_setback_m": Decimal("0.9"),
            "max_site_coverage": Decimal("0.55"),
        }

        result = await compute_setbacks(mock_conn, "RM-4", Decimal("800"))

        expected_footprint = (Decimal("800") * Decimal("0.55")).quantize(Decimal("0.01"))
        assert result.max_footprint_sqm == expected_footprint

    @pytest.mark.asyncio
    async def test_net_site_area_positive(self, mock_conn):
        """Net site area should be positive and less than lot area."""
        mock_conn.fetchrow.return_value = {
            "front_setback_m": Decimal("7.3"),
            "rear_setback_m": Decimal("7.9"),
            "side_setback_m": Decimal("1.2"),
            "max_site_coverage": Decimal("0.45"),
        }

        result = await compute_setbacks(mock_conn, "RS-1", Decimal("500"))

        assert result.net_site_area_sqm > 0
        assert result.net_site_area_sqm < Decimal("500")

    @pytest.mark.asyncio
    async def test_commercial_zero_setbacks(self, mock_conn):
        """Commercial zones (C-1, DD) may have zero setbacks."""
        mock_conn.fetchrow.return_value = {
            "front_setback_m": Decimal("0.0"),
            "rear_setback_m": Decimal("3.0"),
            "side_setback_m": Decimal("0.0"),
            "max_site_coverage": Decimal("0.75"),
        }

        result = await compute_setbacks(mock_conn, "C-1", Decimal("400"))

        assert result.front_setback_m == Decimal("0.0")
        assert result.side_setback_m == Decimal("0.0")
        assert result.max_site_coverage == Decimal("0.75")


class TestNetAreaEstimation:
    """Test the rectangular lot model for net area calculation."""

    def test_normal_lot(self):
        net = _estimate_net_area(Decimal("500"), Decimal("7.3"), Decimal("7.9"), Decimal("1.2"))
        assert net > 0
        assert net < Decimal("500")

    def test_tiny_setbacks(self):
        """Near-zero setbacks should give back most of the lot area."""
        net = _estimate_net_area(Decimal("1000"), Decimal("0.1"), Decimal("0.1"), Decimal("0.1"))
        assert net > Decimal("950")

    def test_huge_setbacks_still_positive(self):
        """Even large setbacks should not go negative."""
        net = _estimate_net_area(Decimal("100"), Decimal("20"), Decimal("20"), Decimal("10"))
        assert net >= 0

    def test_zero_lot_returns_zero(self):
        assert _estimate_net_area(Decimal("0"), Decimal("7"), Decimal("7"), Decimal("1")) == Decimal("0")


# ════════════════════════════════════════════════════════════════════════════
# DEVELOPER ENTITY RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

class TestDeveloperNameNormalization:
    """DV-PIPE-006: Developer name normalization."""

    def test_basic_normalization(self):
        assert normalize_developer_name("  abc  development  ") == "Abc Development"

    def test_abbreviation_expansion(self):
        assert "Corporation" in normalize_developer_name("Acme Corp")
        assert "Limited" in normalize_developer_name("Acme Ltd")
        assert "Development" in normalize_developer_name("Acme Dev")

    def test_trailing_punctuation_removed(self):
        result = normalize_developer_name("Acme Corp.")
        assert not result.endswith(".")

    def test_title_case(self):
        result = normalize_developer_name("APEX DEVELOPMENT GROUP")
        assert result == "Apex Development Group"

    def test_empty_string(self):
        assert normalize_developer_name("") == ""

    def test_whitespace_only(self):
        assert normalize_developer_name("   ") == ""


class TestSimilarityScore:
    """Test the fuzzy matching score function."""

    def test_identical_strings(self):
        assert _similarity_score("ABC", "ABC") == 1.0

    def test_case_insensitive(self):
        assert _similarity_score("ABC", "abc") == 1.0

    def test_substring_match(self):
        score = _similarity_score("ABC Dev", "ABC Development Group")
        assert score >= 0.8

    def test_unrelated_strings(self):
        score = _similarity_score("ABC", "XYZ")
        assert score <= 0.5


class TestDeveloperResolution:
    """Test full developer entity resolution pipeline."""

    @pytest.mark.asyncio
    async def test_exact_match(self, mock_conn):
        """Exact canonical name match returns the entity."""
        mock_conn.fetchrow.return_value = {
            "id": 1,
            "canonical_name": "Abc Development Corporation",
            "aliases": [],
            "bc_corp_number": None,
            "metadata": {},
        }

        result = await resolve_developer(mock_conn, "ABC Development Corp")

        assert result is not None
        assert result.id == 1
        assert result.canonical_name == "Abc Development Corporation"

    @pytest.mark.asyncio
    async def test_empty_name_returns_none(self, mock_conn):
        result = await resolve_developer(mock_conn, "")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_name_returns_none(self, mock_conn):
        result = await resolve_developer(mock_conn, "   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_creates_new_entity(self, mock_conn):
        """When no match found, creates a new entity."""
        # No exact match
        mock_conn.fetchrow.side_effect = [
            None,  # canonical name lookup
            None,  # alias lookup
            # INSERT RETURNING
            {
                "id": 99,
                "canonical_name": "Brand New Developer",
                "aliases": ["Brand New Developer"],
                "bc_corp_number": None,
                "metadata": {},
            },
        ]
        # No entities for fuzzy matching
        mock_conn.fetch.return_value = []

        result = await resolve_developer(mock_conn, "Brand New Developer")

        assert result is not None
        assert result.id == 99

    @pytest.mark.asyncio
    async def test_search_developers(self, mock_conn):
        """Search returns matching entities."""
        mock_conn.fetch.return_value = [
            {
                "id": 1,
                "canonical_name": "ABC Development",
                "aliases": ["ABC Dev"],
                "bc_corp_number": None,
                "metadata": {},
            },
        ]

        results = await search_developers(mock_conn, "ABC")

        assert len(results) == 1
        assert results[0].canonical_name == "ABC Development"


# ════════════════════════════════════════════════════════════════════════════
# PIPELINE DATA VALIDATION
# ════════════════════════════════════════════════════════════════════════════

class TestPipelineEntryValidation:
    """DV-PIPE: Pipeline entry data validation rules."""

    def test_valid_entry(self):
        """Normal entry passes validation."""
        entry = PipelineEntryCreate(
            parcel_pid="001-234-567",
            address="123 Main St",
            pipeline_stage=PipelineStage.REZONING_APPLICATION,
        )
        assert entry.parcel_pid == "001-234-567"

    def test_invalid_pid_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="Invalid PID"):
            PipelineEntryCreate(
                parcel_pid="BADPID",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
            )

    def test_storeys_too_high_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="proposed_storeys"):
            PipelineEntryCreate(
                parcel_pid="001-234-567",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
                proposed_storeys=200,
            )

    def test_storeys_zero_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="proposed_storeys"):
            PipelineEntryCreate(
                parcel_pid="001-234-567",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
                proposed_storeys=0,
            )

    def test_units_too_high_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="proposed_units"):
            PipelineEntryCreate(
                parcel_pid="001-234-567",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
                proposed_units=10000,
            )

    def test_completion_date_past_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="estimated_completion"):
            PipelineEntryCreate(
                parcel_pid="001-234-567",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
                estimated_completion=date(2019, 6, 1),
            )

    def test_completion_date_far_future_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="estimated_completion"):
            PipelineEntryCreate(
                parcel_pid="001-234-567",
                address="123 Main St",
                pipeline_stage=PipelineStage.REZONING_APPLICATION,
                estimated_completion=date(2051, 1, 1),
            )

    def test_valid_storeys_accepted(self):
        entry = PipelineEntryCreate(
            parcel_pid="001-234-567",
            address="123 Main St",
            pipeline_stage=PipelineStage.REZONING_APPLICATION,
            proposed_storeys=50,
        )
        assert entry.proposed_storeys == 50

    def test_valid_date_accepted(self):
        entry = PipelineEntryCreate(
            parcel_pid="001-234-567",
            address="123 Main St",
            pipeline_stage=PipelineStage.REZONING_APPLICATION,
            estimated_completion=date(2028, 6, 1),
        )
        assert entry.estimated_completion == date(2028, 6, 1)

    def test_null_optionals_accepted(self):
        """Optional fields can be None."""
        entry = PipelineEntryCreate(
            parcel_pid="001-234-567",
            address="123 Main St",
            pipeline_stage=PipelineStage.REZONING_APPLICATION,
            proposed_storeys=None,
            proposed_units=None,
            estimated_completion=None,
        )
        assert entry.proposed_storeys is None


# ════════════════════════════════════════════════════════════════════════════
# PIPELINE FILTERS (unit tests for the query builder)
# ════════════════════════════════════════════════════════════════════════════

class TestPipelineFilters:
    """FR-PIPE-005: Pipeline filtering by height, units, developer, polygon."""

    @pytest.fixture
    def mock_pool(self):
        pool = AsyncMock()
        pool.acquire = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool, conn

    @pytest.mark.asyncio
    async def test_height_filter(self, mock_pool):
        """Height range filter adds WHERE clauses."""
        pool, conn = mock_pool
        conn.fetchrow.return_value = {"total": 0}
        conn.fetch.return_value = []

        await SupplyPipelineTracker.get_pipeline(
            pool, height_min=5, height_max=20
        )

        # Verify the query was called with height params
        call_args = conn.fetch.call_args
        # The query should contain proposed_storeys >= and <=
        query = call_args[0][0]
        assert "proposed_storeys >=" in query
        assert "proposed_storeys <=" in query

    @pytest.mark.asyncio
    async def test_units_filter(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow.return_value = {"total": 0}
        conn.fetch.return_value = []

        await SupplyPipelineTracker.get_pipeline(
            pool, units_min=10, units_max=500
        )

        query = conn.fetch.call_args[0][0]
        assert "proposed_units >=" in query
        assert "proposed_units <=" in query

    @pytest.mark.asyncio
    async def test_developer_filter(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow.return_value = {"total": 0}
        conn.fetch.return_value = []

        await SupplyPipelineTracker.get_pipeline(
            pool, developer="Westbank"
        )

        query = conn.fetch.call_args[0][0]
        assert "developer ILIKE" in query

    @pytest.mark.asyncio
    async def test_combined_filters(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow.return_value = {"total": 0}
        conn.fetch.return_value = []

        await SupplyPipelineTracker.get_pipeline(
            pool,
            neighborhood="Downtown",
            stage="rezoning_application",
            height_min=10,
            developer="Bosa",
        )

        query = conn.fetch.call_args[0][0]
        assert "neighborhood =" in query
        assert "pipeline_stage =" in query
        assert "proposed_storeys >=" in query
        assert "developer ILIKE" in query

    @pytest.mark.asyncio
    async def test_polygon_filter(self, mock_pool):
        """Polygon filter uses ST_Intersects with GeoJSON."""
        pool, conn = mock_pool
        conn.fetch.return_value = []

        polygon = {
            "type": "Polygon",
            "coordinates": [[[-123.1, 49.2], [-123.1, 49.3], [-123.0, 49.3], [-123.0, 49.2], [-123.1, 49.2]]]
        }

        await SupplyPipelineTracker.get_pipeline_in_polygon(
            pool, geojson_polygon=polygon
        )

        query = conn.fetch.call_args[0][0]
        assert "ST_Intersects" in query
        assert "ST_GeomFromGeoJSON" in query


# ════════════════════════════════════════════════════════════════════════════
# SETBACK INTEGRATION WITH ENTITLEMENT
# ════════════════════════════════════════════════════════════════════════════

class TestSetbackInEntitlement:
    """Verify setbacks are included in the entitlement response."""

    @pytest.mark.asyncio
    async def test_entitlement_includes_setbacks(self):
        """compute_entitlement response includes setbacks dict."""
        from api.entitlement import compute_entitlement
        from api.models import DealValidation

        mock_conn = AsyncMock()
        parcel = {
            "pid": "001-234-567",
            "civic_address": "1234 Main St",
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

        setback_row = {
            "front_setback_m": Decimal("3.7"),
            "rear_setback_m": Decimal("7.6"),
            "side_setback_m": Decimal("0.9"),
            "max_site_coverage": Decimal("0.55"),
        }

        mock_conn.fetchrow.side_effect = [parcel, None, None, None, setback_row, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.setbacks is not None
        assert result.setbacks["front_setback_m"] == Decimal("3.7")
        assert result.setbacks["max_site_coverage"] == Decimal("0.55")
        assert result.setbacks["is_default"] is False
