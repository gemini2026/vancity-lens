"""
Sprint 7 tests — Political Risk Score Engine

Tests cover:
- Opposition rate calculation (7.1)
- Delay attribution score (7.2)
- Recency-weighted sentiment intensity (7.3)
- Council voting pattern resistance (7.4)
- Composite Political Risk Score (7.5)
- Score materialization (7.6)
- Migration file (7.7)
- AC-OPP-001: Scores for all 22 neighborhoods
- AC-OPP-002: High opposition -> score >= 7
- AC-OPP-003: Low opposition -> score <= 3
"""

import os
from datetime import date, timedelta, timezone, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.intelligence.political_risk import (
    VANCOUVER_NEIGHBORHOODS,
    WEIGHT_OPPOSITION_RATE,
    WEIGHT_DELAY,
    WEIGHT_SENTIMENT,
    WEIGHT_COUNCIL,
    MIN_APPLICATIONS,
    MIN_SIGNALS,
    compute_opposition_rate,
    compute_delay_score,
    compute_sentiment_intensity,
    compute_council_resistance,
    compute_composite_score,
    get_neighborhood_risk,
    get_all_risk_scores,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _make_async_pool_mock():
    """Create a properly configured async pool mock."""
    pool = MagicMock()
    conn = AsyncMock()
    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = acm
    return pool, conn


# ── Neighborhood List Tests ─────────────────────────────────────────


class TestNeighborhoodList:
    """AC-OPP-001: Scores for all 22 neighborhoods."""

    def test_has_22_neighborhoods(self):
        assert len(VANCOUVER_NEIGHBORHOODS) == 22

    def test_includes_key_neighborhoods(self):
        assert "Kitsilano" in VANCOUVER_NEIGHBORHOODS
        assert "Downtown" in VANCOUVER_NEIGHBORHOODS
        assert "Mount Pleasant" in VANCOUVER_NEIGHBORHOODS
        assert "West End" in VANCOUVER_NEIGHBORHOODS
        assert "Shaughnessy" in VANCOUVER_NEIGHBORHOODS


# ── Opposition Rate Tests ───────────────────────────────────────────


class TestOppositionRate:
    """Sprint 7.1: Opposition rate per neighborhood."""

    def test_no_applications(self):
        rate, score = compute_opposition_rate(0, 0)
        assert rate == 0.0
        assert score == 0.0

    def test_below_min_applications(self):
        rate, score = compute_opposition_rate(3, 2)
        assert rate == 0.0
        assert score == 0.0

    def test_no_opposition(self):
        rate, score = compute_opposition_rate(20, 0)
        assert rate == 0.0
        assert score == 0.0

    def test_moderate_opposition(self):
        # 5 of 20 opposed = 25%
        rate, score = compute_opposition_rate(20, 5)
        assert rate == 25.0
        assert 4.0 <= score <= 6.0

    def test_high_opposition(self):
        # 15 of 20 opposed = 75%
        rate, score = compute_opposition_rate(20, 15)
        assert rate == 75.0
        assert score == 10.0  # Clamped at 10 since 75/5 = 15 > 10

    def test_total_opposition(self):
        rate, score = compute_opposition_rate(10, 10)
        assert rate == 100.0
        assert score == 10.0

    def test_boundary_min_applications(self):
        rate, score = compute_opposition_rate(MIN_APPLICATIONS, 2)
        assert rate > 0
        assert score > 0


# ── Delay Score Tests ───────────────────────────────────────────────


class TestDelayScore:
    """Sprint 7.2: Delay attribution calculation."""

    def test_no_delay(self):
        assert compute_delay_score(None) == 0.0

    def test_zero_delay(self):
        assert compute_delay_score(0) == 0.0

    def test_normal_timeline(self):
        # 12 months is baseline — no penalty
        assert compute_delay_score(12.0) == 0.0

    def test_slight_delay(self):
        # 18 months = 6 excess = 6/2.4 = 2.5
        score = compute_delay_score(18.0)
        assert 2.0 <= score <= 3.0

    def test_major_delay(self):
        # 36 months = 24 excess = 24/2.4 = 10
        score = compute_delay_score(36.0)
        assert score == 10.0

    def test_extreme_delay(self):
        # 60 months — should clamp at 10
        score = compute_delay_score(60.0)
        assert score == 10.0

    def test_under_baseline(self):
        # 6 months — faster than baseline
        assert compute_delay_score(6.0) == 0.0


# ── Sentiment Intensity Tests ───────────────────────────────────────


class TestSentimentIntensity:
    """Sprint 7.3: Recency-weighted sentiment intensity."""

    def test_empty_signals(self):
        assert compute_sentiment_intensity([]) == 0.0

    def test_below_min_signals(self):
        signals = [
            {"event_date": date.today().isoformat(), "sentiment": "negative_for_development", "confidence": 0.8},
            {"event_date": date.today().isoformat(), "sentiment": "negative_for_development", "confidence": 0.8},
        ]
        assert compute_sentiment_intensity(signals) == 0.0

    def test_all_negative_recent(self):
        today = date.today()
        signals = [
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": (today - timedelta(days=10)).isoformat(), "sentiment": "negative_for_development", "confidence": 0.8},
            {"event_date": (today - timedelta(days=20)).isoformat(), "sentiment": "negative_for_development", "confidence": 0.7},
            {"event_date": (today - timedelta(days=30)).isoformat(), "sentiment": "negative_for_development", "confidence": 0.85},
        ]
        score = compute_sentiment_intensity(signals)
        assert score > 7.0  # All negative, recent

    def test_all_positive(self):
        today = date.today()
        signals = [
            {"event_date": today.isoformat(), "sentiment": "positive_for_development", "confidence": 0.9},
            {"event_date": (today - timedelta(days=10)).isoformat(), "sentiment": "positive_for_development", "confidence": 0.8},
            {"event_date": (today - timedelta(days=20)).isoformat(), "sentiment": "neutral", "confidence": 0.7},
            {"event_date": (today - timedelta(days=30)).isoformat(), "sentiment": "positive_for_development", "confidence": 0.85},
        ]
        score = compute_sentiment_intensity(signals)
        assert score == 0.0  # No negative signals

    def test_mixed_sentiment(self):
        today = date.today()
        signals = [
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": today.isoformat(), "sentiment": "positive_for_development", "confidence": 0.9},
            {"event_date": today.isoformat(), "sentiment": "neutral", "confidence": 0.8},
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.8},
        ]
        score = compute_sentiment_intensity(signals)
        assert 5.0 <= score <= 10.0  # 50% negative = significant

    def test_old_negative_decays(self):
        today = date.today()
        old_date = (today - timedelta(days=365)).isoformat()
        signals = [
            {"event_date": old_date, "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": old_date, "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": old_date, "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": today.isoformat(), "sentiment": "positive_for_development", "confidence": 0.9},
        ]
        score = compute_sentiment_intensity(signals)
        # Old negatives decay significantly, recent positive dominates
        assert score < 8.0

    def test_low_confidence_excluded(self):
        today = date.today()
        signals = [
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.4},
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.3},
            {"event_date": today.isoformat(), "sentiment": "negative_for_development", "confidence": 0.5},
        ]
        # All below 0.60 threshold
        assert compute_sentiment_intensity(signals) == 0.0

    def test_date_object_input(self):
        today = date.today()
        signals = [
            {"event_date": today, "sentiment": "negative_for_development", "confidence": 0.9},
            {"event_date": today, "sentiment": "negative_for_development", "confidence": 0.8},
            {"event_date": today, "sentiment": "negative_for_development", "confidence": 0.7},
        ]
        score = compute_sentiment_intensity(signals)
        assert score > 0


