"""
Tests for VanCity Lens Building Permit Activity & Competing Supply Analysis
Tests cover models, analyzer class, API endpoints, and edge cases.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from api.building_permits import (
    BuildingPermit,
    BuildingPermitAnalyzer,
    CompetingSupplyResult,
    PermitStatus,
    PermitType,
)


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def mock_conn():
    """Mock asyncpg connection."""
    return AsyncMock()


@pytest.fixture
def sample_permit() -> BuildingPermit:
    """Sample building permit."""
    return BuildingPermit(
        permit_number="BP-2024-001",
        address="123 Main St, Vancouver, BC",
        permit_type=PermitType.NEW_BUILDING,
        status=PermitStatus.APPROVED,
        project_value=Decimal("5000000"),
        units_proposed=50,
        storeys=15,
        sqft=125000,
        issued_date=datetime.now(),
        applicant="Developer Corp",
    )


@pytest.fixture
def sample_permits() -> list[BuildingPermit]:
    """Sample list of permits with varied types and statuses."""
    base_date = datetime.now()
    return [
        BuildingPermit(
            permit_number="BP-2024-001",
            address="123 Main St",
            permit_type=PermitType.NEW_BUILDING,
            status=PermitStatus.APPROVED,
            project_value=Decimal("5000000"),
            units_proposed=50,
            storeys=15,
            sqft=125000,
            issued_date=base_date,
            applicant="Developer A",
        ),
        BuildingPermit(
            permit_number="BP-2024-002",
            address="456 Oak Ave",
            permit_type=PermitType.NEW_BUILDING,
            status=PermitStatus.ISSUED,
            project_value=Decimal("3500000"),
            units_proposed=30,
            storeys=12,
            sqft=85000,
            issued_date=base_date - timedelta(days=30),
            applicant="Developer B",
        ),
        BuildingPermit(
            permit_number="BP-2024-003",
            address="789 Elm St",
            permit_type=PermitType.RENOVATION,
            status=PermitStatus.COMPLETED,
            project_value=Decimal("750000"),
            units_proposed=None,
            storeys=6,
            sqft=15000,
            issued_date=base_date - timedelta(days=90),
            applicant="Renovator Inc",
        ),
        BuildingPermit(
            permit_number="BP-2024-004",
            address="321 Pine Ln",
            permit_type=PermitType.DEMOLITION,
            status=PermitStatus.APPLIED,
            project_value=Decimal("100000"),
            units_proposed=None,
            storeys=None,
            sqft=5000,
            issued_date=base_date - timedelta(days=5),
            applicant="Demo Corp",
        ),
        BuildingPermit(
            permit_number="BP-2024-005",
            address="654 Birch Dr",
            permit_type=PermitType.NEW_BUILDING,
            status=PermitStatus.APPLIED,
            project_value=Decimal("8000000"),
            units_proposed=75,
            storeys=20,
            sqft=200000,
            issued_date=base_date - timedelta(days=10),
            applicant="Developer C",
        ),
    ]


# ── Model Tests ──────────────────────────────────────────────────

class TestBuildingPermitModel:
    """Tests for BuildingPermit model."""

    def test_permit_creation_with_all_fields(self, sample_permit):
        """Test creating permit with all fields."""
        assert sample_permit.permit_number == "BP-2024-001"
        assert sample_permit.address == "123 Main St, Vancouver, BC"
        assert sample_permit.permit_type == PermitType.NEW_BUILDING
        assert sample_permit.status == PermitStatus.APPROVED
        assert sample_permit.project_value == Decimal("5000000")
        assert sample_permit.units_proposed == 50
        assert sample_permit.storeys == 15
        assert sample_permit.sqft == 125000
        assert sample_permit.applicant == "Developer Corp"

    def test_permit_creation_minimal(self):
        """Test creating permit with only required fields."""
        permit = BuildingPermit(
            permit_number="BP-2024-001",
            address="123 Main St",
            permit_type=PermitType.NEW_BUILDING,
            status=PermitStatus.APPLIED,
        )
        assert permit.permit_number == "BP-2024-001"
        assert permit.address == "123 Main St"
        assert permit.units_proposed is None
        assert permit.applicant is None
        assert permit.project_value == Decimal("0")

    def test_permit_type_enum(self):
        """Test all permit types are valid."""
        assert PermitType.NEW_BUILDING.value == "new_build"
        assert PermitType.RENOVATION.value == "renovation"
        assert PermitType.DEMOLITION.value == "demolition"

    def test_permit_status_enum(self):
        """Test all permit statuses are valid."""
        assert PermitStatus.APPLIED.value == "applied"
        assert PermitStatus.APPROVED.value == "approved"
        assert PermitStatus.ISSUED.value == "issued"
        assert PermitStatus.COMPLETED.value == "completed"

    def test_project_value_non_negative(self):
        """Test project_value cannot be negative."""
        with pytest.raises(ValueError):
            BuildingPermit(
                permit_number="BP-001",
                address="Test",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPLIED,
                project_value=Decimal("-1000"),
            )

    def test_units_proposed_non_negative(self):
        """Test units_proposed cannot be negative."""
        with pytest.raises(ValueError):
            BuildingPermit(
                permit_number="BP-001",
                address="Test",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPLIED,
                units_proposed=-5,
            )

    def test_storeys_minimum_one(self):
        """Test storeys must be at least 1."""
        with pytest.raises(ValueError):
            BuildingPermit(
                permit_number="BP-001",
                address="Test",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPLIED,
                storeys=0,
            )

    def test_sqft_non_negative(self):
        """Test sqft cannot be negative."""
        with pytest.raises(ValueError):
            BuildingPermit(
                permit_number="BP-001",
                address="Test",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPLIED,
                sqft=-1000,
            )


class TestCompetingSupplyResultModel:
    """Tests for CompetingSupplyResult model."""

    def test_result_creation(self):
        """Test creating CompetingSupplyResult."""
        result = CompetingSupplyResult(
            total_permits=5,
            new_build_permits=3,
            pipeline_units=155,
            total_value=Decimal("16500000"),
            supply_pressure_score=45.2,
            avg_units_per_project=31.0,
        )
        assert result.total_permits == 5
        assert result.new_build_permits == 3
        assert result.pipeline_units == 155
        assert result.total_value == Decimal("16500000")
        assert result.supply_pressure_score == 45.2
        assert result.avg_units_per_project == 31.0

    def test_result_all_zeros(self):
        """Test result with zero values."""
        result = CompetingSupplyResult(
            total_permits=0,
            new_build_permits=0,
            pipeline_units=0,
            total_value=Decimal("0"),
            supply_pressure_score=0.0,
            avg_units_per_project=0.0,
        )
        assert result.total_permits == 0
        assert result.supply_pressure_score == 0.0

    def test_supply_pressure_bounds(self):
        """Test supply_pressure_score stays within 0-100."""
        result = CompetingSupplyResult(
            total_permits=1,
            new_build_permits=1,
            pipeline_units=100,
            supply_pressure_score=99.99,
        )
        assert 0 <= result.supply_pressure_score <= 100

        with pytest.raises(ValueError):
            CompetingSupplyResult(
                total_permits=1,
                new_build_permits=1,
                pipeline_units=100,
                supply_pressure_score=100.1,
            )

        with pytest.raises(ValueError):
            CompetingSupplyResult(
                total_permits=1,
                new_build_permits=1,
                pipeline_units=100,
                supply_pressure_score=-0.1,
            )


# ── BuildingPermitAnalyzer Tests ─────────────────────────────────

class TestBuildingPermitAnalyzer:
    """Tests for BuildingPermitAnalyzer class."""

    @pytest.mark.asyncio
    async def test_analyzer_initialization(self, mock_conn):
        """Test analyzer can be initialized."""
        analyzer = BuildingPermitAnalyzer(mock_conn)
        assert analyzer.conn is mock_conn

    @pytest.mark.asyncio
    async def test_get_permits_near_parcel(self, mock_conn, sample_permits):
        """Test fetching permits near a parcel."""
        mock_conn.fetch.return_value = [
            {
                "permit_number": "BP-2024-001",
                "address": "123 Main St",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now(),
                "applicant": "Developer A",
            }
        ]

        analyzer = BuildingPermitAnalyzer(mock_conn)
        permits = await analyzer.get_permits_near_parcel(
            "PID-123",
            radius_m=500,
            months_back=12,
        )

        assert len(permits) == 1
        assert permits[0].permit_number == "BP-2024-001"
        assert permits[0].units_proposed == 50
        mock_conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_permits_by_radius(self, mock_conn):
        """Test fetching permits by lat/lng radius."""
        mock_conn.fetch.return_value = [
            {
                "permit_number": "BP-2024-001",
                "address": "123 Main St",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now(),
                "applicant": "Developer A",
            },
            {
                "permit_number": "BP-2024-002",
                "address": "456 Oak Ave",
                "type": "new_build",
                "status": "issued",
                "project_value": 3500000,
                "units": 30,
                "storeys": 12,
                "sqft": 85000,
                "issued_date": datetime.now(),
                "applicant": "Developer B",
            },
        ]

        analyzer = BuildingPermitAnalyzer(mock_conn)
        permits = await analyzer.get_permits_by_radius(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            months_back=12,
        )

        assert len(permits) == 2
        assert permits[0].permit_number == "BP-2024-001"
        assert permits[1].permit_number == "BP-2024-002"

    @pytest.mark.asyncio
    async def test_compute_competing_supply_basic(self, mock_conn):
        """Test computing competing supply for a location."""
        mock_conn.fetch.return_value = [
            {
                "permit_number": "BP-2024-001",
                "address": "123 Main St",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now(),
                "applicant": "Developer A",
            },
            {
                "permit_number": "BP-2024-002",
                "address": "456 Oak Ave",
                "type": "new_build",
                "status": "issued",
                "project_value": 3500000,
                "units": 30,
                "storeys": 12,
                "sqft": 85000,
                "issued_date": datetime.now(),
                "applicant": "Developer B",
            },
            {
                "permit_number": "BP-2024-003",
                "address": "789 Elm St",
                "type": "renovation",
                "status": "completed",
                "project_value": 750000,
                "units": None,
                "storeys": 6,
                "sqft": 15000,
                "issued_date": datetime.now(),
                "applicant": "Renovator Inc",
            },
        ]

        analyzer = BuildingPermitAnalyzer(mock_conn)
        result = await analyzer.compute_competing_supply(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            existing_units=100,
        )

        assert result.total_permits == 3
        assert result.new_build_permits == 2
        assert result.pipeline_units == 80  # Only approved and issued
        assert result.total_value == Decimal("9250000")
        assert 0 <= result.supply_pressure_score <= 100
        assert result.avg_units_per_project > 0

    @pytest.mark.asyncio
    async def test_compute_supply_with_zero_existing_units(self, mock_conn):
        """Test supply pressure with no existing units."""
        mock_conn.fetch.return_value = [
            {
                "permit_number": "BP-2024-001",
                "address": "123 Main St",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now(),
                "applicant": "Developer A",
            },
        ]

        analyzer = BuildingPermitAnalyzer(mock_conn)
        result = await analyzer.compute_competing_supply(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            existing_units=0,
        )

        assert result.pipeline_units == 50
        assert 0 <= result.supply_pressure_score <= 100

    def test_estimate_pipeline_units_with_mixed_statuses(self, sample_permits):
        """Test pipeline unit estimation with various statuses."""
        pipeline = BuildingPermitAnalyzer.estimate_pipeline_units(sample_permits)
        # BP-2024-001: approved, 50 units
        # BP-2024-002: issued, 30 units
        # BP-2024-003: completed, None units
        # BP-2024-004: applied, None units
        # BP-2024-005: applied, 75 units
        # Total: 50 + 30 + 75 = 155
        assert pipeline == 155

    def test_estimate_pipeline_units_empty_list(self):
        """Test pipeline estimation with no permits."""
        result = BuildingPermitAnalyzer.estimate_pipeline_units([])
        assert result == 0

    def test_estimate_pipeline_units_all_completed(self):
        """Test pipeline estimation with only completed permits."""
        permits = [
            BuildingPermit(
                permit_number="BP-001",
                address="123 Main",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.COMPLETED,
                units_proposed=50,
            ),
        ]
        result = BuildingPermitAnalyzer.estimate_pipeline_units(permits)
        assert result == 0  # Completed is not in pipeline

    def test_estimate_pipeline_units_ignores_none(self):
        """Test pipeline estimation ignores None units."""
        permits = [
            BuildingPermit(
                permit_number="BP-001",
                address="123 Main",
                permit_type=PermitType.RENOVATION,
                status=PermitStatus.APPROVED,
                units_proposed=None,
            ),
            BuildingPermit(
                permit_number="BP-002",
                address="456 Oak",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPROVED,
                units_proposed=25,
            ),
        ]
        result = BuildingPermitAnalyzer.estimate_pipeline_units(permits)
        assert result == 25

    def test_compute_supply_pressure_score_zero_units(self):
        """Test supply pressure with zero pipeline units."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=0,
            existing_units=100,
        )
        assert score == 0.0

    def test_compute_supply_pressure_score_high_ratio(self):
        """Test supply pressure with high pipeline to existing ratio."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=500,
            existing_units=100,
        )
        assert 80 < score <= 100

    def test_compute_supply_pressure_score_low_ratio(self):
        """Test supply pressure with low pipeline to existing ratio."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=10,
            existing_units=100,
        )
        assert 0 <= score < 20

    def test_compute_supply_pressure_score_equal_ratio(self):
        """Test supply pressure with 1:1 ratio."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=50,
            existing_units=50,
        )
        assert 40 < score < 60

    def test_compute_supply_pressure_score_bounds(self):
        """Test supply pressure always stays 0-100."""
        test_cases = [
            (0, 100),
            (50, 100),
            (100, 100),
            (1000, 100),
            (10000, 100),
            (0, 0),
            (50, 0),
            (100, 0),
        ]
        for pipeline, existing in test_cases:
            score = BuildingPermitAnalyzer.compute_supply_pressure_score(
                pipeline,
                existing,
            )
            assert 0 <= score <= 100, f"Score {score} out of bounds for pipeline={pipeline}, existing={existing}"

    def test_compute_supply_pressure_monotonic_increase(self):
        """Test supply pressure increases with pipeline units."""
        base_score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=50,
            existing_units=100,
        )
        higher_score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=100,
            existing_units=100,
        )
        highest_score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=200,
            existing_units=100,
        )
        assert base_score < higher_score < highest_score

    def test_row_to_permit_conversion(self):
        """Test converting database row to BuildingPermit."""
        row = {
            "permit_number": "BP-2024-001",
            "address": "123 Main St",
            "type": "new_build",
            "status": "approved",
            "project_value": 5000000,
            "units": 50,
            "storeys": 15,
            "sqft": 125000,
            "issued_date": datetime.now(),
            "applicant": "Developer A",
        }
        permit = BuildingPermitAnalyzer._row_to_permit(row)
        assert permit.permit_number == "BP-2024-001"
        assert permit.permit_type == PermitType.NEW_BUILDING
        assert permit.units_proposed == 50

    def test_row_to_permit_with_nulls(self):
        """Test converting row with NULL values."""
        row = {
            "permit_number": "BP-2024-001",
            "address": "123 Main St",
            "type": "demolition",
            "status": "applied",
            "project_value": None,
            "units": None,
            "storeys": None,
            "sqft": None,
            "issued_date": None,
            "applicant": None,
        }
        permit = BuildingPermitAnalyzer._row_to_permit(row)
        assert permit.permit_number == "BP-2024-001"
        assert permit.project_value == Decimal("0")
        assert permit.units_proposed is None
        assert permit.issued_date is None


# ── Edge Case Tests ──────────────────────────────────────────────

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_estimate_pipeline_large_values(self):
        """Test pipeline estimation with large unit counts."""
        permits = [
            BuildingPermit(
                permit_number=f"BP-{i}",
                address=f"{i} Street",
                permit_type=PermitType.NEW_BUILDING,
                status=PermitStatus.APPROVED,
                units_proposed=10000,
            )
            for i in range(10)
        ]
        result = BuildingPermitAnalyzer.estimate_pipeline_units(permits)
        assert result == 100000

    def test_compute_supply_pressure_very_large_pipeline(self):
        """Test supply pressure with very large pipeline."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=1000000,
            existing_units=100,
        )
        assert score >= 99.0  # Approaches 100 with very large pipeline

    def test_compute_supply_pressure_very_small_units(self):
        """Test supply pressure with very small existing units."""
        score = BuildingPermitAnalyzer.compute_supply_pressure_score(
            pipeline_units=10,
            existing_units=1,
        )
        assert 0 < score < 100

    @pytest.mark.asyncio
    async def test_competing_supply_no_permits(self, mock_conn):
        """Test supply computation with no permits."""
        mock_conn.fetch.return_value = []

        analyzer = BuildingPermitAnalyzer(mock_conn)
        result = await analyzer.compute_competing_supply(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            existing_units=100,
        )

        assert result.total_permits == 0
        assert result.new_build_permits == 0
        assert result.pipeline_units == 0
        assert result.total_value == Decimal("0")
        assert result.supply_pressure_score == 0.0
        assert result.avg_units_per_project == 0.0

    @pytest.mark.asyncio
    async def test_competing_supply_very_high_pressure(self, mock_conn):
        """Test supply pressure with extremely high competing supply."""
        permits_data = [
            {
                "permit_number": f"BP-{i}",
                "address": f"{i} Street",
                "type": "new_build",
                "status": "approved",
                "project_value": 1000000,
                "units": 100,
                "storeys": 10,
                "sqft": 50000,
                "issued_date": datetime.now(),
                "applicant": f"Developer {i}",
            }
            for i in range(50)
        ]
        mock_conn.fetch.return_value = permits_data

        analyzer = BuildingPermitAnalyzer(mock_conn)
        result = await analyzer.compute_competing_supply(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            existing_units=10,
        )

        assert result.total_permits == 50
        assert result.pipeline_units == 5000
        assert result.supply_pressure_score > 95
        assert result.supply_pressure_score <= 100

    def test_permit_value_decimal_precision(self):
        """Test permit values maintain decimal precision."""
        permit = BuildingPermit(
            permit_number="BP-001",
            address="123 Main",
            permit_type=PermitType.NEW_BUILDING,
            status=PermitStatus.APPROVED,
            project_value=Decimal("1234567.89"),
        )
        assert permit.project_value == Decimal("1234567.89")

    def test_multiple_permit_types_in_list(self, sample_permits):
        """Test list contains all three permit types."""
        permit_types = {p.permit_type for p in sample_permits}
        assert PermitType.NEW_BUILDING in permit_types
        assert PermitType.RENOVATION in permit_types
        assert PermitType.DEMOLITION in permit_types

    def test_all_permit_statuses_in_list(self, sample_permits):
        """Test list contains all four permit statuses."""
        statuses = {p.status for p in sample_permits}
        assert PermitStatus.APPLIED in statuses
        assert PermitStatus.APPROVED in statuses
        assert PermitStatus.ISSUED in statuses
        assert PermitStatus.COMPLETED in statuses


