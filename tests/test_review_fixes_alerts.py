"""
Tests for review fixes to api/intelligence/alerts.py:
- Severity enum has all 5 values
- AlertType enum has all 3 values
- AlertCreate accepts Severity and AlertType enums (and string values via str, Enum)
- match_rule() does NOT swallow unexpected errors
- _alert_exists() propagates database errors
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.intelligence.alerts import (
    Severity,
    AlertType,
    AlertCreate,
    Alert,
    AlertEngine,
    WatchlistRule,
    RuleType,
)


# ────────────────────────────────────────────────────────────────────────────
# Severity Enum Tests
# ────────────────────────────────────────────────────────────────────────────

class TestSeverityEnum:
    """Verify Severity enum has all 5 expected values."""

    def test_severity_has_info(self):
        assert Severity.INFO == "info"

    def test_severity_has_low(self):
        assert Severity.LOW == "low"

    def test_severity_has_medium(self):
        assert Severity.MEDIUM == "medium"

    def test_severity_has_high(self):
        assert Severity.HIGH == "high"

    def test_severity_has_critical(self):
        assert Severity.CRITICAL == "critical"

    def test_severity_has_exactly_5_members(self):
        assert len(Severity) == 5

    def test_severity_is_str_enum(self):
        """Severity inherits from str so it serializes to/from strings."""
        assert isinstance(Severity.HIGH, str)
        assert Severity("high") == Severity.HIGH


# ────────────────────────────────────────────────────────────────────────────
# AlertType Enum Tests
# ────────────────────────────────────────────────────────────────────────────

class TestAlertTypeEnum:
    """Verify AlertType enum has all 3 expected values."""

    def test_alert_type_has_signal_match(self):
        assert AlertType.SIGNAL_MATCH == "signal_match"

    def test_alert_type_has_stage_transition(self):
        assert AlertType.STAGE_TRANSITION == "stage_transition"

    def test_alert_type_has_undervalued_match(self):
        assert AlertType.UNDERVALUED_MATCH == "undervalued_match"

    def test_alert_type_has_exactly_3_members(self):
        assert len(AlertType) == 3

    def test_alert_type_is_str_enum(self):
        """AlertType inherits from str so it serializes to/from strings."""
        assert isinstance(AlertType.SIGNAL_MATCH, str)
        assert AlertType("signal_match") == AlertType.SIGNAL_MATCH


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Model Tests with Enums
# ────────────────────────────────────────────────────────────────────────────

class TestAlertCreateWithEnums:
    """Verify AlertCreate model accepts Severity and AlertType enums."""

    def test_alert_create_with_enum_values(self):
        alert = AlertCreate(
            watchlist_id=1,
            signal_id=10,
            alert_type=AlertType.SIGNAL_MATCH,
            headline="Test headline",
            severity=Severity.HIGH,
        )
        assert alert.alert_type == AlertType.SIGNAL_MATCH
        assert alert.severity == Severity.HIGH

    def test_alert_create_with_string_values(self):
        """String values like 'high' should still work due to (str, Enum)."""
        alert = AlertCreate(
            watchlist_id=1,
            signal_id=10,
            alert_type="signal_match",
            headline="Test headline",
            severity="high",
        )
        assert alert.alert_type == AlertType.SIGNAL_MATCH
        assert alert.severity == Severity.HIGH

    def test_alert_create_default_alert_type(self):
        """Default alert_type should be AlertType.SIGNAL_MATCH."""
        alert = AlertCreate(
            watchlist_id=1,
            signal_id=10,
            headline="Test",
            severity=Severity.LOW,
        )
        assert alert.alert_type == AlertType.SIGNAL_MATCH

    def test_alert_create_rejects_invalid_severity(self):
        """Invalid severity string should raise validation error."""
        with pytest.raises(Exception):
            AlertCreate(
                watchlist_id=1,
                signal_id=10,
                headline="Test",
                severity="bogus",
            )

    def test_alert_create_rejects_invalid_alert_type(self):
        """Invalid alert_type string should raise validation error."""
        with pytest.raises(Exception):
            AlertCreate(
                watchlist_id=1,
                signal_id=10,
                alert_type="bogus",
                headline="Test",
                severity="high",
            )

    def test_alert_create_with_undervalued_match(self):
        alert = AlertCreate(
            watchlist_id=1,
            signal_id=10,
            alert_type=AlertType.UNDERVALUED_MATCH,
            headline="Undervalued property found",
            severity=Severity.MEDIUM,
        )
        assert alert.alert_type == AlertType.UNDERVALUED_MATCH

    def test_alert_create_with_stage_transition(self):
        alert = AlertCreate(
            watchlist_id=1,
            signal_id=10,
            alert_type=AlertType.STAGE_TRANSITION,
            headline="Pipeline stage changed",
            severity=Severity.INFO,
        )
        assert alert.alert_type == AlertType.STAGE_TRANSITION


class TestAlertResponseModelWithEnums:
    """Verify Alert response model uses Severity and AlertType enums."""

    def test_alert_model_with_string_values(self):
        """Alert model should accept string values from DB rows."""
        from datetime import datetime

        alert = Alert(
            id=1,
            watchlist_id=1,
            signal_id=10,
            alert_type="signal_match",
            headline="Test",
            summary=None,
            severity="high",
            is_read=False,
            created_at=datetime.now(),
        )
        assert alert.severity == Severity.HIGH
        assert alert.alert_type == AlertType.SIGNAL_MATCH


# ────────────────────────────────────────────────────────────────────────────
# match_rule() Error Propagation Tests
# ────────────────────────────────────────────────────────────────────────────

class TestMatchRuleErrorPropagation:
    """Verify match_rule() does NOT swallow unexpected errors."""

    def test_match_rule_propagates_attribute_error(self):
        """If signal has a non-iterable where a list is expected, error should propagate."""
        signal = {
            "id": 1,
            "addresses": 12345,  # Not iterable -- will cause TypeError in any()
        }
        rule = WatchlistRule(rule_type=RuleType.ADDRESS, rule_value="main street")

        with pytest.raises(TypeError):
            AlertEngine.match_rule(signal, rule)

    def test_match_rule_propagates_error_from_neighborhood(self):
        """If neighborhood value causes an unexpected error, it should propagate."""
        signal = {
            "id": 1,
            "neighborhood": 42,  # int has no .lower()
        }
        rule = WatchlistRule(rule_type=RuleType.NEIGHBORHOOD, rule_value="downtown")

        with pytest.raises(AttributeError):
            AlertEngine.match_rule(signal, rule)

    def test_match_rule_still_handles_range_parse_errors(self):
        """Inner try/except for range parsing should still catch ValueError/IndexError."""
        signal = {"id": 1, "proposed_storeys": 10}
        rule = WatchlistRule(rule_type=RuleType.HEIGHT_RANGE, rule_value="not-a-number")

        # This should NOT raise -- the inner except (ValueError, IndexError) handles it
        result = AlertEngine.match_rule(signal, rule)
        assert result is False

    def test_match_rule_still_handles_unit_range_parse_errors(self):
        """Inner try/except for unit range parsing should still catch parse errors."""
        signal = {"id": 1, "unit_count": 50}
        rule = WatchlistRule(rule_type=RuleType.UNIT_RANGE, rule_value="abc")

        result = AlertEngine.match_rule(signal, rule)
        assert result is False

    def test_match_rule_propagates_error_in_keyword_branch(self):
        """If headline is a non-string type that doesn't support 'in', error should propagate."""
        signal = {
            "id": 1,
            # headline is set to a type that will cause TypeError when we do
            # rule_value in headline (headline is an int after or-fallback)
            "headline": None,
            "summary": None,
        }
        rule = WatchlistRule(rule_type=RuleType.KEYWORD, rule_value="test")

        # With our current code, (None or '').lower() => ''.lower() => '' which is fine.
        # Let's try something that actually breaks:
        # We need to mock .get to return something that causes an unexpected error.
        # Actually, the existing code handles None gracefully via `or ''`.
        # So let's test with a signal dict that has a property that raises on access.
        class BadDict(dict):
            def get(self, key, default=None):
                if key == "headline":
                    raise RuntimeError("Unexpected DB error reading headline")
                return super().get(key, default)

        bad_signal = BadDict({"id": 1})
        with pytest.raises(RuntimeError, match="Unexpected DB error"):
            AlertEngine.match_rule(bad_signal, rule)


