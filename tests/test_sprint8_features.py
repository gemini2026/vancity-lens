"""
Sprint 8 tests — Opposition Themes & Risk Narrative

Tests cover:
- Opposition theme extraction (8.1, AC-OPP-004)
- Risk narrative generation (8.2, AC-OPP-005)
- Parcel-level risk summary (8.3)
- Political risk routes (8.3)
- Confidence exclusion validation (8.8)
- Frontend component existence
"""

import os
from datetime import date, timedelta, timezone, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.intelligence.political_risk import (
    THEME_KEYWORDS,
    extract_opposition_themes,
    generate_risk_narrative,
    get_opposition_themes,
    get_parcel_political_risk,
)
from api.intelligence.political_risk_routes import router as political_risk_router


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


def _make_negative_signal(summary: str, headline: str = "") -> dict:
    return {
        "summary": summary,
        "headline": headline,
        "sentiment": "negative_for_development",
    }


def _make_positive_signal(summary: str) -> dict:
    return {
        "summary": summary,
        "headline": "",
        "sentiment": "positive_for_development",
    }


# ── Theme Extraction Tests ──────────────────────────────────────────


class TestThemeExtraction:
    """Sprint 8.1: Opposition theme extraction (AC-OPP-004)."""

    def test_theme_keywords_exist(self):
        assert len(THEME_KEYWORDS) >= 8

    def test_empty_signals(self):
        themes = extract_opposition_themes([])
        assert themes == []

    def test_single_theme(self):
        signals = [
            _make_negative_signal("Traffic congestion is major concern for residents"),
            _make_negative_signal("Traffic impact study shows increased congestion"),
            _make_negative_signal("Parking shortage due to new development"),
        ]
        themes = extract_opposition_themes(signals)
        assert len(themes) >= 1
        assert any("Traffic" in t["theme"] for t in themes)

    def test_multiple_themes(self):
        signals = [
            _make_negative_signal("Building is too tall, shadow impacts neighbors"),
            _make_negative_signal("Height exceeds neighborhood character"),
            _make_negative_signal("Traffic congestion will worsen"),
            _make_negative_signal("Sewer infrastructure cannot handle density"),
            _make_negative_signal("Loss of neighborhood character and scale"),
        ]
        themes = extract_opposition_themes(signals, top_n=3)
        assert len(themes) <= 3
        # Should detect height, character, traffic, infrastructure themes
        theme_names = [t["theme"].lower() for t in themes]
        assert any("height" in n or "character" in n for n in theme_names)

    def test_positive_signals_excluded(self):
        signals = [
            _make_positive_signal("Great transit-oriented development opportunity"),
            _make_positive_signal("Much needed housing density for the area"),
        ]
        themes = extract_opposition_themes(signals)
        assert themes == []

    def test_top_n_limit(self):
        signals = [
            _make_negative_signal("Traffic congestion"),
            _make_negative_signal("Traffic parking"),
            _make_negative_signal("Building height shadow"),
            _make_negative_signal("Height too tall"),
            _make_negative_signal("Density overcrowd"),
            _make_negative_signal("Infrastructure sewer"),
            _make_negative_signal("Noise construction"),
        ]
        themes = extract_opposition_themes(signals, top_n=2)
        assert len(themes) <= 2

    def test_theme_has_count_and_example(self):
        signals = [
            _make_negative_signal("Traffic congestion is a major concern"),
            _make_negative_signal("More traffic from this development"),
        ]
        themes = extract_opposition_themes(signals)
        assert len(themes) >= 1
        theme = themes[0]
        assert "theme" in theme
        assert "count" in theme
        assert theme["count"] >= 2
        assert "example" in theme


# ── Risk Narrative Tests ────────────────────────────────────────────


class TestRiskNarrative:
    """Sprint 8.2: Risk narrative generation (AC-OPP-005)."""

    def test_low_risk_narrative(self):
        narrative = generate_risk_narrative(
            neighborhood="Kitsilano",
            risk_score=2.5,
            opposition_rate=10.0,
            themes=[{"theme": "Traffic Congestion", "count": 3, "example": ""}],
            total_signals=20,
            negative_signals=3,
        )
        assert "Kitsilano" in narrative
        assert "2.5" in narrative
        assert "low" in narrative.lower()
        assert len(narrative.split()) <= 150

    def test_moderate_risk_narrative(self):
        narrative = generate_risk_narrative(
            neighborhood="Mount Pleasant",
            risk_score=5.0,
            opposition_rate=30.0,
            themes=[
                {"theme": "Building Height", "count": 5, "example": ""},
                {"theme": "Density", "count": 3, "example": ""},
            ],
            total_signals=40,
            negative_signals=15,
        )
        assert "Mount Pleasant" in narrative
        assert "moderate" in narrative.lower()
        assert len(narrative.split()) <= 150

    def test_high_risk_narrative(self):
        narrative = generate_risk_narrative(
            neighborhood="Shaughnessy",
            risk_score=8.5,
            opposition_rate=65.0,
            themes=[
                {"theme": "Neighborhood Character", "count": 12, "example": ""},
                {"theme": "Building Height", "count": 8, "example": ""},
                {"theme": "Density", "count": 6, "example": ""},
            ],
            total_signals=60,
            negative_signals=40,
        )
        assert "Shaughnessy" in narrative
        assert "high" in narrative.lower()
        assert len(narrative.split()) <= 150

    def test_no_themes_narrative(self):
        narrative = generate_risk_narrative(
            neighborhood="Downtown",
            risk_score=3.0,
            opposition_rate=5.0,
            themes=[],
            total_signals=10,
            negative_signals=2,
        )
        assert "Downtown" in narrative
        assert len(narrative.split()) <= 150

    def test_zero_signals_narrative(self):
        narrative = generate_risk_narrative(
            neighborhood="Oakridge",
            risk_score=1.0,
            opposition_rate=0.0,
            themes=[],
            total_signals=0,
            negative_signals=0,
        )
        assert "Oakridge" in narrative
        assert len(narrative.split()) <= 150

    def test_narrative_under_150_words(self):
        narrative = generate_risk_narrative(
            neighborhood="West End",
            risk_score=7.0,
            opposition_rate=50.0,
            themes=[
                {"theme": "Traffic Congestion", "count": 15, "example": ""},
                {"theme": "Building Height", "count": 10, "example": ""},
                {"theme": "Density", "count": 8, "example": ""},
            ],
            total_signals=100,
            negative_signals=55,
        )
        word_count = len(narrative.split())
        assert word_count <= 150, f"Narrative is {word_count} words, expected <= 150"


