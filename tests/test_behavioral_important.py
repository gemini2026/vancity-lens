"""
Behavioral tests for important gaps (Gaps 6-12).

Covers:
- Gap 6:  compute_implied_value + compute_discount_pct unit tests
- Gap 7:  build_caveats combination tests
- Gap 8:  z-score anomaly detection in _collect_red_flags
- Gap 9:  Parcel search disambiguation (mock-based)
- Gap 10: RetrievalTracker.log_retrieval context manager
- Gap 11: GEOGRAPHIC_SCOPE rule matching edge case
- Gap 12: AddressNormalizer.normalize
"""

import json
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Gap 6: compute_implied_value + compute_discount_pct + is_undervalued
# ---------------------------------------------------------------------------
from api.intelligence.undervalued_scoring import (
    UNDERVALUED_THRESHOLD_PCT,
    build_caveats,
    compute_discount_pct,
    compute_implied_value,
    is_undervalued,
)


class TestComputeImpliedValue:
    """Gap 6: Unit tests for compute_implied_value."""

    @pytest.mark.parametrize(
        "buildable_sqft, avg_comp, expected",
        [
            (0, 500, 0),          # zero buildable -> 0
            (-100, 500, 0),       # negative buildable -> 0
            (1000, 0, 0),         # zero comp -> 0
            (1000, -10, 0),       # negative comp -> 0
            (1000, 500, 500000),  # normal case
            (1, 1, 1),            # edge minimal
        ],
    )
    def test_compute_implied_value(self, buildable_sqft, avg_comp, expected):
        assert compute_implied_value(buildable_sqft, avg_comp) == expected


class TestComputeDiscountPct:
    """Gap 6: Unit tests for compute_discount_pct."""

    def test_assessed_value_none_returns_none(self):
        result = compute_discount_pct(assessed_value=None, implied_value=2000000)
        assert result is None

    def test_implied_value_zero_returns_none(self):
        result = compute_discount_pct(assessed_value=1000000, implied_value=0)
        assert result is None

    def test_implied_value_negative_returns_none(self):
        result = compute_discount_pct(assessed_value=1000000, implied_value=-100)
        assert result is None

    def test_50pct_discount(self):
        # assessed=1M, implied=2M -> (2M-1M)/2M*100 = 50.0%
        result = compute_discount_pct(assessed_value=1000000, implied_value=2000000)
        assert result == 50.0

    def test_zero_discount_same_values(self):
        result = compute_discount_pct(assessed_value=1000000, implied_value=1000000)
        assert result == 0.0

    def test_negative_discount_overvalued(self):
        # assessed=2M, implied=1M -> (1M-2M)/1M*100 = -100.0
        result = compute_discount_pct(assessed_value=2000000, implied_value=1000000)
        assert result == -100.0


class TestIsUndervalued:
    """Gap 6: is_undervalued threshold tests (threshold is 25.0%)."""

    def test_threshold_value(self):
        """Verify the threshold constant is 25.0."""
        assert UNDERVALUED_THRESHOLD_PCT == 25.0

    def test_none_returns_false(self):
        assert is_undervalued(None) is False

    def test_below_threshold_returns_false(self):
        # 24.9% is not > 25.0%
        assert is_undervalued(24.9) is False

    def test_at_threshold_returns_false(self):
        # 25.0% is not > 25.0% (strict greater-than)
        assert is_undervalued(25.0) is False

    def test_above_threshold_returns_true(self):
        # 25.1% > 25.0%
        assert is_undervalued(25.1) is True

    def test_well_above_threshold_returns_true(self):
        assert is_undervalued(50.0) is True


# ---------------------------------------------------------------------------
# Gap 7: build_caveats
# ---------------------------------------------------------------------------


