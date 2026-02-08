"""
Tests for VCL-42 [INTEL-007] Weekly digest generator.

Test coverage:
- Subscription CRUD operations
- Digest generation with various filters
- Signal summarization and grouping
- Highlight generation
- Statistics computation
- Neighborhood update formatting
- Scheduler cycle
- Edge cases (no signals, empty period, invalid filters)
"""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest

from api.intelligence.digest import (
    DigestGenerator,
    DigestScheduler,
    DigestSubscription,
    DigestContent,
    DigestDelivery,
    DigestFrequency,
    DigestHighlight,
    DigestStats,
    NeighborhoodUpdate,
    DeliveryStatus,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def sample_signals():
    """Sample intelligence signals for testing."""
    return [
        {
            "id": 1,
            "document_id": 1,
            "signal_type": "rezoning_decision",
            "summary": "Rezoning approved for 1234 Main St from RS-1 to CD-1",
            "headline": "Main St rezoned to mixed-use",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": date.today() - timedelta(days=2),
            "source_title": "City Council Minutes",
            "source_url": "https://council.vancouver.ca/minutes",
            "source_type": "council_minutes",
            "source_date": date.today() - timedelta(days=2),
        },
        {
            "id": 2,
            "document_id": 2,
            "signal_type": "permit_approval",
            "summary": "Building permit approved for residential project",
            "headline": "Residential permit approved",
            "addresses": ["456 Granville Ave"],
            "neighborhood": "Mount Pleasant",
            "decision": "approved",
            "vote_for": None,
            "vote_against": None,
            "sentiment": "positive_for_development",
            "severity": "medium",
            "confidence": 0.85,
            "event_date": date.today() - timedelta(days=1),
            "source_title": "Permits Database",
            "source_url": "https://permits.vancouver.ca",
            "source_type": "permit_approval",
            "source_date": date.today() - timedelta(days=1),
        },
        {
            "id": 3,
            "document_id": 3,
            "signal_type": "policy_change",
            "summary": "New zoning policy implemented for downtown",
            "headline": "Downtown zoning policy update",
            "addresses": [],
            "neighborhood": "Downtown",
            "decision": "approved",
            "vote_for": 11,
            "vote_against": 0,
            "sentiment": "neutral",
            "severity": "high",
            "confidence": 0.90,
            "event_date": date.today() - timedelta(days=3),
            "source_title": "City Policy Update",
            "source_url": "https://policy.vancouver.ca",
            "source_type": "staff_report",
            "source_date": date.today() - timedelta(days=3),
        },
        {
            "id": 4,
            "document_id": 4,
            "signal_type": "infrastructure",
            "summary": "New rapid transit line planned for broadway",
            "headline": "Broadway rapid transit project announced",
            "addresses": ["Broadway Corridor"],
            "neighborhood": "Kitsilano",
            "decision": "approved",
            "vote_for": 9,
            "vote_against": 2,
            "sentiment": "positive_for_development",
            "severity": "critical",
            "confidence": 0.92,
            "event_date": date.today() - timedelta(days=5),
            "source_title": "Transit Authority News",
            "source_url": "https://transit.vancouver.ca",
            "source_type": "community_plan",
            "source_date": date.today() - timedelta(days=5),
        },
        {
            "id": 5,
            "document_id": 5,
            "signal_type": "community_opposition",
            "summary": "Community groups oppose proposed development",
            "headline": "Community opposition to proposed tower",
            "addresses": ["789 Hastings St"],
            "neighborhood": "Downtown",
            "decision": "pending",
            "vote_for": None,
            "vote_against": None,
            "sentiment": "negative_for_development",
            "severity": "low",
            "confidence": 0.70,
            "event_date": date.today() - timedelta(days=4),
            "source_title": "Public Hearing Minutes",
            "source_url": "https://hearings.vancouver.ca",
            "source_type": "public_hearing",
            "source_date": date.today() - timedelta(days=4),
        },
    ]


@pytest.fixture
def sample_subscription():
    """Sample digest subscription."""
    return DigestSubscription(
        id=1,
        user_id=1,
        neighborhoods=["Downtown", "Mount Pleasant"],
        signal_types=["rezoning_decision", "permit_approval"],
        frequency=DigestFrequency.WEEKLY,
        is_active=True,
        created_at=datetime.utcnow(),
    )


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Signal Fetching
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_signals_for_period_all(mock_db_pool, sample_signals):
    """Test fetching all signals for a period."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=sample_signals
    )

    result = await DigestGenerator._fetch_signals_for_period(
        mock_db_pool,
        date.today() - timedelta(days=7),
        date.today(),
    )

    assert len(result) == 5
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_fetch_signals_for_period_with_neighborhood_filter(mock_db_pool, sample_signals):
    """Test fetching signals filtered by neighborhood."""
    downtown_signals = [s for s in sample_signals if s["neighborhood"] == "Downtown"]
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=downtown_signals
    )

    result = await DigestGenerator._fetch_signals_for_period(
        mock_db_pool,
        date.today() - timedelta(days=7),
        date.today(),
        neighborhoods=["Downtown"],
    )

    assert len(result) == 3
    assert all(s["neighborhood"] == "Downtown" for s in result)


@pytest.mark.asyncio
async def test_fetch_signals_for_period_with_type_filter(mock_db_pool, sample_signals):
    """Test fetching signals filtered by type."""
    rezoning_signals = [
        s for s in sample_signals
        if s["signal_type"] in ["rezoning_decision", "permit_approval"]
    ]
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=rezoning_signals
    )

    result = await DigestGenerator._fetch_signals_for_period(
        mock_db_pool,
        date.today() - timedelta(days=7),
        date.today(),
        signal_types=["rezoning_decision", "permit_approval"],
    )

    assert len(result) == 2
    assert all(s["signal_type"] in ["rezoning_decision", "permit_approval"] for s in result)


@pytest.mark.asyncio
async def test_fetch_signals_for_period_empty(mock_db_pool):
    """Test fetching signals when none exist."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=[]
    )

    result = await DigestGenerator._fetch_signals_for_period(
        mock_db_pool,
        date.today() - timedelta(days=7),
        date.today(),
    )

    assert len(result) == 0


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Signal Summarization
# ────────────────────────────────────────────────────────────────────────────