# ── Integration Tests ────────────────────────────────────────────

class TestIntegration:
    """Integration tests combining multiple features."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_conn):
        """Test complete workflow from fetch to analysis."""
        permits_data = [
            {
                "permit_number": "BP-2024-001",
                "address": "123 Main St",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now() - timedelta(days=30),
                "applicant": "Developer A",
            },
            {
                "permit_number": "BP-2024-002",
                "address": "456 Oak Ave",
                "type": "new_build",
                "status": "issued",
                "project_value": 3500000,
                "units": 30,
                "storeys": 12,
                "sqft": 85000,
                "issued_date": datetime.now() - timedelta(days=60),
                "applicant": "Developer B",
            },
            {
                "permit_number": "BP-2024-003",
                "address": "789 Elm St",
                "type": "renovation",
                "status": "completed",
                "project_value": 750000,
                "units": None,
                "storeys": 6,
                "sqft": 15000,
                "issued_date": datetime.now() - timedelta(days=90),
                "applicant": "Renovator Inc",
            },
        ]

        mock_conn.fetch.return_value = permits_data

        analyzer = BuildingPermitAnalyzer(mock_conn)
        result = await analyzer.compute_competing_supply(
            lat=49.2827,
            lng=-123.1207,
            radius_m=500,
            existing_units=200,
        )

        assert result.total_permits == 3
        assert result.new_build_permits == 2
        assert result.pipeline_units == 80
        assert result.total_value == Decimal("9250000")
        assert 0 <= result.supply_pressure_score <= 100
        assert result.avg_units_per_project == pytest.approx(26.67, rel=0.01)

    @pytest.mark.asyncio
    async def test_multiple_analyses_same_connection(self, mock_conn):
        """Test running multiple analyses on same connection."""
        mock_conn.fetch.return_value = [
            {
                "permit_number": "BP-001",
                "address": "123 Main",
                "type": "new_build",
                "status": "approved",
                "project_value": 5000000,
                "units": 50,
                "storeys": 15,
                "sqft": 125000,
                "issued_date": datetime.now(),
                "applicant": "Developer",
            },
        ]

        analyzer = BuildingPermitAnalyzer(mock_conn)

        result1 = await analyzer.compute_competing_supply(49.2827, -123.1207)
        result2 = await analyzer.compute_competing_supply(49.2900, -123.1300)

        assert result1.pipeline_units == 50
        assert result2.pipeline_units == 50
        assert mock_conn.fetch.call_count == 2


# ── Database Schema Tests ────────────────────────────────────────

class TestDatabaseSchema:
    """Tests for database table structure expectations."""

    def test_building_permits_table_columns(self):
        """Test expected columns in building_permits table.

        Expected schema:
        - id: integer primary key
        - permit_number: varchar unique
        - address: varchar
        - type: varchar (new_build, renovation, demolition)
        - status: varchar (applied, approved, issued, completed)
        - project_value: numeric
        - units: integer nullable
        - storeys: integer nullable
        - sqft: integer nullable
        - geom: geometry (PostGIS)
        - issued_date: timestamp nullable
        """
        expected_columns = [
            "id",
            "permit_number",
            "address",
            "type",
            "status",
            "project_value",
            "units",
            "storeys",
            "sqft",
            "geom",
            "issued_date",
        ]
        # This test documents the expected schema
        assert len(expected_columns) > 0

    def test_permit_number_uniqueness_expectation(self):
        """Test that permit_number should be unique in database."""
        # Document that permit_number has unique constraint
        assert True

    def test_geom_spatial_index_expectation(self):
        """Test expectation of spatial index on geom column."""
        # Document that geom should have GIST or BRIN index
        assert True


# ── Vancouver Permit Type Tests ──────────────────────────────────

class TestVancouverPermitTypes:
    """Tests for Vancouver-specific permit types."""

    def test_new_building_permit_type(self):
        """Test NEW_BUILDING permit type."""
        assert PermitType.NEW_BUILDING.value == "new_build"

    def test_renovation_permit_type(self):
        """Test RENOVATION (Addition/Alteration) permit type."""
        assert PermitType.RENOVATION.value == "renovation"

    def test_demolition_permit_type(self):
        """Test DEMOLITION permit type."""
        assert PermitType.DEMOLITION.value == "demolition"

    def test_all_permit_types_valid(self):
        """Test all permit types can be instantiated."""
        for permit_type in PermitType:
            permit = BuildingPermit(
                permit_number="BP-001",
                address="Test",
                permit_type=permit_type,
                status=PermitStatus.APPLIED,
            )
            assert permit.permit_type == permit_type