# ── Council Resistance Tests ────────────────────────────────────────


class TestCouncilResistance:
    """Sprint 7.4: Council voting pattern analysis."""

    def test_no_records(self):
        avg, score = compute_council_resistance([])
        assert avg == 0.0
        assert score == 0.0

    def test_unanimous_approval(self):
        records = [
            {"vote_for": 10, "vote_against": 0},
            {"vote_for": 8, "vote_against": 0},
        ]
        avg, score = compute_council_resistance(records)
        assert avg == 0.0
        assert score == 0.0

    def test_moderate_resistance(self):
        records = [
            {"vote_for": 7, "vote_against": 3},  # 30% against
            {"vote_for": 6, "vote_against": 4},  # 40% against
        ]
        avg, score = compute_council_resistance(records)
        assert 30.0 <= avg <= 40.0
        assert 5.0 <= score <= 8.0

    def test_high_resistance(self):
        records = [
            {"vote_for": 3, "vote_against": 7},  # 70% against
            {"vote_for": 4, "vote_against": 6},  # 60% against
        ]
        avg, score = compute_council_resistance(records)
        assert avg > 60.0
        assert score == 10.0  # 65/5 = 13, clamped to 10

    def test_no_valid_votes(self):
        records = [
            {"vote_for": 0, "vote_against": 0},
            {"vote_for": None, "vote_against": None},
        ]
        avg, score = compute_council_resistance(records)
        assert avg == 0.0
        assert score == 0.0


# ── Composite Score Tests ───────────────────────────────────────────