def test_summarize_signals(sample_signals):
    """Test signal summarization by category."""
    summary = DigestGenerator._summarize_signals(sample_signals)

    assert summary["by_type"]["rezoning_decision"] == 1
    assert summary["by_type"]["permit_approval"] == 1
    assert summary["by_type"]["infrastructure"] == 1
    assert summary["by_neighborhood"]["Downtown"] == 3
    assert summary["by_neighborhood"]["Mount Pleasant"] == 1
    assert summary["by_severity"]["critical"] == 1
    assert summary["by_severity"]["high"] == 2
    assert summary["by_severity"]["medium"] == 1


def test_summarize_signals_empty():
    """Test summarization of empty signal list."""
    summary = DigestGenerator._summarize_signals([])

    assert summary["by_type"] == {}
    assert summary["by_neighborhood"] == {}
    assert summary["by_severity"] == {}


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Highlight Generation
# ────────────────────────────────────────────────────────────────────────────

def test_generate_highlights_priority_order(sample_signals):
    """Test highlights are generated in correct priority order."""
    highlights = DigestGenerator._generate_highlights(sample_signals)

    # Should be top 5 by severity/confidence
    assert len(highlights) <= 5
    assert highlights[0].signal_id == 4  # critical infrastructure
    assert highlights[1].signal_id == 1 or highlights[1].signal_id == 3  # high severity
    assert all(isinstance(h, DigestHighlight) for h in highlights)


def test_generate_highlights_limited_to_five(sample_signals):
    """Test highlights capped at 5."""
    # Add more signals
    extended = sample_signals + sample_signals

    highlights = DigestGenerator._generate_highlights(extended)

    assert len(highlights) <= 5


def test_generate_highlights_empty():
    """Test highlight generation with no signals."""
    highlights = DigestGenerator._generate_highlights([])

    assert len(highlights) == 0