# ────────────────────────────────────────────────────────────────────────────
# _alert_exists() Error Propagation Tests
# ────────────────────────────────────────────────────────────────────────────

class TestAlertExistsErrorPropagation:
    """Verify _alert_exists() propagates database errors instead of returning False."""

    @pytest.fixture
    def mock_db_pool(self):
        """Mock asyncpg connection pool."""
        pool = AsyncMock()
        pool.acquire = MagicMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        return pool

    @pytest.mark.asyncio
    async def test_alert_exists_propagates_db_error(self, mock_db_pool):
        """DB errors in _alert_exists should propagate, not return False."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            await AlertEngine._alert_exists(mock_db_pool, watchlist_id=1, signal_id=10)

    @pytest.mark.asyncio
    async def test_alert_exists_propagates_asyncpg_error(self, mock_db_pool):
        """Simulated asyncpg errors should propagate."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.side_effect = ConnectionError("pool exhausted")

        with pytest.raises(ConnectionError, match="pool exhausted"):
            await AlertEngine._alert_exists(mock_db_pool, watchlist_id=1, signal_id=10)

    @pytest.mark.asyncio
    async def test_alert_exists_returns_true_when_found(self, mock_db_pool):
        """Normal case: returns True when alert row exists."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.return_value = {"id": 42}

        result = await AlertEngine._alert_exists(mock_db_pool, watchlist_id=1, signal_id=10)
        assert result is True

    @pytest.mark.asyncio
    async def test_alert_exists_returns_false_when_not_found(self, mock_db_pool):
        """Normal case: returns False when no alert row exists."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.return_value = None

        result = await AlertEngine._alert_exists(mock_db_pool, watchlist_id=1, signal_id=10)
        assert result is False