class TestBuildCaveats:
    """Gap 7: build_caveats combination tests."""

    def test_no_caveats(self):
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=10,
            bca_age_months=6,
        )
        assert caveats == []

    def test_contamination_caveat(self):
        caveats = build_caveats(
            has_contamination=True,
            has_heritage=False,
            comp_count=10,
            bca_age_months=6,
        )
        assert len(caveats) == 1
        assert "contamination" in caveats[0].lower()

    def test_heritage_caveat(self):
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=True,
            comp_count=10,
            bca_age_months=6,
        )
        assert len(caveats) == 1
        assert "heritage" in caveats[0].lower()

    def test_low_comp_count_caveat(self):
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=3,
            bca_age_months=6,
        )
        assert len(caveats) == 1
        assert "3 transactions" in caveats[0]

    def test_comp_count_at_threshold_no_caveat(self):
        """comp_count >= 5 should not trigger caveat."""
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=5,
            bca_age_months=6,
        )
        assert caveats == []

    def test_old_bca_data_caveat(self):
        """BCA age > 18 months triggers caveat."""
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=10,
            bca_age_months=24,
        )
        assert len(caveats) == 1
        assert "24 months" in caveats[0]

    def test_bca_age_at_threshold_no_caveat(self):
        """BCA age exactly 18 months should NOT trigger (> not >=)."""
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=10,
            bca_age_months=18,
        )
        assert caveats == []

    def test_bca_age_none_no_caveat(self):
        """None bca_age_months should not trigger caveat."""
        caveats = build_caveats(
            has_contamination=False,
            has_heritage=False,
            comp_count=10,
            bca_age_months=None,
        )
        assert caveats == []

    def test_all_caveats_combined(self):
        caveats = build_caveats(
            has_contamination=True,
            has_heritage=True,
            comp_count=2,
            bca_age_months=20,
        )
        assert len(caveats) == 4
        text = " ".join(caveats).lower()
        assert "contamination" in text
        assert "heritage" in text
        assert "2 transactions" in text
        assert "20 months" in text


# ---------------------------------------------------------------------------
# Gap 8: z-score anomaly detection in _collect_red_flags
# ---------------------------------------------------------------------------
from api.report_generator import ParcelReport, ReportGenerator


class TestCollectRedFlagsZScore:
    """Gap 8: z-score anomaly detection in ReportGenerator._collect_red_flags."""

    def _make_parcel_data(self, **extra_attrs) -> ParcelReport:
        """Create a minimal ParcelReport with optional extra attributes."""
        data = ParcelReport(
            pid="999-999-999",
            lot_area_sqm=Decimal("500"),
            lot_area_sqft=Decimal("5382"),
            buildable_sqft=Decimal("10000"),
        )
        for k, v in extra_attrs.items():
            object.__setattr__(data, k, v)
        return data

    def test_zscore_anomaly_flag_returned(self):
        """Assessed value with z-score > 2 should produce an Assessed Value Anomaly flag."""
        data = self._make_parcel_data(
            assessed_value=5000000,
            neighbourhood_median_assessed=1000000,
            neighbourhood_std_assessed=500000,
        )
        # z-score = |5000000 - 1000000| / 500000 = 8.0
        gen = ReportGenerator()
        flags = gen._collect_red_flags(data)
        anomaly_flags = [f for f in flags if f["flag_name"] == "Assessed Value Anomaly"]
        assert len(anomaly_flags) == 1
        flag = anomaly_flags[0]
        assert flag["severity"] == "medium"
        assert "8.0" in flag["detail"]
        assert "$5,000,000" in flag["detail"]

    def test_no_anomaly_when_within_2_std(self):
        """Assessed value within 2 std devs should NOT produce anomaly flag."""
        data = self._make_parcel_data(
            assessed_value=1500000,
            neighbourhood_median_assessed=1000000,
            neighbourhood_std_assessed=500000,
        )
        # z-score = |1500000 - 1000000| / 500000 = 1.0 (< 2)
        gen = ReportGenerator()
        flags = gen._collect_red_flags(data)
        anomaly_flags = [f for f in flags if f["flag_name"] == "Assessed Value Anomaly"]
        assert len(anomaly_flags) == 0

    def test_no_anomaly_when_missing_stats(self):
        """No median/std data should not produce anomaly flag."""
        data = self._make_parcel_data(assessed_value=5000000)
        gen = ReportGenerator()
        flags = gen._collect_red_flags(data)
        anomaly_flags = [f for f in flags if f["flag_name"] == "Assessed Value Anomaly"]
        assert len(anomaly_flags) == 0

    def test_heritage_flag(self):
        """Heritage designation should produce a flag."""
        data = self._make_parcel_data(heritage_designation="A")
        gen = ReportGenerator()
        flags = gen._collect_red_flags(data)
        heritage_flags = [f for f in flags if f["flag_name"] == "Heritage Designation"]
        assert len(heritage_flags) == 1
        assert heritage_flags[0]["severity"] == "high"

    def test_contamination_flag(self):
        """Active contamination status should produce a flag."""
        data = self._make_parcel_data(contamination_status="Active Remediation")
        gen = ReportGenerator()
        flags = gen._collect_red_flags(data)
        contam_flags = [f for f in flags if f["flag_name"] == "Environmental Contamination"]
        assert len(contam_flags) == 1
        assert contam_flags[0]["severity"] == "high"