def test_generate_highlights_single_signal():
    """Test highlight generation with single signal."""
    signals = [
        {
            "id": 1,
            "headline": "Test headline",
            "summary": "Test summary",
            "signal_type": "rezoning_decision",
            "neighborhood": "Downtown",
            "severity": "high",
            "event_date": date.today(),
            "confidence": 0.95,
        }
    ]

    highlights = DigestGenerator._generate_highlights(signals)

    assert len(highlights) == 1
    assert highlights[0].headline == "Test headline"


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Statistics Computation
# ────────────────────────────────────────────────────────────────────────────

def test_compute_statistics(sample_signals):
    """Test statistics computation."""
    date_from = date.today() - timedelta(days=7)
    date_to = date.today()

    stats = DigestGenerator._compute_statistics(sample_signals, date_from, date_to)

    assert stats.total_signals == 5
    assert stats.period_days == 8
    assert len(stats.by_type) == 5
    assert len(stats.by_neighborhood) == 3
    assert len(stats.by_severity) == 4  # critical, high, medium, low
    assert stats.by_type["rezoning_decision"] == 1
    assert stats.by_neighborhood["Downtown"] == 3


def test_compute_statistics_empty():
    """Test statistics with no signals."""
    date_from = date.today() - timedelta(days=7)
    date_to = date.today()

    stats = DigestGenerator._compute_statistics([], date_from, date_to)

    assert stats.total_signals == 0
    assert stats.by_type == {}
    assert stats.by_neighborhood == {}


def test_compute_statistics_correct_period_days():
    """Test period days calculation is accurate."""
    date_from = date(2024, 1, 1)
    date_to = date(2024, 1, 8)

    stats = DigestGenerator._compute_statistics([], date_from, date_to)

    assert stats.period_days == 8


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Neighborhood Formatting
# ────────────────────────────────────────────────────────────────────────────

def test_format_neighborhood_updates(sample_signals):
    """Test neighborhood update formatting."""
    updates = DigestGenerator._format_neighborhood_updates(sample_signals)

    assert len(updates) == 3  # Downtown, Mount Pleasant, Kitsilano
    assert any(u.neighborhood == "Downtown" for u in updates)
    assert any(u.neighborhood == "Mount Pleasant" for u in updates)
    assert any(u.neighborhood == "Kitsilano" for u in updates)

    downtown = next(u for u in updates if u.neighborhood == "Downtown")
    assert downtown.signal_count == 3
    assert "rezoning_decision" in downtown.signal_types
    assert len(downtown.key_events) > 0


def test_format_neighborhood_updates_excludes_none(sample_signals):
    """Test that signals without neighborhood are excluded."""
    signals = sample_signals + [
        {
            "id": 10,
            "signal_type": "policy_change",
            "summary": "City-wide policy update",
            "headline": "City policy",
            "neighborhood": None,
            "severity": "info",
            "event_date": date.today(),
            "confidence": 0.8,
        }
    ]

    updates = DigestGenerator._format_neighborhood_updates(signals)

    # Should not create an update for None neighborhood
    assert all(u.neighborhood is not None for u in updates)


def test_format_neighborhood_updates_top_signal_selection(sample_signals):
    """Test that top signal is selected correctly."""
    updates = DigestGenerator._format_neighborhood_updates(sample_signals)

    downtown = next(u for u in updates if u.neighborhood == "Downtown")
    assert downtown.top_signal is not None
    # Should pick high severity signal (policy_change id=3)
    assert downtown.top_signal.severity in ["high", "critical"]


def test_format_neighborhood_updates_empty():
    """Test neighborhood formatting with no signals."""
    updates = DigestGenerator._format_neighborhood_updates([])

    assert len(updates) == 0