# ── Parcel-Level Risk Tests ─────────────────────────────────────────


class TestParcelPoliticalRisk:
    """Sprint 8.3: Parcel-level risk summary."""

    @pytest.mark.asyncio
    async def test_parcel_with_risk(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = [
            # parcels lookup
            {"geo_local_area": "Kitsilano"},
            # latest_political_risk
            {
                "neighborhood": "Kitsilano",
                "risk_score": Decimal("4.5"),
                "opposition_rate": Decimal("15.0"),
                "total_signals": 30,
                "negative_signals": 8,
                "delay_score": Decimal("2.0"),
                "sentiment_intensity": Decimal("3.5"),
                "council_resistance": Decimal("2.0"),
                "total_applications": 20,
                "opposed_applications": 3,
                "avg_delay_months": Decimal("14.5"),
                "avg_vote_against_pct": Decimal("22.0"),
                "period_months": 36,
                "computed_at": datetime.now(timezone.utc),
            },
        ]
        conn.fetch.side_effect = [
            # parcel-specific signals
            [],
            # neighborhood signals for themes
            [
                {"summary": "Traffic concerns raised", "headline": "", "sentiment": "negative_for_development"},
            ],
        ]

        result = await get_parcel_political_risk(pool, "012-345-678")
        assert result is not None
        assert result["pid"] == "012-345-678"
        assert result["neighborhood"] == "Kitsilano"
        assert result["risk_score"] == 4.5
        assert "narrative" in result

    @pytest.mark.asyncio
    async def test_parcel_not_found(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = None

        result = await get_parcel_political_risk(pool, "000-000-000")
        assert result is None

    @pytest.mark.asyncio
    async def test_parcel_no_neighborhood(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.return_value = {"geo_local_area": None}

        result = await get_parcel_political_risk(pool, "012-345-678")
        assert result is None

    @pytest.mark.asyncio
    async def test_parcel_db_error(self):
        pool, conn = _make_async_pool_mock()
        conn.fetchrow.side_effect = Exception("connection lost")

        result = await get_parcel_political_risk(pool, "012-345-678")
        assert result is None


# ── Route Tests ─────────────────────────────────────────────────────


class TestPoliticalRiskRoutes:
    """Sprint 8.3: Political risk API routes."""

    def test_router_prefix(self):
        assert political_risk_router.prefix == "/api/v1/political-risk"

    def test_has_neighborhoods_route(self):
        paths = [r.path for r in political_risk_router.routes]
        assert any("neighborhoods" in p for p in paths)

    def test_has_neighborhood_detail_route(self):
        paths = [r.path for r in political_risk_router.routes]
        assert any("neighborhood" in p for p in paths)

    def test_has_parcel_route(self):
        paths = [r.path for r in political_risk_router.routes]
        assert any("parcels" in p or "pid" in p for p in paths)


# ── Validation Tests ────────────────────────────────────────────────


class TestConfidenceExclusion:
    """Sprint 8.8: Confidence < 0.60 exclusion."""

    @pytest.mark.asyncio
    async def test_themes_use_confidence_filter(self):
        pool, conn = _make_async_pool_mock()
        conn.fetch.return_value = [
            {"summary": "Traffic bad", "headline": "", "sentiment": "negative_for_development"},
        ]

        themes = await get_opposition_themes(pool, "Kitsilano")
        # Verify the query was called with confidence filter
        call_args = conn.fetch.call_args
        query = call_args[0][0]
        assert "confidence >= 0.60" in query


# ── Frontend Component Tests ────────────────────────────────────────


class TestPoliticalRiskFrontend:
    """Sprint 8.6: PoliticalRiskBadge component."""

    def test_component_exists(self):
        assert os.path.exists("frontend/src/components/PoliticalRiskBadge.tsx")

    def test_component_is_client(self):
        with open("frontend/src/components/PoliticalRiskBadge.tsx") as f:
            content = f.read()
        assert '"use client"' in content

    def test_component_has_risk_colors(self):
        with open("frontend/src/components/PoliticalRiskBadge.tsx") as f:
            content = f.read()
        assert "getRiskColor" in content
        assert "bg-green" in content
        assert "bg-red" in content

    def test_component_fetches_api(self):
        with open("frontend/src/components/PoliticalRiskBadge.tsx") as f:
            content = f.read()
        assert "/api/v1/political-risk/parcels/" in content

    def test_component_shows_themes(self):
        with open("frontend/src/components/PoliticalRiskBadge.tsx") as f:
            content = f.read()
        assert "themes" in content.lower()
        assert "narrative" in content.lower()