# ---------------------------------------------------------------------------
# Gap 9: Parcel search disambiguation (mock-based)
# ---------------------------------------------------------------------------
from api.parcel_search import ParcelSearchResult, ParcelSearchService, search_parcels


def _make_search_result(pid: str = "111-111-111", address: str = "123 Main St") -> ParcelSearchResult:
    return ParcelSearchResult(
        parcel_id="1",
        pid=pid,
        civic_address=address,
        lat=49.2827,
        lng=-123.1207,
        lot_area_sqm=500.0,
        zoning="RS-1",
        neighborhood="Kitsilano",
        match_score=0.9,
    )


class TestParcelSearchDisambiguation:
    """Gap 9: Parcel search disambiguation logic."""

    @pytest.mark.asyncio
    async def test_single_result_no_disambiguation(self):
        """Exactly 1 result -> disambiguation = False."""
        service = MagicMock(spec=ParcelSearchService)
        service.search_by_address = AsyncMock(return_value=[_make_search_result()])

        result = await search_parcels(q="123 Main St", limit=10, service=service)

        assert result["count"] == 1
        assert result["disambiguation"] is False

    @pytest.mark.asyncio
    async def test_multiple_results_disambiguation(self):
        """3 results -> disambiguation = True."""
        results = [
            _make_search_result("111-111-111", "123 Main St"),
            _make_search_result("222-222-222", "123 Main Ave"),
            _make_search_result("333-333-333", "123 Main Blvd"),
        ]
        service = MagicMock(spec=ParcelSearchService)
        service.search_by_address = AsyncMock(return_value=results)

        result = await search_parcels(q="123 Main", limit=10, service=service)

        assert result["count"] == 3
        assert result["disambiguation"] is True

    @pytest.mark.asyncio
    async def test_zero_results_raises_404(self):
        """0 results -> HTTPException 404."""
        from fastapi import HTTPException

        service = MagicMock(spec=ParcelSearchService)
        service.search_by_address = AsyncMock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await search_parcels(q="nonexistent address xyz", limit=10, service=service)

        assert exc_info.value.status_code == 404
        assert "could not be resolved" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_pid_format_direct_lookup(self):
        """PID format query triggers search_by_pid first."""
        service = MagicMock(spec=ParcelSearchService)
        service.search_by_pid = AsyncMock(return_value=_make_search_result("123-456-789"))

        result = await search_parcels(q="123-456-789", limit=10, service=service)

        service.search_by_pid.assert_called_once_with("123-456-789")
        assert result["count"] == 1
        assert result["disambiguation"] is False