# ────────────────────────────────────────────────────────────────────────────
# Test DigestGenerator - Full Digest Generation
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_weekly_digest_full(mock_db_pool, sample_signals):
    """Test complete digest generation."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=sample_signals
    )

    digest = await DigestGenerator.generate_weekly_digest(
        mock_db_pool,
        user_id=1,
    )

    assert isinstance(digest, DigestContent)
    assert digest.statistics.total_signals == 5
    assert len(digest.highlights) > 0
    assert len(digest.neighborhood_updates) > 0
    assert len(digest.summary_text) > 0


@pytest.mark.asyncio
async def test_generate_weekly_digest_with_filters(mock_db_pool, sample_signals):
    """Test digest generation with neighborhood and type filters."""
    filtered = [s for s in sample_signals if s["neighborhood"] == "Downtown"]
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=filtered
    )

    digest = await DigestGenerator.generate_weekly_digest(
        mock_db_pool,
        user_id=1,
        neighborhoods=["Downtown"],
        signal_types=["rezoning_decision", "policy_change"],
    )

    assert digest.statistics.total_signals == len(filtered)


@pytest.mark.asyncio
async def test_generate_weekly_digest_date_range(mock_db_pool, sample_signals):
    """Test digest generation with custom date range."""
    date_from = date.today() - timedelta(days=14)
    date_to = date.today() - timedelta(days=7)

    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=sample_signals
    )

    digest = await DigestGenerator.generate_weekly_digest(
        mock_db_pool,
        user_id=1,
        date_from=date_from,
        date_to=date_to,
    )

    assert digest.date_from == date_from
    assert digest.date_to == date_to


@pytest.mark.asyncio
async def test_generate_weekly_digest_empty_period(mock_db_pool):
    """Test digest generation with no signals."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=[]
    )

    digest = await DigestGenerator.generate_weekly_digest(
        mock_db_pool,
        user_id=1,
    )

    assert digest.statistics.total_signals == 0
    assert len(digest.highlights) == 0
    assert len(digest.neighborhood_updates) == 0


# ────────────────────────────────────────────────────────────────────────────
# Test DigestScheduler - Subscription Management
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_subscriptions(mock_db_pool):
    """Test retrieving active subscriptions."""
    subscriptions_data = [
        {
            "id": 1,
            "user_id": 1,
            "neighborhoods": ["Downtown"],
            "signal_types": ["rezoning_decision"],
            "frequency": "weekly",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "id": 2,
            "user_id": 2,
            "neighborhoods": ["Mount Pleasant"],
            "signal_types": [],
            "frequency": "daily",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    ]

    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=subscriptions_data
    )

    result = await DigestScheduler.get_active_subscriptions(mock_db_pool)

    assert len(result) == 2
    assert result[0].user_id == 1
    assert result[1].frequency == DigestFrequency.DAILY


@pytest.mark.asyncio
async def test_get_active_subscriptions_filtered_by_frequency(mock_db_pool):
    """Test retrieving subscriptions filtered by frequency."""
    weekly_subs = [
        {
            "id": 1,
            "user_id": 1,
            "neighborhoods": [],
            "signal_types": [],
            "frequency": "weekly",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    ]

    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=weekly_subs
    )

    result = await DigestScheduler.get_active_subscriptions(
        mock_db_pool,
        frequency=DigestFrequency.WEEKLY,
    )

    assert len(result) == 1
    assert result[0].frequency == DigestFrequency.WEEKLY


# ────────────────────────────────────────────────────────────────────────────
# Test DigestScheduler - Digest Processing
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_subscription_new_delivery(mock_db_pool, sample_subscription, sample_signals):
    """Test processing a subscription creates new delivery."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=sample_signals
    )
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchrow = AsyncMock(
        return_value=None  # No existing delivery
    )
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchval = AsyncMock(
        return_value=1  # New delivery ID
    )

    with patch.object(DigestGenerator, 'generate_weekly_digest') as mock_gen:
        mock_gen.return_value = DigestContent(
            subscription_id=sample_subscription.id,
            digest_date=date.today(),
            date_from=date.today() - timedelta(days=7),
            date_to=date.today(),
            highlights=[],
            statistics=DigestStats(
                total_signals=5,
                by_type={},
                by_neighborhood={},
                by_severity={},
                period_days=7,
            ),
            neighborhood_updates=[],
            summary_text="Test summary",
        )

        delivery = await DigestScheduler.process_subscription(
            mock_db_pool,
            sample_subscription,
        )

    assert delivery.id == 1
    assert delivery.subscription_id == sample_subscription.id
    assert delivery.delivery_status == DeliveryStatus.PENDING


@pytest.mark.asyncio
async def test_process_subscription_existing_delivery(mock_db_pool, sample_subscription, sample_signals):
    """Test processing updates existing delivery."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=sample_signals
    )
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchrow = AsyncMock(
        return_value={"id": 99}  # Existing delivery
    )

    with patch.object(DigestGenerator, 'generate_weekly_digest') as mock_gen:
        mock_gen.return_value = DigestContent(
            subscription_id=sample_subscription.id,
            digest_date=date.today(),
            date_from=date.today() - timedelta(days=7),
            date_to=date.today(),
            highlights=[],
            statistics=DigestStats(
                total_signals=5,
                by_type={},
                by_neighborhood={},
                by_severity={},
                period_days=7,
            ),
            neighborhood_updates=[],
            summary_text="Test summary",
        )

        delivery = await DigestScheduler.process_subscription(
            mock_db_pool,
            sample_subscription,
        )

    assert delivery.id == 99