class TestCompositeScore:
    """Sprint 7.5: Composite Political Risk Score (1-10)."""

    def test_weights_sum_to_one(self):
        total = WEIGHT_OPPOSITION_RATE + WEIGHT_DELAY + WEIGHT_SENTIMENT + WEIGHT_COUNCIL
        assert abs(total - 1.0) < 0.001

    def test_all_zero_components(self):
        score = compute_composite_score(0, 0, 0, 0)
        assert score == 1.0  # Minimum score

    def test_all_max_components(self):
        score = compute_composite_score(10, 10, 10, 10)
        assert score == 10.0  # Maximum score

    def test_low_risk_score(self):
        # AC-OPP-003: Low opposition -> score <= 3
        score = compute_composite_score(1.0, 0.5, 1.0, 0.5)
        assert score <= 3.0

    def test_high_risk_score(self):
        # AC-OPP-002: High opposition -> score >= 7
        score = compute_composite_score(9.0, 8.0, 9.0, 8.0)
        assert score >= 7.0

    def test_moderate_risk(self):
        score = compute_composite_score(5.0, 5.0, 5.0, 5.0)
        assert 4.0 <= score <= 6.0

    def test_always_at_least_one(self):
        score = compute_composite_score(0, 0, 0, 0)
        assert score >= 1.0

    def test_never_exceeds_ten(self):
        score = compute_composite_score(15, 15, 15, 15)
        assert score <= 10.0


# ── DB Query Tests ──────────────────────────────────────────────────


class TestGetNeighborhoodRisk:
    """Test DB query functions for risk scores."""

    @pytest.mark.asyncio
    async def test_get_neighborhood_risk(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {
            "neighborhood": "Kitsilano",
            "risk_score": Decimal("4.5"),
            "opposition_rate": Decimal("15.0"),
            "delay_score": Decimal("2.0"),
            "sentiment_intensity": Decimal("3.5"),
            "council_resistance": Decimal("2.0"),
            "total_applications": 20,
            "opposed_applications": 3,
            "total_signals": 45,
            "negative_signals": 8,
            "avg_delay_months": Decimal("14.5"),
            "avg_vote_against_pct": Decimal("22.0"),
            "period_months": 36,
            "computed_at": datetime.now(timezone.utc),
        }

        result = await get_neighborhood_risk(pool, "Kitsilano")
        assert result is not None
        assert result["neighborhood"] == "Kitsilano"
        assert result["risk_score"] == Decimal("4.5")

    @pytest.mark.asyncio
    async def test_get_neighborhood_risk_not_found(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = None

        result = await get_neighborhood_risk(pool, "Atlantis")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_risk_scores(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {"neighborhood": "Downtown", "risk_score": Decimal("6.5")},
            {"neighborhood": "Kitsilano", "risk_score": Decimal("4.5")},
        ]

        result = await get_all_risk_scores(pool)
        assert len(result) == 2
        assert result[0]["neighborhood"] == "Downtown"

    @pytest.mark.asyncio
    async def test_get_all_risk_scores_failure(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.side_effect = Exception("table not found")

        result = await get_all_risk_scores(pool)
        assert result == []


# ── Migration Tests ─────────────────────────────────────────────────


class TestSprint7Migration:
    """Sprint 7.7: Migration file validation."""

    def test_migration_exists(self):
        assert os.path.exists("db/040_political_risk_sprint7.sql")

    def test_migration_creates_table(self):
        with open("db/040_political_risk_sprint7.sql") as f:
            sql = f.read()
        assert "political_risk_scores" in sql
        assert "risk_score" in sql
        assert "opposition_rate" in sql
        assert "delay_score" in sql
        assert "sentiment_intensity" in sql
        assert "council_resistance" in sql

    def test_migration_has_check_constraint(self):
        with open("db/040_political_risk_sprint7.sql") as f:
            sql = f.read()
        assert "CHECK" in sql
        assert "risk_score >= 1" in sql
        assert "risk_score <= 10" in sql

    def test_migration_has_indexes(self):
        with open("db/040_political_risk_sprint7.sql") as f:
            sql = f.read()
        assert "idx_political_risk_neighborhood" in sql
        assert "idx_political_risk_computed" in sql

    def test_migration_has_view(self):
        with open("db/040_political_risk_sprint7.sql") as f:
            sql = f.read()
        assert "latest_political_risk" in sql
        assert "DISTINCT ON (neighborhood)" in sql

    def test_migration_has_component_columns(self):
        with open("db/040_political_risk_sprint7.sql") as f:
            sql = f.read()
        assert "total_applications" in sql
        assert "opposed_applications" in sql
        assert "total_signals" in sql
        assert "negative_signals" in sql
        assert "avg_delay_months" in sql
        assert "avg_vote_against_pct" in sql
