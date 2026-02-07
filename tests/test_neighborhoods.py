"""Tests for neighborhood scorecards (Phase 5).

TDD: Tests written before implementation.
Tests cover: scoring engine, metric normalization, composite scores,
API routes, comparison mode, and trend detection.
"""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def vancouver_neighborhoods():
    """All 22 Vancouver local areas."""
    return [
        "Arbutus Ridge", "Downtown", "Dunbar-Southlands", "Fairview",
        "Grandview-Woodland", "Hastings-Sunrise", "Kensington-Cedar Cottage",
        "Kerrisdale", "Killarney", "Kitsilano", "Marpole", "Mount Pleasant",
        "Oakridge", "Renfrew-Collingwood", "Riley Park", "Shaughnessy",
        "South Cambie", "Strathcona", "Sunset", "Victoria-Fraserview",
        "West End", "West Point Grey",
    ]


@pytest.fixture
def sample_raw_metrics():
    """Raw metrics for 3 neighborhoods across multiple categories."""
    return [
        # Safety - crime rates per 1000 residents (lower is better)
        {"neighborhood": "Mount Pleasant", "category": "safety", "metric_name": "crimes_per_1000",
         "value": 45.2, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Kitsilano", "category": "safety", "metric_name": "crimes_per_1000",
         "value": 28.1, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Downtown", "category": "safety", "metric_name": "crimes_per_1000",
         "value": 102.5, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        # Schools - average rating 1-10 (higher is better)
        {"neighborhood": "Mount Pleasant", "category": "schools", "metric_name": "avg_school_rating",
         "value": 7.8, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Kitsilano", "category": "schools", "metric_name": "avg_school_rating",
         "value": 8.5, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Downtown", "category": "schools", "metric_name": "avg_school_rating",
         "value": 6.2, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        # Transit - stops within 400m per km2 (higher is better)
        {"neighborhood": "Mount Pleasant", "category": "transit", "metric_name": "stops_per_km2",
         "value": 12.3, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Kitsilano", "category": "transit", "metric_name": "stops_per_km2",
         "value": 9.1, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Downtown", "category": "transit", "metric_name": "stops_per_km2",
         "value": 25.7, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        # Parks - green space hectares per 1000 residents (higher is better)
        {"neighborhood": "Mount Pleasant", "category": "parks", "metric_name": "green_ha_per_1000",
         "value": 2.1, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Kitsilano", "category": "parks", "metric_name": "green_ha_per_1000",
         "value": 5.8, "period_start": "2025-01-01", "period_end": "2025-12-31"},
        {"neighborhood": "Downtown", "category": "parks", "metric_name": "green_ha_per_1000",
         "value": 1.2, "period_start": "2025-01-01", "period_end": "2025-12-31"},
    ]


@pytest.fixture
def sample_category_scores():
    """Pre-computed category scores for testing composite calculation."""
    return {
        "Mount Pleasant": {
            "safety": 6.2, "schools": 7.8, "transit": 7.5, "parks": 5.1,
            "development": 9.2, "air_quality": 8.0, "affordability": 4.1, "walkability": 8.3,
        },
        "Kitsilano": {
            "safety": 8.1, "schools": 8.5, "transit": 6.8, "parks": 8.5,
            "development": 6.0, "air_quality": 9.0, "affordability": 3.2, "walkability": 8.8,
        },
        "Downtown": {
            "safety": 3.0, "schools": 6.2, "transit": 9.5, "parks": 3.0,
            "development": 8.5, "air_quality": 5.0, "affordability": 2.0, "walkability": 9.5,
        },
    }


@pytest.fixture
def default_weights():
    """Default scoring weights (must sum to 1.0)."""
    return {
        "safety": 0.15,
        "schools": 0.15,
        "transit": 0.15,
        "parks": 0.10,
        "development": 0.15,
        "air_quality": 0.05,
        "affordability": 0.15,
        "walkability": 0.10,
    }


@pytest.fixture
def mock_db_pool():
    """Mock database pool for async operations."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


# ── Model Tests ──────────────────────────────────────────────

class TestNeighborhoodModels:
    """Test Pydantic models for neighborhood scorecards."""

    def test_metric_category_enum_values(self):
        from api.intelligence.models import MetricCategory
        assert MetricCategory.SAFETY == "safety"
        assert MetricCategory.SCHOOLS == "schools"
        assert MetricCategory.TRANSIT == "transit"
        assert MetricCategory.PARKS == "parks"
        assert MetricCategory.DEVELOPMENT == "development"
        assert MetricCategory.AIR_QUALITY == "air_quality"
        assert MetricCategory.AFFORDABILITY == "affordability"
        assert MetricCategory.WALKABILITY == "walkability"
        assert len(MetricCategory) == 8

    def test_trend_direction_enum(self):
        from api.intelligence.models import TrendDirection
        assert TrendDirection.IMPROVING == "improving"
        assert TrendDirection.STABLE == "stable"
        assert TrendDirection.DECLINING == "declining"

    def test_category_score_validation(self):
        from api.intelligence.models import CategoryScore, MetricCategory, TrendDirection
        score = CategoryScore(
            category=MetricCategory.SAFETY,
            score=7.5,
            raw_value=28.1,
            percentile=75.0,
            trend=TrendDirection.IMPROVING,
            trend_change=0.3,
        )
        assert score.score == 7.5
        assert score.category == "safety"
        assert score.trend == "improving"

    def test_category_score_bounds(self):
        from api.intelligence.models import CategoryScore, MetricCategory
        # Score must be 0-10
        with pytest.raises(Exception):
            CategoryScore(category=MetricCategory.SAFETY, score=-1.0)
        with pytest.raises(Exception):
            CategoryScore(category=MetricCategory.SAFETY, score=11.0)

    def test_neighborhood_scorecard_model(self):
        from api.intelligence.models import (
            NeighborhoodScorecard, NeighborhoodBase, CategoryScore, MetricCategory
        )
        scorecard = NeighborhoodScorecard(
            neighborhood=NeighborhoodBase(name="Mount Pleasant", slug="mount-pleasant"),
            overall_score=7.2,
            rank=5,
            category_scores=[
                CategoryScore(category=MetricCategory.SAFETY, score=6.2),
                CategoryScore(category=MetricCategory.SCHOOLS, score=7.8),
            ],
            active_rezonings=7,
            recent_permits=23,
            recent_signals=15,
        )
        assert scorecard.overall_score == 7.2
        assert scorecard.rank == 5
        assert len(scorecard.category_scores) == 2
        assert scorecard.active_rezonings == 7
        assert scorecard.total_neighborhoods == 22

    def test_neighborhood_summary_model(self):
        from api.intelligence.models import NeighborhoodSummary
        summary = NeighborhoodSummary(
            name="Kitsilano",
            slug="kitsilano",
            overall_score=8.1,
            rank=2,
            top_category="parks",
            bottom_category="affordability",
            signal_count=12,
        )
        assert summary.overall_score == 8.1
        assert summary.top_category == "parks"

    def test_neighborhood_comparison_model(self):
        from api.intelligence.models import (
            NeighborhoodComparison, NeighborhoodScorecard,
            NeighborhoodBase, MetricCategory,
        )
        comparison = NeighborhoodComparison(
            neighborhoods=[
                NeighborhoodScorecard(
                    neighborhood=NeighborhoodBase(name="Kitsilano", slug="kitsilano"),
                    overall_score=8.1,
                ),
                NeighborhoodScorecard(
                    neighborhood=NeighborhoodBase(name="Downtown", slug="downtown"),
                    overall_score=5.5,
                ),
            ],
            categories=[MetricCategory.SAFETY, MetricCategory.TRANSIT],
        )
        assert len(comparison.neighborhoods) == 2

    def test_metric_ingestion_model(self):
        from api.intelligence.models import MetricIngestion, MetricCategory
        ingestion = MetricIngestion(
            neighborhood_name="Mount Pleasant",
            category=MetricCategory.SAFETY,
            metric_name="crimes_per_1000",
            metric_value=45.2,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            source_name="VPD GeoDASH",
            source_url="https://geodash.vpd.ca/opendata/",
        )
        assert ingestion.metric_value == 45.2
        assert ingestion.source_name == "VPD GeoDASH"


# ── Scoring Engine Tests ─────────────────────────────────────

class TestScoringEngine:
    """Test the neighborhood scoring engine logic."""

    def test_normalize_higher_is_better(self):
        """For metrics where higher = better (schools, transit, parks),
        normalization should map [min, max] → [0, 10]."""
        from api.intelligence.neighborhoods import normalize_metric
        # School rating 8.5 out of range [6.2, 8.5] should be 10.0
        assert normalize_metric(8.5, min_val=6.2, max_val=8.5, higher_is_better=True) == 10.0
        # School rating 6.2 should be 0.0 (but we floor at 1.0 for UX)
        result = normalize_metric(6.2, min_val=6.2, max_val=8.5, higher_is_better=True)
        assert result <= 1.0
        # Midpoint should be roughly 5.0
        mid = normalize_metric(7.35, min_val=6.2, max_val=8.5, higher_is_better=True)
        assert 4.0 <= mid <= 6.0

    def test_normalize_lower_is_better(self):
        """For metrics where lower = better (crime, affordability/price),
        normalization should invert: low value → high score."""
        from api.intelligence.neighborhoods import normalize_metric
        # Crime rate 28.1 out of [28.1, 102.5] — lowest crime = highest score
        result = normalize_metric(28.1, min_val=28.1, max_val=102.5, higher_is_better=False)
        assert result >= 9.0
        # Crime rate 102.5 — highest crime = lowest score
        result = normalize_metric(102.5, min_val=28.1, max_val=102.5, higher_is_better=False)
        assert result <= 1.0

    def test_normalize_single_value(self):
        """When min == max, should return middle score (5.0)."""
        from api.intelligence.neighborhoods import normalize_metric
        result = normalize_metric(50.0, min_val=50.0, max_val=50.0, higher_is_better=True)
        assert result == 5.0

    def test_compute_composite_score(self, sample_category_scores, default_weights):
        """Composite score should be weighted average of category scores."""
        from api.intelligence.neighborhoods import compute_composite_score
        score = compute_composite_score(
            sample_category_scores["Mount Pleasant"],
            default_weights,
        )
        # Manual: 6.2*0.15 + 7.8*0.15 + 7.5*0.15 + 5.1*0.10 + 9.2*0.15 + 8.0*0.05 + 4.1*0.15 + 8.3*0.10
        # = 0.93 + 1.17 + 1.125 + 0.51 + 1.38 + 0.40 + 0.615 + 0.83 = 6.96
        assert 6.5 <= score <= 7.5
        assert isinstance(score, float)

    def test_composite_score_bounds(self, default_weights):
        """Composite score must be between 0 and 10."""
        from api.intelligence.neighborhoods import compute_composite_score
        # All zeros
        zero_scores = {cat: 0.0 for cat in default_weights}
        assert compute_composite_score(zero_scores, default_weights) == 0.0
        # All tens
        max_scores = {cat: 10.0 for cat in default_weights}
        assert compute_composite_score(max_scores, default_weights) == 10.0

    def test_composite_score_weights_sum_to_one(self, default_weights):
        """Default weights must sum to 1.0."""
        total = sum(default_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_rank_neighborhoods(self, sample_category_scores, default_weights):
        """Ranking should order neighborhoods by composite score descending."""
        from api.intelligence.neighborhoods import rank_neighborhoods
        ranked = rank_neighborhoods(sample_category_scores, default_weights)
        assert len(ranked) == 3
        # Each entry should have name, score, rank
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2
        assert ranked[2]["rank"] == 3
        # Scores should be descending
        assert ranked[0]["score"] >= ranked[1]["score"]
        assert ranked[1]["score"] >= ranked[2]["score"]

    def test_detect_trend_improving(self):
        """Score increase > threshold should be 'improving'."""
        from api.intelligence.neighborhoods import detect_trend
        trend, change = detect_trend(current_score=7.5, previous_score=6.8)
        assert trend == "improving"
        assert change > 0

    def test_detect_trend_declining(self):
        """Score decrease > threshold should be 'declining'."""
        from api.intelligence.neighborhoods import detect_trend
        trend, change = detect_trend(current_score=6.0, previous_score=7.2)
        assert trend == "declining"
        assert change < 0

    def test_detect_trend_stable(self):
        """Small change should be 'stable'."""
        from api.intelligence.neighborhoods import detect_trend
        trend, change = detect_trend(current_score=7.5, previous_score=7.4)
        assert trend == "stable"

    def test_detect_trend_no_previous(self):
        """No previous score should default to 'stable'."""
        from api.intelligence.neighborhoods import detect_trend
        trend, change = detect_trend(current_score=7.5, previous_score=None)
        assert trend == "stable"
        assert change == 0.0

    def test_get_top_and_bottom_categories(self, sample_category_scores):
        """Should identify highest and lowest scoring categories."""
        from api.intelligence.neighborhoods import get_top_and_bottom
        top, bottom = get_top_and_bottom(sample_category_scores["Mount Pleasant"])
        assert top == "development"  # 9.2
        assert bottom == "affordability"  # 4.1

    def test_metric_direction_config(self):
        """Each category should have a defined direction (higher/lower is better)."""
        from api.intelligence.neighborhoods import METRIC_DIRECTIONS
        assert METRIC_DIRECTIONS["safety"] == "lower_is_better"  # crime
        assert METRIC_DIRECTIONS["schools"] == "higher_is_better"
        assert METRIC_DIRECTIONS["transit"] == "higher_is_better"
        assert METRIC_DIRECTIONS["parks"] == "higher_is_better"
        assert METRIC_DIRECTIONS["development"] == "higher_is_better"
        assert METRIC_DIRECTIONS["air_quality"] == "higher_is_better"  # AQI inverted
        assert METRIC_DIRECTIONS["affordability"] == "lower_is_better"  # price
        assert METRIC_DIRECTIONS["walkability"] == "higher_is_better"


# ── Open Data Scraper Tests ──────────────────────────────────

class TestOpenDataScrapers:
    """Test the open data ingestion scrapers."""

    @pytest.mark.asyncio
    async def test_scrape_vpd_crime_returns_metrics(self):
        """VPD crime scraper should return per-neighborhood crime counts."""
        from api.intelligence.scraper_opendata import scrape_vpd_crime
        mock_session = MagicMock()
        # Mock CSV response with crime data
        csv_data = (
            "TYPE,YEAR,MONTH,HUNDRED_BLOCK,NEIGHBOURHOOD,X,Y\n"
            "Break and Enter Residential/Other,2025,6,11XX MAIN ST,Mount Pleasant,493200,5457200\n"
            "Theft from Vehicle,2025,6,22XX W 4TH AVE,Kitsilano,489800,5458100\n"
            "Mischief,2025,6,100 W HASTINGS ST,Downtown,492100,5459000\n"
            "Break and Enter Residential/Other,2025,6,33XX COMMERCIAL DR,Grandview-Woodland,493600,5458300\n"
            "Theft from Vehicle,2025,6,200 MAIN ST,Downtown,492600,5458800\n"
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=csv_data)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=ctx)

        metrics = await scrape_vpd_crime(mock_session)
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        for m in metrics:
            assert "neighborhood" in m
            assert "category" in m
            assert m["category"] == "safety"
            assert "value" in m
            assert isinstance(m["value"], (int, float))

    @pytest.mark.asyncio
    async def test_scrape_cov_parks_returns_metrics(self):
        """CoV parks scraper should return green space per neighborhood."""
        from api.intelligence.scraper_opendata import scrape_cov_parks
        mock_session = MagicMock()
        # Mock GeoJSON response
        parks_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"PARK_NAME": "Jonathan Rogers Park", "NEIGHBOURHOOD_NAME": "Mount Pleasant",
                                   "HECTARE": 1.2},
                    "geometry": {"type": "Point", "coordinates": [-123.103, 49.261]},
                },
                {
                    "type": "Feature",
                    "properties": {"PARK_NAME": "Kitsilano Beach Park", "NEIGHBOURHOOD_NAME": "Kitsilano",
                                   "HECTARE": 8.5},
                    "geometry": {"type": "Point", "coordinates": [-123.154, 49.273]},
                },
            ],
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=parks_geojson)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=ctx)

        metrics = await scrape_cov_parks(mock_session)
        assert isinstance(metrics, list)
        for m in metrics:
            assert m["category"] == "parks"

    @pytest.mark.asyncio
    async def test_scrape_translink_gtfs_returns_metrics(self):
        """TransLink GTFS scraper should return transit density metrics."""
        from api.intelligence.scraper_opendata import scrape_translink_transit
        mock_session = MagicMock()
        # Mock stops.txt GTFS data
        stops_data = (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "10001,COMMERCIAL-BROADWAY STN,49.2626,-123.0694\n"
            "10002,MAIN ST-SCIENCE WORLD STN,49.2733,-123.1006\n"
            "10003,BROADWAY-CITY HALL STN,49.2632,-123.1149\n"
            "10004,KING EDWARD STN,49.2490,-123.1160\n"
            "10005,KITSILANO BEACH,49.2731,-123.1540\n"
        )
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=stops_data)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=ctx)

        metrics = await scrape_translink_transit(mock_session)
        assert isinstance(metrics, list)
        for m in metrics:
            assert m["category"] == "transit"

    @pytest.mark.asyncio
    async def test_scraper_handles_http_error(self):
        """Scrapers should handle HTTP errors gracefully."""
        from api.intelligence.scraper_opendata import scrape_vpd_crime
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.text = AsyncMock(return_value="Service Unavailable")
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=ctx)

        metrics = await scrape_vpd_crime(mock_session)
        assert metrics == []  # Should return empty on error, not crash

    @pytest.mark.asyncio
    async def test_scrape_development_from_signals(self):
        """Development score should be derived from intelligence signals count."""
        from api.intelligence.scraper_opendata import compute_development_metrics
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"neighborhood": "Mount Pleasant", "signal_count": 42, "rezoning_count": 7,
             "permit_count": 23},
            {"neighborhood": "Downtown", "signal_count": 35, "rezoning_count": 5,
             "permit_count": 18},
        ])
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=ctx)

        metrics = await compute_development_metrics(mock_pool)
        assert isinstance(metrics, list)
        assert len(metrics) >= 2
        for m in metrics:
            assert m["category"] == "development"


# ── API Route Tests ──────────────────────────────────────────

class TestNeighborhoodRoutes:
    """Test the neighborhood scorecard API endpoints."""

    @pytest.fixture
    def api_client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_get_neighborhoods_list(self, api_client):
        """GET /api/v1/intel/neighborhoods/scorecards should return all neighborhoods."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool, \
             patch("api.intelligence.neighborhoods.get_all_neighborhood_summaries") as mock_fn:
            mock_pool.return_value = MagicMock()
            mock_fn.return_value = [
                {"name": "Kitsilano", "slug": "kitsilano", "overall_score": 8.1, "rank": 1},
                {"name": "Mount Pleasant", "slug": "mount-pleasant", "overall_score": 7.2, "rank": 2},
            ]
            response = api_client.get("/api/v1/intel/neighborhoods/scorecards")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_get_neighborhood_scorecard(self, api_client):
        """GET /api/v1/intel/neighborhoods/{slug}/scorecard should return full scorecard."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool, \
             patch("api.intelligence.neighborhoods.get_neighborhood_scorecard") as mock_fn:
            mock_pool.return_value = MagicMock()
            mock_fn.return_value = {
                "neighborhood": {"name": "Mount Pleasant", "slug": "mount-pleasant"},
                "overall_score": 7.2,
                "rank": 5,
                "category_scores": [
                    {"category": "safety", "score": 6.2, "trend": "stable"},
                    {"category": "schools", "score": 7.8, "trend": "improving"},
                ],
                "active_rezonings": 7,
                "recent_permits": 23,
            }
            response = api_client.get("/api/v1/intel/neighborhoods/mount-pleasant/scorecard")
            assert response.status_code == 200
            data = response.json()
            assert data["overall_score"] == 7.2
            assert len(data["category_scores"]) == 2

    def test_get_neighborhood_scorecard_not_found(self, api_client):
        """GET /api/v1/intel/neighborhoods/{slug}/scorecard for invalid slug returns 404."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool, \
             patch("api.intelligence.neighborhoods.get_neighborhood_scorecard") as mock_fn:
            mock_pool.return_value = MagicMock()
            mock_fn.return_value = None
            response = api_client.get("/api/v1/intel/neighborhoods/fake-hood/scorecard")
            assert response.status_code == 404

    def test_compare_neighborhoods(self, api_client):
        """GET /api/v1/intel/neighborhoods/compare?slugs=X,Y should return comparison."""
        with patch("api.intelligence.routes.get_db_pool") as mock_pool, \
             patch("api.intelligence.neighborhoods.compare_neighborhoods") as mock_fn:
            mock_pool.return_value = MagicMock()
            mock_fn.return_value = {
                "neighborhoods": [
                    {"neighborhood": {"name": "Kitsilano"}, "overall_score": 8.1},
                    {"neighborhood": {"name": "Downtown"}, "overall_score": 5.5},
                ],
                "categories": ["safety", "transit", "parks"],
            }
            response = api_client.get(
                "/api/v1/intel/neighborhoods/compare?slugs=kitsilano,downtown"
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["neighborhoods"]) == 2

    def test_compare_too_many_neighborhoods(self, api_client):
        """Comparing more than 4 neighborhoods should return 400."""
        response = api_client.get(
            "/api/v1/intel/neighborhoods/compare?slugs=a,b,c,d,e"
        )
        assert response.status_code == 400


# ── Integration / Aggregation Tests ──────────────────────────

class TestScoringIntegration:
    """Integration tests for the full scoring pipeline."""

    def test_full_scoring_pipeline(self, sample_raw_metrics, default_weights):
        """Full pipeline: raw metrics → normalize → composite → rank."""
        from api.intelligence.neighborhoods import (
            normalize_metric, compute_composite_score, rank_neighborhoods,
            METRIC_DIRECTIONS,
        )

        # Step 1: Normalize raw metrics per neighborhood
        neighborhoods = {}
        for metric in sample_raw_metrics:
            hood = metric["neighborhood"]
            cat = metric["category"]
            if hood not in neighborhoods:
                neighborhoods[hood] = {}
            neighborhoods[hood][cat] = metric["value"]

        # Get min/max per category for normalization
        category_ranges = {}
        for metric in sample_raw_metrics:
            cat = metric["category"]
            if cat not in category_ranges:
                category_ranges[cat] = {"min": float("inf"), "max": float("-inf")}
            category_ranges[cat]["min"] = min(category_ranges[cat]["min"], metric["value"])
            category_ranges[cat]["max"] = max(category_ranges[cat]["max"], metric["value"])

        # Normalize
        scored = {}
        for hood, cats in neighborhoods.items():
            scored[hood] = {}
            for cat, val in cats.items():
                direction = METRIC_DIRECTIONS.get(cat, "higher_is_better")
                higher_is_better = direction == "higher_is_better"
                scored[hood][cat] = normalize_metric(
                    val,
                    category_ranges[cat]["min"],
                    category_ranges[cat]["max"],
                    higher_is_better,
                )

        # Verify normalization
        for hood in scored:
            for cat, score in scored[hood].items():
                assert 0.0 <= score <= 10.0, f"{hood}/{cat} score {score} out of range"

        # Step 2: Compute composite (only for available categories)
        # Fill missing categories with 5.0 (neutral)
        all_cats = set(default_weights.keys())
        for hood in scored:
            for cat in all_cats:
                if cat not in scored[hood]:
                    scored[hood][cat] = 5.0

        ranked = rank_neighborhoods(scored, default_weights)
        assert len(ranked) == 3
        assert ranked[0]["rank"] == 1

    def test_scoring_deterministic(self, sample_category_scores, default_weights):
        """Same inputs should produce same outputs."""
        from api.intelligence.neighborhoods import compute_composite_score
        score1 = compute_composite_score(sample_category_scores["Mount Pleasant"], default_weights)
        score2 = compute_composite_score(sample_category_scores["Mount Pleasant"], default_weights)
        assert score1 == score2