# ────────────────────────────────────────────────────────────────────────────
# Test DigestScheduler - Digest Cycle
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_digest_cycle(mock_db_pool):
    """Test running a full digest cycle."""
    subscriptions_data = [
        {
            "id": 1,
            "user_id": 1,
            "neighborhoods": [],
            "signal_types": [],
            "frequency": "weekly",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "id": 2,
            "user_id": 2,
            "neighborhoods": [],
            "signal_types": [],
            "frequency": "weekly",
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    ]

    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(
        return_value=[]
    )
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchrow = AsyncMock(
        return_value=None
    )
    mock_db_pool.acquire.return_value.__aenter__.return_value.fetchval = AsyncMock(
        side_effect=[1, 2]  # Two delivery IDs
    )

    # Override the fetch to return subscriptions first
    call_count = [0]

    async def fetch_side_effect(query, *args):
        call_count[0] += 1
        if "digest_subscriptions" in query:
            return subscriptions_data
        return []

    mock_db_pool.acquire.return_value.__aenter__.return_value.fetch = fetch_side_effect

    with patch.object(DigestScheduler, 'get_active_subscriptions') as mock_get_subs:
        mock_get_subs.return_value = [
            DigestSubscription(
                id=1,
                user_id=1,
                neighborhoods=[],
                signal_types=[],
                frequency=DigestFrequency.WEEKLY,
                is_active=True,
            ),
            DigestSubscription(
                id=2,
                user_id=2,
                neighborhoods=[],
                signal_types=[],
                frequency=DigestFrequency.WEEKLY,
                is_active=True,
            ),
        ]

        with patch.object(DigestScheduler, 'process_subscription') as mock_process:
            mock_process.side_effect = [
                DigestDelivery(
                    id=1,
                    subscription_id=1,
                    digest_date=date.today(),
                    content_json={},
                    signal_count=0,
                ),
                DigestDelivery(
                    id=2,
                    subscription_id=2,
                    digest_date=date.today(),
                    content_json={},
                    signal_count=0,
                ),
            ]

            deliveries = await DigestScheduler.run_digest_cycle(mock_db_pool)

    assert len(deliveries) == 2


# ────────────────────────────────────────────────────────────────────────────
# Test DigestScheduler - Delivery Status Management
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_delivery_sent(mock_db_pool):
    """Test marking delivery as sent."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock()

    result = await DigestScheduler.mark_delivery_sent(mock_db_pool, delivery_id=1)

    assert result is True
    mock_db_pool.acquire.return_value.__aenter__.return_value.execute.assert_called_once()


@pytest.mark.asyncio
async def test_mark_delivery_failed(mock_db_pool):
    """Test marking delivery as failed."""
    mock_db_pool.acquire.return_value.__aenter__.return_value.execute = AsyncMock()

    result = await DigestScheduler.mark_delivery_failed(
        mock_db_pool,
        delivery_id=1,
        error_message="Test error",
    )

    assert result is True
    mock_db_pool.acquire.return_value.__aenter__.return_value.execute.assert_called_once()


# ────────────────────────────────────────────────────────────────────────────
# Test Edge Cases
# ────────────────────────────────────────────────────────────────────────────

def test_create_summary_text_no_signals():
    """Test summary text generation with no signals."""
    stats = DigestStats(
        total_signals=0,
        by_type={},
        by_neighborhood={},
        by_severity={},
        period_days=7,
    )

    text = DigestGenerator._create_summary_text(0, stats, [], [])

    assert "No intelligence signals" in text
    assert "VanCity Lens Weekly Digest" in text


def test_create_summary_text_with_signals():
    """Test summary text generation with signals."""
    stats = DigestStats(
        total_signals=5,
        by_type={"rezoning_decision": 2, "permit_approval": 3},
        by_neighborhood={"Downtown": 3, "Mount Pleasant": 2},
        by_severity={"high": 3, "medium": 2},
        period_days=7,
    )

    highlights = [
        DigestHighlight(
            signal_id=1,
            headline="Test headline 1",
            summary="Test summary",
            signal_type="rezoning_decision",
            neighborhood="Downtown",
            severity="high",
            event_date=date.today(),
            confidence=0.95,
        ),
    ]

    text = DigestGenerator._create_summary_text(5, stats, ["Downtown"], highlights)

    assert "5 intelligence signals" in text
    # The summary doesn't explicitly include neighborhood names, just counts
    assert "2 neighborhoods" in text  # Summary shows neighborhood count
    assert "Test headline 1" in text


def test_summarize_signals_with_missing_fields():
    """Test summarization handles signals with missing optional fields."""
    signals = [
        {
            "id": 1,
            "signal_type": "rezoning_decision",
            "severity": "high",
            "neighborhood": None,  # Missing neighborhood
        },
        {
            "id": 2,
            "signal_type": "permit_approval",
            "severity": "medium",
            "neighborhood": "Downtown",
        },
    ]

    summary = DigestGenerator._summarize_signals(signals)

    assert summary["by_type"]["rezoning_decision"] == 1
    assert summary["by_type"]["permit_approval"] == 1
    assert summary["by_neighborhood"]["Downtown"] == 1
    assert "None" not in summary["by_neighborhood"]


def test_generate_highlights_with_missing_fields():
    """Test highlight generation handles missing fields."""
    signals = [
        {
            "id": 1,
            "headline": None,
            "summary": "Signal 1 summary",
            "signal_type": "rezoning_decision",
            "neighborhood": "Downtown",
            "severity": "high",
            "event_date": date.today(),
            "confidence": 0.95,
        },
        {
            "id": 2,
            "headline": "Signal 2 headline",
            "summary": "Signal 2 summary",
            "signal_type": "permit_approval",
            "neighborhood": "Mount Pleasant",
            "severity": "medium",
            "event_date": date.today(),
            "confidence": 0.85,
        },
    ]

    highlights = DigestGenerator._generate_highlights(signals)

    assert len(highlights) == 2
    assert highlights[0].headline is not None or highlights[0].summary is not None


# ────────────────────────────────────────────────────────────────────────────
# Test Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

def test_digest_subscription_model():
    """Test DigestSubscription model validation."""
    sub = DigestSubscription(
        id=1,
        user_id=1,
        neighborhoods=["Downtown"],
        signal_types=["rezoning_decision"],
        frequency=DigestFrequency.WEEKLY,
        is_active=True,
    )

    assert sub.user_id == 1
    assert len(sub.neighborhoods) == 1
    assert sub.frequency == DigestFrequency.WEEKLY


def test_digest_content_model():
    """Test DigestContent model validation."""
    content = DigestContent(
        subscription_id=1,
        digest_date=date.today(),
        date_from=date.today() - timedelta(days=7),
        date_to=date.today(),
        highlights=[],
        statistics=DigestStats(
            total_signals=0,
            by_type={},
            by_neighborhood={},
            by_severity={},
            period_days=7,
        ),
        neighborhood_updates=[],
        summary_text="Test",
    )

    assert content.subscription_id == 1
    assert content.statistics.total_signals == 0


def test_digest_delivery_model():
    """Test DigestDelivery model validation."""
    delivery = DigestDelivery(
        id=1,
        subscription_id=1,
        digest_date=date.today(),
        content_json={"test": "data"},
        signal_count=5,
        delivery_status=DeliveryStatus.PENDING,
    )

    assert delivery.id == 1
    assert delivery.signal_count == 5
    assert delivery.delivery_status == DeliveryStatus.PENDING
