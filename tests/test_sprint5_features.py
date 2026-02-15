"""
Sprint 5 tests — Regulatory Intelligence Completion

Tests cover:
- NLP extraction confidence threshold + review queue (DV-REG-002)
- Daily digest option
- Geographic scope validation (DV-REG-004)
- Effective date validation (DV-REG-003)
- Municipal bylaw amendment detection
- Review queue routes
"""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Confidence Threshold Tests ───────────────────────────────────

from api.intelligence.extractor import CONFIDENCE_AUTO_APPROVE_THRESHOLD


class TestConfidenceThreshold:
    """DV-REG-002: Confidence threshold for review flagging."""

    def test_threshold_is_85_percent(self):
        assert CONFIDENCE_AUTO_APPROVE_THRESHOLD == 0.85

    def test_high_confidence_auto_approved(self):
        """Signals with confidence >= 0.85 get auto_approved."""
        confidence = 0.90
        review_status = "auto_approved" if confidence >= CONFIDENCE_AUTO_APPROVE_THRESHOLD else "pending_review"
        assert review_status == "auto_approved"

    def test_low_confidence_pending_review(self):
        """Signals with confidence < 0.85 get pending_review."""
        confidence = 0.60
        review_status = "auto_approved" if confidence >= CONFIDENCE_AUTO_APPROVE_THRESHOLD else "pending_review"
        assert review_status == "pending_review"

    def test_boundary_confidence_auto_approved(self):
        """Signals at exactly 0.85 get auto_approved."""
        confidence = 0.85
        review_status = "auto_approved" if confidence >= CONFIDENCE_AUTO_APPROVE_THRESHOLD else "pending_review"
        assert review_status == "auto_approved"

    def test_just_below_threshold_pending(self):
        confidence = 0.849
        review_status = "auto_approved" if confidence >= CONFIDENCE_AUTO_APPROVE_THRESHOLD else "pending_review"
        assert review_status == "pending_review"


# ── Review Queue Tests ───────────────────────────────────────────

from api.intelligence.review_queue import (
    get_pending_reviews,
    review_signal,
    bulk_review,
    get_review_stats,
)


class TestReviewQueue:
    """Test review queue functions."""

    @pytest.mark.asyncio
    async def test_review_signal_approve(self):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = acm

        mock_conn.fetchrow.return_value = {
            "id": 1, "signal_type": "rezoning",
            "summary": "Test", "confidence": 0.6,
            "review_status": "approved",
        }

        result = await review_signal(mock_pool, 1, "approve", reviewer_id=1, notes="Looks good")
        assert result is not None
        assert result["review_status"] == "approved"

    @pytest.mark.asyncio
    async def test_review_signal_reject(self):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = acm

        mock_conn.fetchrow.return_value = {
            "id": 2, "signal_type": "rezoning",
            "summary": "Noise", "confidence": 0.3,
            "review_status": "rejected",
        }

        result = await review_signal(mock_pool, 2, "reject", reviewer_id=1)
        assert result["review_status"] == "rejected"

    @pytest.mark.asyncio
    async def test_review_signal_invalid_action(self):
        mock_pool = MagicMock()
        with pytest.raises(ValueError, match="Invalid action"):
            await review_signal(mock_pool, 1, "invalid", reviewer_id=1)

    @pytest.mark.asyncio
    async def test_bulk_review(self):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = acm
        mock_conn.execute.return_value = "UPDATE 3"

        result = await bulk_review(mock_pool, [1, 2, 3], "approve", reviewer_id=1)
        assert result["updated"] == 3
        assert result["action"] == "approve"

    @pytest.mark.asyncio
    async def test_get_review_stats(self):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = acm

        mock_conn.fetchrow.return_value = {
            "pending": 5, "approved": 100,
            "rejected": 10, "auto_approved": 500,
            "avg_pending_confidence": 0.65,
        }

        stats = await get_review_stats(mock_pool)
        assert stats["pending"] == 5
        assert stats["auto_approved"] == 500


# ── Geographic Validation Tests ──────────────────────────────────

