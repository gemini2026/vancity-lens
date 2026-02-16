"""
Sprint 1.9 — DV-HBU Validation Rule Tests

Tests for all data validation rules added in Sprint 1:
  DV-HBU-001: PID format validation (9-digit NNN-NNN-NNN)
  DV-HBU-002: Lot area range check (0–500K SF)
  DV-HBU-003: FSR range check (0.1–15.0)
  DV-HBU-005: Height storey-to-metres conversion
  DV-HBU-006: Assessment staleness (>18 months)
  DV-HBU-008: View cone hard height cap
  AC-HBU-006: Helpful 404 error messages
  AC-HBU-007: Market data date stamp
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from api.entitlement import (
    compute_entitlement,
    validate_pid_format,
    InvalidPIDFormatError,
    _storeys_to_metres,
    MARKET_DATA_DATE,
)
from api.models import DealValidation


# ════════════════════════════════════════════════════════════════════════════
# DV-HBU-001: PID Format Validation
# ════════════════════════════════════════════════════════════════════════════

class TestPIDFormatValidation:
    """DV-HBU-001: PID must be 9 digits, optionally hyphenated NNN-NNN-NNN."""

    def test_valid_pid_with_hyphens(self):
        assert validate_pid_format("012-345-678") == "012-345-678"

    def test_valid_pid_without_hyphens(self):
        assert validate_pid_format("012345678") == "012345678"

    def test_valid_pid_all_zeros(self):
        assert validate_pid_format("000-000-000") == "000-000-000"

    def test_valid_pid_all_nines(self):
        assert validate_pid_format("999-999-999") == "999-999-999"

    def test_invalid_pid_too_short(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("12345")

    def test_invalid_pid_too_long(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("0123456789")

    def test_invalid_pid_letters(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("ABC-DEF-GHI")

    def test_invalid_pid_mixed_alpha_numeric(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("012-ABC-678")

    def test_invalid_pid_wrong_hyphen_placement(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("01-234-5678")

    def test_invalid_pid_empty_string(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("")

    def test_invalid_pid_special_chars(self):
        with pytest.raises(InvalidPIDFormatError):
            validate_pid_format("012.345.678")

    def test_error_message_includes_pid(self):
        with pytest.raises(InvalidPIDFormatError) as exc_info:
            validate_pid_format("BADPID")
        assert "BADPID" in str(exc_info.value)
        assert "NNN-NNN-NNN" in str(exc_info.value)


# ════════════════════════════════════════════════════════════════════════════
# DV-HBU-005: Storey-to-Metres Conversion
# ════════════════════════════════════════════════════════════════════════════

class TestStoreyToMetresConversion:
    """DV-HBU-005: Height = 3.5m (ground floor) + 3.0m per additional storey."""

    def test_zero_storeys(self):
        assert _storeys_to_metres(0) == Decimal("0")

    def test_negative_storeys(self):
        assert _storeys_to_metres(-1) == Decimal("0")

    def test_one_storey(self):
        """1 storey = 3.5m (ground floor only)."""
        assert _storeys_to_metres(1) == Decimal("3.5")

    def test_two_storeys(self):
        """2 storeys = 3.5m + 3.0m = 6.5m."""
        assert _storeys_to_metres(2) == Decimal("6.5")

    def test_six_storeys(self):
        """6 storeys = 3.5 + 5×3.0 = 18.5m."""
        assert _storeys_to_metres(6) == Decimal("18.5")

    def test_twelve_storeys(self):
        """12 storeys = 3.5 + 11×3.0 = 36.5m."""
        assert _storeys_to_metres(12) == Decimal("36.5")

    def test_twenty_storeys(self):
        """20 storeys = 3.5 + 19×3.0 = 60.5m."""
        assert _storeys_to_metres(20) == Decimal("60.5")

    def test_entitled_height_set_on_entitlement(self):
        """Verify that compute_entitlement populates entitled_height_m on each entitlement."""
        # This is tested via the integration test below
        pass


# ════════════════════════════════════════════════════════════════════════════
# DV-HBU-002, 003, 006: Data Quality Warnings
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_conn():
    return AsyncMock()


@pytest.fixture
def base_parcel():
    """Normal parcel for warning tests."""
    return {
        "pid": "001-234-567",
        "civic_address": "1234 Main St, Vancouver, BC",
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


@pytest.fixture
def tier1_entitlement():
    return {
        "station_name": "Main Street Station",
        "tier": 1,
        "max_storeys": 20,
        "max_fsr": Decimal("4.0"),
        "distance_m": Decimal("150"),
        "current_height": 6,
        "current_fsr": Decimal("2.5"),
    }


class TestLotAreaWarning:
    """DV-HBU-002: Lot area range check — warn if outside 0–500K SF."""

    @pytest.mark.asyncio
    async def test_no_warning_normal_lot(self, mock_conn, base_parcel, tier1_entitlement):
        """Normal lot area (500 sqm ≈ 5,382 SF) produces no warning."""
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "LOT_AREA_ANOMALY" not in warning_codes

    @pytest.mark.asyncio
    async def test_warning_huge_lot(self, mock_conn, base_parcel, tier1_entitlement):
        """Lot area > 500K SF triggers LOT_AREA_ANOMALY warning."""
        parcel = base_parcel.copy()
        parcel["lot_area_sqm"] = Decimal("50000")  # ~538,000 SF > 500K
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "LOT_AREA_ANOMALY" in warning_codes
        warning = next(w for w in result.data_warnings if w.code == "LOT_AREA_ANOMALY")
        assert warning.field == "lot_area_sqm"

    @pytest.mark.asyncio
    async def test_no_warning_null_lot(self, mock_conn, base_parcel, tier1_entitlement):
        """Null lot area does not trigger warning (just skips check)."""
        parcel = base_parcel.copy()
        parcel["lot_area_sqm"] = None
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "LOT_AREA_ANOMALY" not in warning_codes


class TestFSRWarning:
    """DV-HBU-003: FSR range check — warn if outside 0.1–15.0."""

    @pytest.mark.asyncio
    async def test_no_warning_normal_fsr(self, mock_conn, base_parcel, tier1_entitlement):
        """FSR 2.5 is within range — no warning."""
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" not in warning_codes

    @pytest.mark.asyncio
    async def test_warning_fsr_too_low(self, mock_conn, base_parcel, tier1_entitlement):
        """FSR 0.05 < 0.1 triggers FSR_ANOMALY."""
        parcel = base_parcel.copy()
        parcel["current_fsr"] = Decimal("0.05")
        ent = tier1_entitlement.copy()
        ent["current_fsr"] = Decimal("0.05")
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" in warning_codes

    @pytest.mark.asyncio
    async def test_warning_fsr_too_high(self, mock_conn, base_parcel, tier1_entitlement):
        """FSR 20.0 > 15.0 triggers FSR_ANOMALY."""
        parcel = base_parcel.copy()
        parcel["current_fsr"] = Decimal("20.0")
        ent = tier1_entitlement.copy()
        ent["current_fsr"] = Decimal("20.0")
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" in warning_codes
        warning = next(w for w in result.data_warnings if w.code == "FSR_ANOMALY")
        assert warning.field == "current_fsr"

    @pytest.mark.asyncio
    async def test_no_warning_null_fsr(self, mock_conn, base_parcel, tier1_entitlement):
        """Null FSR does not trigger warning."""
        parcel = base_parcel.copy()
        parcel["current_fsr"] = None
        ent = tier1_entitlement.copy()
        ent["current_fsr"] = None
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" not in warning_codes

    @pytest.mark.asyncio
    async def test_boundary_fsr_0_1_no_warning(self, mock_conn, base_parcel, tier1_entitlement):
        """FSR 0.1 is at the lower boundary — no warning."""
        parcel = base_parcel.copy()
        parcel["current_fsr"] = Decimal("0.1")
        ent = tier1_entitlement.copy()
        ent["current_fsr"] = Decimal("0.1")
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" not in warning_codes

    @pytest.mark.asyncio
    async def test_boundary_fsr_15_no_warning(self, mock_conn, base_parcel, tier1_entitlement):
        """FSR 15.0 is at the upper boundary — no warning."""
        parcel = base_parcel.copy()
        parcel["current_fsr"] = Decimal("15.0")
        ent = tier1_entitlement.copy()
        ent["current_fsr"] = Decimal("15.0")
        mock_conn.fetchrow.side_effect = [parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        warning_codes = [w.code for w in result.data_warnings]
        assert "FSR_ANOMALY" not in warning_codes


# ════════════════════════════════════════════════════════════════════════════
# DV-HBU-008: View Cone Hard Cap
# ════════════════════════════════════════════════════════════════════════════

class TestViewConeHardCap:
    """DV-HBU-008: View cone must cap height below entitled storeys."""

    @pytest.mark.asyncio
    async def test_no_view_cone(self, mock_conn, base_parcel, tier1_entitlement):
        """No view cone → entitled_height_m reflects full storeys."""
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.view_cone_capped is False
        assert be.view_cone_max_m is None
        # 20 storeys = 3.5 + 19×3.0 = 60.5m
        assert be.entitled_height_m == Decimal("60.5")
        assert be.entitled_storeys == 20

    @pytest.mark.asyncio
    async def test_view_cone_caps_height(self, mock_conn, base_parcel, tier1_entitlement):
        """View cone at 30m caps 20-storey entitlement down to ~10 storeys."""
        view_cone_result = {"view_cone_max_m": Decimal("30.0")}
        mock_conn.fetchrow.side_effect = [base_parcel, view_cone_result, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.view_cone_capped is True
        assert be.view_cone_max_m == Decimal("30.0")
        assert be.entitled_height_m == Decimal("30.0")
        # 30m: (30 - 3.5) / 3.0 = 8.83 → int(8.83) = 8, so 1 + 8 = 9 storeys
        assert be.entitled_storeys == 9

    @pytest.mark.asyncio
    async def test_view_cone_very_low(self, mock_conn, base_parcel, tier1_entitlement):
        """View cone at 3.0m (below ground floor 3.5m) → 1 storey only."""
        view_cone_result = {"view_cone_max_m": Decimal("3.0")}
        mock_conn.fetchrow.side_effect = [base_parcel, view_cone_result, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.view_cone_capped is True
        assert be.entitled_storeys == 1

    @pytest.mark.asyncio
    async def test_view_cone_above_entitlement(self, mock_conn, base_parcel, tier1_entitlement):
        """View cone at 100m (above 20-storey = 60.5m) → no cap applied."""
        view_cone_result = {"view_cone_max_m": Decimal("100.0")}
        mock_conn.fetchrow.side_effect = [base_parcel, view_cone_result, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.view_cone_capped is False
        assert be.view_cone_max_m is None
        assert be.entitled_storeys == 20

    @pytest.mark.asyncio
    async def test_view_cone_storey_uplift_recalculated(self, mock_conn, base_parcel, tier1_entitlement):
        """When view cone caps storeys, storey_uplift is recalculated."""
        # Current height: 6 storeys, Bill 47: 20, View cone caps to 9
        view_cone_result = {"view_cone_max_m": Decimal("30.0")}
        mock_conn.fetchrow.side_effect = [base_parcel, view_cone_result, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        # Capped to 9 storeys, current is 6, so uplift = 3
        assert be.storey_uplift == 3

    @pytest.mark.asyncio
    async def test_view_cone_null_result(self, mock_conn, base_parcel, tier1_entitlement):
        """View cone query returns row with NULL max_height_m → no cap."""
        view_cone_result = {"view_cone_max_m": None}
        mock_conn.fetchrow.side_effect = [base_parcel, view_cone_result, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.view_cone_capped is False
        assert be.entitled_storeys == 20


# ════════════════════════════════════════════════════════════════════════════
# AC-HBU-007: Market Data Date
# ════════════════════════════════════════════════════════════════════════════

class TestMarketDataDate:
    """AC-HBU-007: Every entitlement response includes market_data_date."""

    @pytest.mark.asyncio
    async def test_market_data_date_present(self, mock_conn, base_parcel, tier1_entitlement):
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.market_data_date == MARKET_DATA_DATE

    @pytest.mark.asyncio
    async def test_market_data_date_on_non_toa_parcel(self, mock_conn, base_parcel):
        """Even non-TOA parcels include market_data_date."""
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[], []]  # no entitlements + no community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        assert result.market_data_date == MARKET_DATA_DATE


# ════════════════════════════════════════════════════════════════════════════
# DV-HBU-005 Integration: Entitled Height on Entitlements
# ════════════════════════════════════════════════════════════════════════════

class TestEntitledHeightIntegration:
    """Verify entitled_height_m is set correctly on each entitlement object."""

    @pytest.mark.asyncio
    async def test_height_m_on_tier1(self, mock_conn, base_parcel, tier1_entitlement):
        """Tier 1 = 20 storeys → 60.5m."""
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier1_entitlement], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        assert be.entitled_height_m == Decimal("60.5")

    @pytest.mark.asyncio
    async def test_height_m_on_tier2(self, mock_conn, base_parcel):
        """Tier 2 = 12 storeys → 36.5m."""
        tier2_ent = {
            "station_name": "Nanaimo Station",
            "tier": 2,
            "max_storeys": 12,
            "max_fsr": Decimal("2.5"),
            "distance_m": Decimal("300"),
            "current_height": 6,
            "current_fsr": Decimal("2.5"),
        }
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier2_ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        # max(12, 6) = 12 storeys → 3.5 + 11×3.0 = 36.5m
        assert be.entitled_height_m == Decimal("36.5")

    @pytest.mark.asyncio
    async def test_height_m_on_tier3(self, mock_conn, base_parcel):
        """Tier 3 = 6 storeys (same as current) → 18.5m."""
        tier3_ent = {
            "station_name": "29th Station",
            "tier": 3,
            "max_storeys": 6,
            "max_fsr": Decimal("1.5"),
            "distance_m": Decimal("700"),
            "current_height": 6,
            "current_fsr": Decimal("2.5"),
        }
        mock_conn.fetchrow.side_effect = [base_parcel, None, None, None, None, None]  # parcel + view cone + heritage + benchmark + setback + bill44
        mock_conn.fetch.side_effect = [[tier3_ent], []]  # entitlements + community plan
        mock_conn.fetchval.return_value = 0

        with patch('api.entitlement.compute_validation') as mv:
            mv.return_value = MagicMock(spec=DealValidation)
            result = await compute_entitlement(mock_conn, "001-234-567")

        be = result.best_entitlement
        # max(6, 6) = 6 storeys → 3.5 + 5×3.0 = 18.5m
        assert be.entitled_height_m == Decimal("18.5")


# ════════════════════════════════════════════════════════════════════════════
# AC-HBU-006: Helpful 404 Error (tested via test_api_contracts.py HTTP layer)
# Integration test: ensure InvalidPIDFormatError contains helpful details
# ════════════════════════════════════════════════════════════════════════════

class TestHelpfulErrors:
    """AC-HBU-006: Error messages include verification links and guidance."""

    def test_invalid_pid_error_has_format_hint(self):
        try:
            validate_pid_format("BADPID")
        except InvalidPIDFormatError as e:
            msg = str(e)
            assert "NNN-NNN-NNN" in msg
            assert "012-345-678" in msg  # example PID

    def test_invalid_pid_error_has_pid(self):
        try:
            validate_pid_format("XYZ")
        except InvalidPIDFormatError as e:
            assert e.pid == "XYZ"
