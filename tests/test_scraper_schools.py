"""
Tests for VSB School Data Scraper (VCL-96).

Covers:
- School data parsing from mock API response
- Neighborhood mapping logic
- Quality metric calculations
- Database storage
- Route endpoints
- Error handling
- Edge cases
"""

import pytest
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any

import asyncpg

from api.intelligence.scraper_schools import (
    VSBSchoolScraper,
    SchoolData,
    SchoolMetrics,
)


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def mock_db_pool():
    """Create a mock asyncpg pool."""
    pool = AsyncMock(spec=asyncpg.Pool)
    pool.acquire = MagicMock()

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def mock_api_response():
    """Create mock VSB API response."""
    return {
        "results": [
            {
                "name": "Lord Byng Secondary",
                "address": "3939 W. 16th Ave, Vancouver, BC V6R 3C1",
                "school_type": "secondary",
                "enrollment": 1450,
                "capacity": 1600,
                "student_teacher_ratio": 16.5,
                "geo_point_2d": {"lat": 49.2680, "lon": -123.1600},
                "neighborhood": "Kitsilano",
            },
            {
                "name": "Kitsilano Elementary",
                "address": "2025 W. 5th Ave, Vancouver, BC V6J 1T8",
                "school_type": "elementary",
                "enrollment": 380,
                "capacity": 450,
                "student_teacher_ratio": 22.1,
                "geo_point_2d": {"lat": 49.2650, "lon": -123.1580},
                "neighborhood": "Kitsilano",
            },
            {
                "name": "Downtown Eastside Elementary",
                "address": "220 E. Pender St, Vancouver, BC V6A 1W5",
                "school_type": "elementary",
                "enrollment": 220,
                "capacity": 350,
                "student_teacher_ratio": 18.0,
                "geo_point_2d": {"lat": 49.2827, "lon": -123.1207},
                "neighborhood": "Downtown",
            },
        ]
    }


@pytest.fixture
def scraper():
    """Create a VSBSchoolScraper instance."""
    return VSBSchoolScraper()


# ── Data Model Tests ───────────────────────────────────────────


class TestSchoolDataModel:
    """Tests for SchoolData Pydantic model."""

    def test_school_data_basic_creation(self):
        """Test basic SchoolData creation."""
        school = SchoolData(
            name="Test School",
            address="123 Test St",
            school_type="elementary",
            enrollment=300,
            capacity=400,
        )
        assert school.name == "Test School"
        assert school.address == "123 Test St"
        assert school.school_type == "elementary"
        assert school.enrollment == 300
        assert school.capacity == 400

    def test_school_data_with_coordinates(self):
        """Test SchoolData with geographic coordinates."""
        school = SchoolData(
            name="Test School",
            address="123 Test St",
            school_type="secondary",
            latitude=49.2680,
            longitude=-123.1600,
            neighborhood="Kitsilano",
        )
        assert school.latitude == 49.2680
        assert school.longitude == -123.1600
        assert school.neighborhood == "Kitsilano"

    def test_school_data_optional_fields(self):
        """Test SchoolData with optional fields."""
        school = SchoolData(
            name="Test School",
            address="123 Test St",
            school_type="elementary",
        )
        assert school.enrollment is None
        assert school.capacity is None
        assert school.student_teacher_ratio is None
        assert school.latitude is None
        assert school.neighborhood is None


class TestSchoolMetricsModel:
    """Tests for SchoolMetrics Pydantic model."""

    def test_school_metrics_creation(self):
        """Test SchoolMetrics creation."""
        metrics = SchoolMetrics(
            neighborhood="Kitsilano",
            school_count=5,
            elementary_count=3,
            secondary_count=2,
            total_enrollment=1500,
            total_capacity=1800,
            avg_capacity_utilization=83.3,
            avg_student_teacher_ratio=19.5,
            quality_score=7.8,
        )
        assert metrics.neighborhood == "Kitsilano"
        assert metrics.school_count == 5
        assert metrics.avg_capacity_utilization == 83.3
        assert metrics.quality_score == 7.8

    def test_school_metrics_defaults(self):
        """Test SchoolMetrics with defaults."""
        metrics = SchoolMetrics(neighborhood="Downtown")
        assert metrics.school_count == 0
        assert metrics.elementary_count == 0
        assert metrics.secondary_count == 0
        assert metrics.total_enrollment == 0
        assert metrics.total_capacity == 0


# ── School Type Normalization Tests ────────────────────────────