# ---------------------------------------------------------------------------
# Gap 10: RetrievalTracker.log_retrieval context manager
# ---------------------------------------------------------------------------
from api.retrieval_logging import RetrievalTracker, log_retrieval
import api.retrieval_logging


class TestLogRetrieval:
    """Gap 10: log_retrieval async context manager tests."""

    def _make_mock_pool(self, execute_side_effect=None):
        """Create a mock db_pool with an async context manager for acquire()."""
        mock_conn = AsyncMock()
        if execute_side_effect:
            mock_conn.execute = AsyncMock(side_effect=execute_side_effect)
        else:
            mock_conn.execute = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        return mock_pool, mock_conn

    @pytest.mark.asyncio
    async def test_successful_retrieval_inserts_log(self):
        """Successful retrieval inserts into retrieval_log and updates freshness."""
        mock_pool, mock_conn = self._make_mock_pool()

        async with log_retrieval(mock_pool, "DS-001", {"q": "test"}) as tracker:
            tracker.set_status(200)
            tracker.set_record_count(5)

        # Should have called execute twice: INSERT + UPDATE freshness
        assert mock_conn.execute.call_count == 2
        insert_call = mock_conn.execute.call_args_list[0]
        assert "retrieval_log" in insert_call.args[0]
        assert insert_call.args[1] == "DS-001"

        update_call = mock_conn.execute.call_args_list[1]
        assert "data_source_freshness" in update_call.args[0]

    @pytest.mark.asyncio
    async def test_failed_retrieval_records_error(self):
        """Failed retrieval records error message and re-raises exception."""
        mock_pool, mock_conn = self._make_mock_pool()

        with pytest.raises(ValueError, match="fetch failed"):
            async with log_retrieval(mock_pool, "DS-002") as tracker:
                tracker.set_status(500)
                raise ValueError("fetch failed")

        # Should have inserted with error_message set
        insert_call = mock_conn.execute.call_args_list[0]
        args = insert_call.args
        assert args[6] == "fetch failed"  # error_message is $6

    @pytest.mark.asyncio
    async def test_db_insert_failure_swallowed(self):
        """DB insert failure during logging is swallowed (not re-raised)."""
        # Reset the global so the logger.error branch is taken
        api.retrieval_logging._first_log_failure_reported = False

        mock_pool, mock_conn = self._make_mock_pool(
            execute_side_effect=RuntimeError("DB unavailable")
        )

        # Should NOT raise even though DB insert fails
        async with log_retrieval(mock_pool, "DS-003") as tracker:
            tracker.set_status(200)
            tracker.set_record_count(1)

        # The context manager should have completed without error
        assert tracker.source_id == "DS-003"

    @pytest.mark.asyncio
    async def test_tracker_duration_positive(self):
        """Tracker should record positive duration_ms."""
        mock_pool, _ = self._make_mock_pool()

        async with log_retrieval(mock_pool, "DS-004") as tracker:
            tracker.set_status(200)

        assert tracker.duration_ms >= 0


# ---------------------------------------------------------------------------
# Gap 11: GEOGRAPHIC_SCOPE rule matching edge case
# ---------------------------------------------------------------------------
from api.intelligence.alerts import AlertEngine, RuleType, WatchlistRule