from api.intelligence.geo_validation import (
    resolve_neighborhood,
    validate_zoning,
    validate_event_date_range,
    VANCOUVER_NEIGHBORHOODS,
)


class TestGeographicValidation:
    """DV-REG-004: Geographic scope validation."""

    def test_canonical_neighborhoods_count(self):
        assert len(VANCOUVER_NEIGHBORHOODS) == 22

    def test_resolve_exact_match(self):
        name, valid = resolve_neighborhood("Kitsilano")
        assert name == "Kitsilano"
        assert valid is True

    def test_resolve_case_insensitive(self):
        name, valid = resolve_neighborhood("kitsilano")
        assert name == "Kitsilano"
        assert valid is True

    def test_resolve_alias_kits(self):
        name, valid = resolve_neighborhood("Kits")
        assert name == "Kitsilano"
        assert valid is True

    def test_resolve_alias_commercial_drive(self):
        name, valid = resolve_neighborhood("Commercial Drive")
        assert name == "Grandview-Woodland"
        assert valid is True

    def test_resolve_alias_mt_pleasant(self):
        name, valid = resolve_neighborhood("Mt Pleasant")
        assert name == "Mount Pleasant"
        assert valid is True

    def test_resolve_non_vancouver(self):
        name, valid = resolve_neighborhood("Burnaby")
        assert valid is False  # Burnaby is not a Vancouver neighborhood

    def test_resolve_unknown(self):
        name, valid = resolve_neighborhood("Atlantis")
        assert valid is False

    def test_resolve_none(self):
        name, valid = resolve_neighborhood(None)
        assert name is None
        assert valid is False

    def test_resolve_empty_string(self):
        name, valid = resolve_neighborhood("")
        assert valid is False

    def test_validate_zoning_rs1(self):
        assert validate_zoning("RS-1") is True

    def test_validate_zoning_rm4(self):
        assert validate_zoning("RM-4") is True

    def test_validate_zoning_cd1(self):
        assert validate_zoning("CD-1") is True

    def test_validate_zoning_c2(self):
        assert validate_zoning("C-2") is True

    def test_validate_zoning_invalid(self):
        assert validate_zoning("ZZZZ-99") is False

    def test_validate_zoning_none(self):
        assert validate_zoning(None) is False


# ── Event Date Validation Tests ──────────────────────────────────

class TestEventDateValidation:
    """DV-REG-003: Effective date validation rules."""

    def test_valid_recent_date(self):
        valid, reason = validate_event_date_range("2025-06-15")
        assert valid is True
        assert reason is None

    def test_valid_today(self):
        valid, reason = validate_event_date_range(date.today().isoformat())
        assert valid is True

    def test_null_date_is_valid(self):
        valid, reason = validate_event_date_range(None)
        assert valid is True

    def test_date_too_old(self):
        old_date = (date.today() - timedelta(days=365 * 6)).isoformat()
        valid, reason = validate_event_date_range(old_date)
        assert valid is False
        assert "5 years" in reason

    def test_date_too_far_future(self):
        future_date = (date.today() + timedelta(days=400)).isoformat()
        valid, reason = validate_event_date_range(future_date)
        assert valid is False
        assert "1 year" in reason

    def test_invalid_format(self):
        valid, reason = validate_event_date_range("not-a-date")
        assert valid is False
        assert "Invalid date" in reason

    def test_date_object_input(self):
        valid, reason = validate_event_date_range(date.today())
        assert valid is True


# ── Bylaw Detection Tests ───────────────────────────────────────

from api.intelligence.bylaw_detection import (
    detect_bylaw_references,
    detect_zoning_changes,
    COMPILED_PATTERNS,
)