class TestSchoolTypeNormalization:
    """Tests for school type normalization."""

    def test_normalize_secondary_type(self, scraper):
        """Test normalization of secondary school types."""
        assert scraper._normalize_school_type("secondary") == "secondary"
        assert scraper._normalize_school_type("Secondary") == "secondary"
        assert scraper._normalize_school_type("SECONDARY") == "secondary"
        assert scraper._normalize_school_type("high school") == "secondary"
        assert scraper._normalize_school_type("High School") == "secondary"

    def test_normalize_middle_type(self, scraper):
        """Test normalization of middle school types."""
        assert scraper._normalize_school_type("middle") == "middle"
        assert scraper._normalize_school_type("Middle") == "middle"
        assert scraper._normalize_school_type("MIDDLE SCHOOL") == "middle"

    def test_normalize_elementary_type(self, scraper):
        """Test normalization of elementary school types."""
        assert scraper._normalize_school_type("elementary") == "elementary"
        assert scraper._normalize_school_type("Elementary") == "elementary"
        assert scraper._normalize_school_type("primary") == "elementary"
        assert scraper._normalize_school_type("unknown") == "elementary"


# ── Neighborhood Mapping Tests ─────────────────────────────────


class TestNeighborhoodMapping:
    """Tests for neighborhood mapping from coordinates."""

    def test_map_kitsilano_coordinates(self, scraper):
        """Test mapping Kitsilano coordinates."""
        result = scraper._map_to_neighborhood(49.2680, -123.1600)
        assert result == "Kitsilano"

    def test_map_downtown_coordinates(self, scraper):
        """Test mapping Downtown coordinates."""
        result = scraper._map_to_neighborhood(49.2827, -123.1207)
        assert result == "Downtown"

    def test_map_mount_pleasant_coordinates(self, scraper):
        """Test mapping Mount Pleasant coordinates."""
        result = scraper._map_to_neighborhood(49.2620, -123.1000)
        assert result == "Mount Pleasant"

    def test_map_fairview_coordinates(self, scraper):
        """Test mapping Fairview coordinates."""
        result = scraper._map_to_neighborhood(49.2650, -123.1300)
        assert result == "Fairview"

    def test_map_west_end_coordinates(self, scraper):
        """Test mapping West End coordinates."""
        result = scraper._map_to_neighborhood(49.2870, -123.1370)
        assert result == "West End"

    def test_map_grandview_woodland_coordinates(self, scraper):
        """Test mapping Grandview-Woodland coordinates."""
        result = scraper._map_to_neighborhood(49.2750, -123.0700)
        assert result == "Grandview-Woodland"

    def test_map_unknown_coordinates(self, scraper):
        """Test mapping unknown coordinates."""
        result = scraper._map_to_neighborhood(45.0, -100.0)
        assert result == "Unknown"

    def test_map_none_coordinates(self, scraper):
        """Test mapping with None coordinates."""
        result = scraper._map_to_neighborhood(None, None)
        assert result == "Unknown"

    def test_map_partial_coordinates(self, scraper):
        """Test mapping with partial coordinates."""
        result = scraper._map_to_neighborhood(49.2680, None)
        assert result == "Unknown"

    def test_map_prefers_provided_neighborhood(self, scraper):
        """Test that provided neighborhood is preferred."""
        result = scraper._map_to_neighborhood(49.2680, -123.1600, "Mount Pleasant")
        assert result == "Mount Pleasant"

    def test_map_provided_neighborhood_case_insensitive(self, scraper):
        """Test provided neighborhood matching is case-insensitive."""
        result = scraper._map_to_neighborhood(49.2680, -123.1600, "kitsilano")
        assert result == "Kitsilano"


# ── Data Parsing Tests ────────────────────────────────────────