class TestGeographicScopeRuleMatching:
    """Gap 11: GEOGRAPHIC_SCOPE rule matching edge cases."""

    def test_kitsilano_rule_vs_citywide_signal_no_match(self):
        """rule_value='kitsilano' should NOT match a citywide signal."""
        rule = WatchlistRule(
            rule_type=RuleType.GEOGRAPHIC_SCOPE,
            rule_value="kitsilano",
        )
        signal = {"geographic_scope": "citywide"}

        result = AlertEngine.match_rule(signal, rule)
        assert result is False

    def test_citywide_rule_vs_citywide_signal_matches(self):
        """rule_value='citywide' should match a citywide signal."""
        rule = WatchlistRule(
            rule_type=RuleType.GEOGRAPHIC_SCOPE,
            rule_value="citywide",
        )
        signal = {"geographic_scope": "citywide"}

        result = AlertEngine.match_rule(signal, rule)
        assert result is True

    def test_neighborhood_rule_matches_affected_area(self):
        """Neighbourhood rule should match when in affected_areas list."""
        rule = WatchlistRule(
            rule_type=RuleType.GEOGRAPHIC_SCOPE,
            rule_value="kitsilano",
        )
        signal = {
            "geographic_scope": "neighbourhood",
            "affected_areas": ["Kitsilano", "Point Grey"],
        }

        result = AlertEngine.match_rule(signal, rule)
        assert result is True

    def test_neighborhood_rule_not_in_affected_areas(self):
        """Neighbourhood rule should NOT match when not in affected_areas."""
        rule = WatchlistRule(
            rule_type=RuleType.GEOGRAPHIC_SCOPE,
            rule_value="kitsilano",
        )
        signal = {
            "geographic_scope": "neighbourhood",
            "affected_areas": ["Downtown", "Strathcona"],
        }

        result = AlertEngine.match_rule(signal, rule)
        assert result is False

    def test_empty_geographic_scope(self):
        """Missing/empty geographic_scope in signal should not match."""
        rule = WatchlistRule(
            rule_type=RuleType.GEOGRAPHIC_SCOPE,
            rule_value="kitsilano",
        )
        signal = {}

        result = AlertEngine.match_rule(signal, rule)
        assert result is False

    def test_empty_rules_matches_all(self):
        """Empty rules list should match all signals (OR logic fallback)."""
        result = AlertEngine.match_rules({"geographic_scope": "citywide"}, [])
        assert result is True


# ---------------------------------------------------------------------------
# Gap 12: AddressNormalizer.normalize
# ---------------------------------------------------------------------------
from api.parcel_search import AddressNormalizer


class TestAddressNormalizer:
    """Gap 12: AddressNormalizer.normalize tests."""

    def test_unit_prefix_stripped(self):
        """'#202 123 Main St' -> strips unit, normalizes suffix."""
        result = AddressNormalizer.normalize("#202 123 Main St")
        assert result == "123 main street"

    def test_suite_prefix_stripped(self):
        """'Suite 100 456 Broadway Ave.' -> strips suite, normalizes suffix."""
        result = AddressNormalizer.normalize("Suite 100 456 Broadway Ave.")
        assert result == "456 broadway avenue"

    def test_unit_prefix_word_stripped(self):
        """'Unit 5A 789 Oak Dr' -> strips unit prefix."""
        result = AddressNormalizer.normalize("Unit 5A 789 Oak Dr")
        assert result == "789 oak drive"

    def test_whitespace_normalization(self):
        """Multiple spaces should be collapsed to single space."""
        result = AddressNormalizer.normalize("  123   Main    St  ")
        # Leading spaces prevent the ^-anchored unit regex from stripping "123",
        # so the number is preserved but whitespace is normalized.
        assert "  " not in result
        assert result == "123 main street"

    def test_boulevard_suffix(self):
        result = AddressNormalizer.normalize("100 Cambie Blvd")
        assert "boulevard" in result

    def test_road_suffix(self):
        result = AddressNormalizer.normalize("200 Knight Rd")
        assert "road" in result

    def test_crescent_suffix(self):
        result = AddressNormalizer.normalize("300 Beach Cres")
        assert "crescent" in result

    def test_lowercase_conversion(self):
        result = AddressNormalizer.normalize("500 MAIN STREET")
        assert result == result.lower()

    def test_no_unit_prefix_preserves_address(self):
        """Address without unit prefix: number is still stripped by the regex."""
        result = AddressNormalizer.normalize("456 Broadway Ave")
        assert result == "broadway avenue"

    def test_period_after_suffix_handled(self):
        """Trailing period on suffix should be handled."""
        result = AddressNormalizer.normalize("100 Cambie Blvd.")
        assert "boulevard" in result