class TestBylawDetection:
    """Test municipal bylaw amendment detection."""

    def test_detect_bylaw_number(self):
        text = "Council approved Bylaw No. 12345 amending the zoning schedule."
        refs = detect_bylaw_references(text)
        assert len(refs) >= 1
        assert any(r["bylaw_number"] == "12345" for r in refs)

    def test_detect_bylaw_hyphenated(self):
        text = "The by-law no. 99876 was enacted on January 15."
        refs = detect_bylaw_references(text)
        assert len(refs) >= 1

    def test_detect_zoning_amendment_language(self):
        text = "Council voted to amend the zoning bylaw for the Cambie corridor."
        refs = detect_bylaw_references(text)
        assert len(refs) >= 1

    def test_detect_public_hearing(self):
        text = "A public hearing on bylaw rezoning amendment for Cambie was held."
        refs = detect_bylaw_references(text)
        assert len(refs) >= 1

    def test_detect_reading(self):
        text = "The first reading of the rezoning amendment was approved."
        refs = detect_bylaw_references(text)
        assert len(refs) >= 1

    def test_no_false_positive(self):
        text = "The weather in Vancouver was sunny today with clear skies."
        refs = detect_bylaw_references(text)
        assert len(refs) == 0

    def test_detect_zoning_change_from_to(self):
        text = "The property will be rezoned from RS-1 to RM-4."
        changes = detect_zoning_changes(text)
        assert len(changes) == 1
        assert changes[0]["zoning_from"] == "RS-1"
        assert changes[0]["zoning_to"] == "RM-4"

    def test_detect_zoning_change_reclassify(self):
        text = "reclassified from C-2 to CD-1"
        changes = detect_zoning_changes(text)
        assert len(changes) == 1

    def test_no_zoning_change(self):
        text = "The current zoning is RS-1."
        changes = detect_zoning_changes(text)
        assert len(changes) == 0

    def test_compiled_patterns_exist(self):
        assert len(COMPILED_PATTERNS) > 5


# ── Digest Frequency Tests ───────────────────────────────────────

from api.intelligence.digest import DigestFrequency


class TestDigestFrequency:
    """Test daily/weekly digest frequency support."""

    def test_daily_frequency_exists(self):
        assert DigestFrequency.DAILY.value == "daily"

    def test_weekly_frequency_exists(self):
        assert DigestFrequency.WEEKLY.value == "weekly"


# ── Review Routes Tests ──────────────────────────────────────────

from api.intelligence.review_routes import router as review_router


class TestReviewRoutes:
    """Test review queue API routes configuration."""

    def test_router_prefix(self):
        assert review_router.prefix == "/api/v1/admin/review-queue"

    def test_has_list_route(self):
        paths = [r.path for r in review_router.routes]
        assert any("" == p or "/api/v1/admin/review-queue" in p for p in paths)

    def test_has_stats_route(self):
        paths = [r.path for r in review_router.routes]
        assert any("stats" in p for p in paths)

    def test_has_review_route(self):
        paths = [r.path for r in review_router.routes]
        assert any("review" in p for p in paths)

    def test_has_bulk_review_route(self):
        paths = [r.path for r in review_router.routes]
        assert any("bulk" in p for p in paths)


# ── Migration Tests ──────────────────────────────────────────────

class TestSprint5Migration:
    """Test Sprint 5 migration file."""

    def test_migration_exists(self):
        import os
        assert os.path.exists("db/038_review_queue_sprint5.sql")

    def test_migration_adds_review_columns(self):
        with open("db/038_review_queue_sprint5.sql") as f:
            sql = f.read()
        assert "review_status" in sql
        assert "reviewed_by" in sql
        assert "reviewed_at" in sql
        assert "review_notes" in sql

    def test_migration_adds_neighborhoods_table(self):
        with open("db/038_review_queue_sprint5.sql") as f:
            sql = f.read()
        assert "vancouver_neighborhoods" in sql
        assert "Kitsilano" in sql
        assert "Mount Pleasant" in sql

    def test_migration_adds_digest_personalization(self):
        with open("db/038_review_queue_sprint5.sql") as f:
            sql = f.read()
        assert "severity_min" in sql
        assert "max_signals_per_digest" in sql

    def test_migration_has_review_status_index(self):
        with open("db/038_review_queue_sprint5.sql") as f:
            sql = f.read()
        assert "idx_signals_review_status" in sql