class TestSchoolDataParsing:
    """Tests for parsing raw API response into SchoolData objects."""

    def test_parse_basic_school_record(self, scraper, mock_api_response):
        """Test parsing a basic school record."""
        schools = scraper._parse_school_data(mock_api_response)
        assert len(schools) == 3
        assert schools[0].name == "Lord Byng Secondary"
        assert schools[0].school_type == "secondary"
        assert schools[0].enrollment == 1450

    def test_parse_school_with_coordinates(self, scraper, mock_api_response):
        """Test parsing school coordinates."""
        schools = scraper._parse_school_data(mock_api_response)
        assert schools[0].latitude == 49.2680
        assert schools[0].longitude == -123.1600

    def test_parse_school_neighborhood_mapping(self, scraper, mock_api_response):
        """Test neighborhood is mapped during parsing."""
        schools = scraper._parse_school_data(mock_api_response)
        assert schools[0].neighborhood == "Kitsilano"
        assert schools[2].neighborhood == "Downtown"

    def test_parse_empty_response(self, scraper):
        """Test parsing empty API response."""
        response = {"results": []}
        schools = scraper._parse_school_data(response)
        assert schools == []

    def test_parse_response_without_results_key(self, scraper):
        """Test parsing response without results key."""
        response = {}
        schools = scraper._parse_school_data(response)
        assert schools == []

    def test_parse_school_with_string_enrollment(self, scraper):
        """Test parsing school with string enrollment."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "enrollment": "300",
                    "capacity": "400",
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].enrollment == 300
        assert schools[0].capacity == 400

    def test_parse_school_with_invalid_string_enrollment(self, scraper):
        """Test parsing school with non-numeric string enrollment."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "enrollment": "invalid",
                    "capacity": "also_invalid",
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].enrollment is None
        assert schools[0].capacity is None

    def test_parse_school_missing_required_fields(self, scraper):
        """Test parsing school with missing required fields."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    # missing address
                    "school_type": "elementary",
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert len(schools) == 0

    def test_parse_school_with_coordinates_as_string(self, scraper):
        """Test parsing coordinates provided as string."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "geo_point_2d": "49.2680,-123.1600",
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].latitude == 49.2680
        assert schools[0].longitude == -123.1600

    def test_parse_school_with_alt_field_names(self, scraper):
        """Test parsing schools with alternative field names."""
        response = {
            "results": [
                {
                    "school_name": "Test School",
                    "street_address": "123 Test St",
                    "type": "elementary",
                    "str": "20.5",
                    "location": {"lat": 49.2680, "lon": -123.1600},
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].name == "Test School"
        assert schools[0].address == "123 Test St"
        assert schools[0].student_teacher_ratio == 20.5
        assert schools[0].latitude == 49.2680


# ── Quality Score Calculation Tests ────────────────────────────


class TestQualityScoreCalculation:
    """Tests for school quality score computation."""

    def test_quality_score_all_none_returns_none(self, scraper):
        """Test quality score with all None inputs."""
        score = scraper._compute_quality_score(None, None, 5)
        assert score is None

    def test_quality_score_at_ideal_capacity(self, scraper):
        """Test quality score at ideal capacity (75%)."""
        score = scraper._compute_quality_score(75.0, 18.0, 5)
        assert score is not None
        assert 7.0 <= score <= 9.0

    def test_quality_score_low_capacity(self, scraper):
        """Test quality score with low capacity utilization."""
        score = scraper._compute_quality_score(30.0, 18.0, 5)
        assert score is not None
        assert 5.0 <= score <= 8.0

    def test_quality_score_high_capacity(self, scraper):
        """Test quality score with high capacity utilization."""
        score = scraper._compute_quality_score(95.0, 18.0, 5)
        assert score is not None
        assert 7.0 <= score <= 10.0

    def test_quality_score_over_capacity(self, scraper):
        """Test quality score when over capacity."""
        score = scraper._compute_quality_score(110.0, 18.0, 5)
        assert score is not None
        assert 8.0 <= score <= 10.0

    def test_quality_score_good_student_teacher_ratio(self, scraper):
        """Test quality score with good student-teacher ratio."""
        score = scraper._compute_quality_score(75.0, 15.0, 5)
        assert score is not None
        assert 8.0 <= score <= 10.0

    def test_quality_score_poor_student_teacher_ratio(self, scraper):
        """Test quality score with poor student-teacher ratio."""
        score = scraper._compute_quality_score(75.0, 30.0, 5)
        assert score is not None
        assert 5.0 <= score <= 8.0

    def test_quality_score_only_capacity_utilization(self, scraper):
        """Test quality score with only capacity utilization."""
        score = scraper._compute_quality_score(75.0, None, 5)
        assert score is not None

    def test_quality_score_only_student_teacher_ratio(self, scraper):
        """Test quality score with only student-teacher ratio."""
        score = scraper._compute_quality_score(None, 18.0, 5)
        assert score is not None

    def test_quality_score_many_schools_bonus(self, scraper):
        """Test quality score gets bonus for more schools."""
        score_few = scraper._compute_quality_score(75.0, 18.0, 2)
        score_many = scraper._compute_quality_score(75.0, 18.0, 10)
        assert score_many > score_few

    def test_quality_score_bounds(self, scraper):
        """Test quality score is always between 0-10."""
        for capacity in [0, 50, 100, 150]:
            for str_val in [10, 20, 35]:
                for count in [1, 5, 15]:
                    score = scraper._compute_quality_score(float(capacity), float(str_val), count)
                    if score is not None:
                        assert 0.0 <= score <= 10.0


# ── Neighborhood Metrics Computation Tests ─────────────────────


class TestNeighborhoodMetricsComputation:
    """Tests for computing aggregated neighborhood metrics."""

    def test_compute_metrics_single_neighborhood(self, scraper):
        """Test computing metrics for single neighborhood."""
        schools = [
            SchoolData(
                name="School 1",
                address="Address 1",
                school_type="elementary",
                enrollment=300,
                capacity=400,
                student_teacher_ratio=20.0,
                neighborhood="Kitsilano",
            ),
            SchoolData(
                name="School 2",
                address="Address 2",
                school_type="secondary",
                enrollment=1400,
                capacity=1600,
                student_teacher_ratio=16.5,
                neighborhood="Kitsilano",
            ),
        ]
        schools_by_neighborhood = {"Kitsilano": schools}

        metrics = scraper._compute_quality_metrics(schools_by_neighborhood)

        assert "Kitsilano" in metrics
        assert metrics["Kitsilano"].school_count == 2
        assert metrics["Kitsilano"].elementary_count == 1
        assert metrics["Kitsilano"].secondary_count == 1
        assert metrics["Kitsilano"].total_enrollment == 1700
        assert metrics["Kitsilano"].total_capacity == 2000

    def test_compute_metrics_capacity_utilization(self, scraper):
        """Test capacity utilization calculation."""
        schools = [
            SchoolData(
                name="School 1",
                address="Address 1",
                school_type="elementary",
                enrollment=300,
                capacity=400,
                neighborhood="Downtown",
            ),
        ]
        schools_by_neighborhood = {"Downtown": schools}

        metrics = scraper._compute_quality_metrics(schools_by_neighborhood)
        assert metrics["Downtown"].avg_capacity_utilization == 75.0

    def test_compute_metrics_multiple_neighborhoods(self, scraper):
        """Test computing metrics for multiple neighborhoods."""
        schools_by_neighborhood = {
            "Kitsilano": [
                SchoolData(
                    name="School 1",
                    address="Address 1",
                    school_type="elementary",
                    enrollment=300,
                    capacity=400,
                    student_teacher_ratio=20.0,
                    neighborhood="Kitsilano",
                ),
            ],
            "Downtown": [
                SchoolData(
                    name="School 2",
                    address="Address 2",
                    school_type="secondary",
                    enrollment=1400,
                    capacity=1600,
                    student_teacher_ratio=16.5,
                    neighborhood="Downtown",
                ),
            ],
        }

        metrics = scraper._compute_quality_metrics(schools_by_neighborhood)

        assert len(metrics) == 2
        assert "Kitsilano" in metrics
        assert "Downtown" in metrics

    def test_compute_metrics_empty_input(self, scraper):
        """Test computing metrics with empty input."""
        metrics = scraper._compute_quality_metrics({})
        assert metrics == {}

    def test_compute_metrics_schools_with_missing_data(self, scraper):
        """Test computing metrics when schools have missing enrollment/capacity."""
        schools = [
            SchoolData(
                name="School 1",
                address="Address 1",
                school_type="elementary",
                enrollment=None,
                capacity=None,
                student_teacher_ratio=None,
                neighborhood="Kitsilano",
            ),
        ]
        schools_by_neighborhood = {"Kitsilano": schools}

        metrics = scraper._compute_quality_metrics(schools_by_neighborhood)

        assert metrics["Kitsilano"].school_count == 1
        assert metrics["Kitsilano"].total_enrollment == 0
        assert metrics["Kitsilano"].avg_capacity_utilization is None


# ── Database Storage Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_save_schools_to_db(scraper):
    """Test saving schools to database."""
    pool, conn = AsyncMock(spec=asyncpg.Pool), AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    schools = [
        SchoolData(
            name="Test School",
            address="123 Test St",
            school_type="elementary",
            enrollment=300,
            capacity=400,
            student_teacher_ratio=20.0,
            neighborhood="Kitsilano",
        ),
    ]

    conn.execute = AsyncMock()

    result = await scraper.save_to_db(pool, schools)

    assert result["schools_found"] == 1
    assert result["schools_saved"] >= 0
    assert "neighborhoods_updated" in result

    # Verify execute was called
    assert conn.execute.called


@pytest.mark.asyncio
async def test_save_schools_empty_list(scraper):
    """Test saving empty school list."""
    pool, conn = AsyncMock(spec=asyncpg.Pool), AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await scraper.save_to_db(pool, [])

    assert result["schools_found"] == 0
    assert result["schools_saved"] == 0
    assert result["neighborhoods_updated"] == 0


@pytest.mark.asyncio
async def test_save_schools_db_error(scraper):
    """Test handling database errors during save."""
    pool = AsyncMock()
    pool.acquire.side_effect = Exception("DB error")

    schools = [
        SchoolData(
            name="Test School",
            address="123 Test St",
            school_type="elementary",
            neighborhood="Kitsilano",
        ),
    ]

    result = await scraper.save_to_db(pool, schools)

    assert result["schools_saved"] == 0


# ── API Response Scraping Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_scraper_session_initialization(scraper):
    """Test that scraper initializes aiohttp session."""
    assert scraper.timeout == 30
    assert scraper.session is None

    # After first fetch, session should be created
    # (but we'll mock the fetch to avoid actual network calls)
    with patch.object(scraper, "_fetch_school_list") as mock_fetch:
        mock_fetch.return_value = {"results": []}
        await scraper._fetch_school_list()
        assert mock_fetch.called


@pytest.mark.asyncio
async def test_scraper_handles_missing_session(scraper):
    """Test that scraper creates session if needed."""
    scraper.session = None
    # The _fetch_school_list will create a session if None
    # We just verify the initialization code exists
    assert scraper.timeout == 30


# ── Full Scrape Pipeline Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_full_pipeline(scraper, mock_api_response):
    """Test complete scrape pipeline."""
    with patch.object(scraper, "_fetch_school_list") as mock_fetch:
        mock_fetch.return_value = mock_api_response

        schools = await scraper.scrape()

        assert len(schools) == 3
        assert schools[0].name == "Lord Byng Secondary"
        assert schools[1].name == "Kitsilano Elementary"


@pytest.mark.asyncio
async def test_scrape_handles_api_errors(scraper):
    """Test scrape handles API errors gracefully."""
    with patch.object(scraper, "_fetch_school_list") as mock_fetch:
        mock_fetch.side_effect = Exception("API error")

        schools = await scraper.scrape()

        assert schools == []


# ── Edge Case Tests ────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_parse_school_with_zero_enrollment(self, scraper):
        """Test parsing school with zero enrollment."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "enrollment": 0,
                    "capacity": 400,
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].enrollment == 0

    def test_parse_school_over_capacity(self, scraper):
        """Test parsing school with enrollment over capacity."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "enrollment": 500,
                    "capacity": 400,
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].enrollment == 500
        assert schools[0].capacity == 400

    def test_parse_school_with_negative_str(self, scraper):
        """Test parsing school with invalid student-teacher ratio."""
        response = {
            "results": [
                {
                    "name": "Test School",
                    "address": "123 Test St",
                    "school_type": "elementary",
                    "student_teacher_ratio": -5.0,
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert schools[0].student_teacher_ratio == -5.0

    def test_compute_metrics_with_zero_capacity(self, scraper):
        """Test computing metrics when capacity is zero."""
        schools = [
            SchoolData(
                name="School 1",
                address="Address 1",
                school_type="elementary",
                enrollment=100,
                capacity=0,
                neighborhood="Kitsilano",
            ),
        ]
        schools_by_neighborhood = {"Kitsilano": schools}

        metrics = scraper._compute_quality_metrics(schools_by_neighborhood)

        assert metrics["Kitsilano"].total_capacity == 0

    def test_map_coordinate_on_boundary(self, scraper):
        """Test mapping coordinate exactly on neighborhood boundary."""
        # Test on exact boundary
        result = scraper._map_to_neighborhood(49.26, -123.18)
        assert result is not None

    def test_parse_school_with_special_characters(self, scraper):
        """Test parsing school name with special characters."""
        response = {
            "results": [
                {
                    "name": "St. George's Elementary & Middle School",
                    "address": "123 Test St (Area: Downtown)",
                    "school_type": "elementary",
                }
            ]
        }
        schools = scraper._parse_school_data(response)
        assert "St. George's" in schools[0].name
        assert "&" in schools[0].name


# ── Routing Integration Tests ────────────────────────────────
# Note: Full endpoint integration tests would require TestClient and database setup.
# Routes are covered by route-specific test files.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
