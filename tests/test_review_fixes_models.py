"""
Tests for review-fix model changes:
- SetbackInfo, Bill44Info, CommunityPlanInfo sub-models
- Narrowed heritage_category (Literal["A", "B", "C"])
- Narrowed deal_grade (Literal["A", "B", "C", "D", "F"])
- ParcelEntitlementResponse accepts new sub-model types (and raw dicts via coercion)

Note: market_data_date remains Optional[str] because the codebase uses non-ISO
date strings like "2025-Q4" which cannot be parsed as date objects.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.models import (
    Bill44Info,
    CommunityPlanInfo,
    DealValidation,
    ParcelEntitlementResponse,
    SetbackInfo,
)


# ════════════════════════════════════════════════════════════════════════════
# SetbackInfo
# ════════════════════════════════════════════════════════════════════════════


class TestSetbackInfo:
    """SetbackInfo sub-model tests."""

    def test_accepts_full_dict(self):
        """SetbackInfo can be created from a dict with all known fields."""
        data = {
            "front_m": 3.0,
            "rear_m": 7.5,
            "side_m": 1.2,
            "site_coverage_pct": 60.0,
        }
        info = SetbackInfo(**data)
        assert info.front_m == Decimal("3.0")
        assert info.rear_m == Decimal("7.5")
        assert info.side_m == Decimal("1.2")
        assert info.site_coverage_pct == Decimal("60.0")

    def test_accepts_partial_dict(self):
        """SetbackInfo allows partial data — missing fields default to None."""
        info = SetbackInfo(front_m=3.0)
        assert info.front_m == Decimal("3.0")
        assert info.rear_m is None
        assert info.side_m is None
        assert info.site_coverage_pct is None

    def test_accepts_empty(self):
        """SetbackInfo can be created with no fields at all."""
        info = SetbackInfo()
        assert info.front_m is None
        assert info.rear_m is None


# ════════════════════════════════════════════════════════════════════════════
# Bill44Info
# ════════════════════════════════════════════════════════════════════════════


class TestBill44Info:
    """Bill44Info sub-model tests."""

    def test_accepts_full_dict(self):
        """Bill44Info can be created from a dict with all known fields."""
        data = {
            "eligible": True,
            "max_units": 6,
            "transit_bonus": True,
            "description": "Eligible for SSMUH under Bill 44",
        }
        info = Bill44Info(**data)
        assert info.eligible is True
        assert info.max_units == 6
        assert info.transit_bonus is True
        assert info.description == "Eligible for SSMUH under Bill 44"

    def test_accepts_partial_dict(self):
        """Bill44Info allows partial data — missing fields default to None."""
        info = Bill44Info(eligible=False)
        assert info.eligible is False
        assert info.max_units is None
        assert info.transit_bonus is None
        assert info.description is None

    def test_accepts_empty(self):
        """Bill44Info can be created with no fields at all."""
        info = Bill44Info()
        assert info.eligible is None


# ════════════════════════════════════════════════════════════════════════════
# CommunityPlanInfo
# ════════════════════════════════════════════════════════════════════════════


class TestCommunityPlanInfo:
    """CommunityPlanInfo sub-model tests."""

    def test_accepts_full_dict(self):
        """CommunityPlanInfo can be created from a dict with all known fields."""
        data = {
            "plan_name": "Cambie Corridor Plan",
            "max_fsr": 4.5,
            "max_storeys": 18,
        }
        info = CommunityPlanInfo(**data)
        assert info.plan_name == "Cambie Corridor Plan"
        assert info.max_fsr == Decimal("4.5")
        assert info.max_storeys == 18

    def test_accepts_partial_dict(self):
        """CommunityPlanInfo allows partial data — missing fields default to None."""
        info = CommunityPlanInfo(plan_name="Broadway Plan")
        assert info.plan_name == "Broadway Plan"
        assert info.max_fsr is None
        assert info.max_storeys is None

    def test_accepts_empty(self):
        """CommunityPlanInfo can be created with no fields at all."""
        info = CommunityPlanInfo()
        assert info.plan_name is None


# ════════════════════════════════════════════════════════════════════════════
# heritage_category Literal narrowing
# ════════════════════════════════════════════════════════════════════════════


class TestHeritageCategory:
    """heritage_category Literal type narrowing tests."""

    @pytest.mark.parametrize("cat", ["A", "B", "C"])
    def test_accepts_valid_categories(self, cat):
        """heritage_category accepts 'A', 'B', 'C'."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            heritage_category=cat,
        )
        assert resp.heritage_category == cat

    def test_accepts_none(self):
        """heritage_category accepts None."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            heritage_category=None,
        )
        assert resp.heritage_category is None

    def test_rejects_invalid_category(self):
        """heritage_category rejects 'Z' (not in A/B/C)."""
        with pytest.raises(ValidationError) as exc_info:
            ParcelEntitlementResponse(
                pid="001-234-567",
                in_toa=False,
                heritage_category="Z",
            )
        errors = exc_info.value.errors()
        assert any("heritage_category" in str(e.get("loc", "")) for e in errors)

    def test_rejects_lowercase(self):
        """heritage_category rejects lowercase 'a' — must be uppercase."""
        with pytest.raises(ValidationError):
            ParcelEntitlementResponse(
                pid="001-234-567",
                in_toa=False,
                heritage_category="a",
            )


# ════════════════════════════════════════════════════════════════════════════
# deal_grade Literal narrowing
# ════════════════════════════════════════════════════════════════════════════


class TestDealGrade:
    """deal_grade Literal type narrowing tests."""

    @pytest.mark.parametrize("grade", ["A", "B", "C", "D", "F"])
    def test_accepts_valid_grades(self, grade):
        """deal_grade accepts A, B, C, D, F."""
        dv = DealValidation(
            deal_grade=grade,
            deal_score=50,
            confidence_level="medium",
            one_liner="Test",
        )
        assert dv.deal_grade == grade

    def test_rejects_invalid_grade(self):
        """deal_grade rejects 'G' (not in A/B/C/D/F)."""
        with pytest.raises(ValidationError) as exc_info:
            DealValidation(
                deal_grade="G",
                deal_score=50,
                confidence_level="medium",
                one_liner="Test",
            )
        errors = exc_info.value.errors()
        assert any("deal_grade" in str(e.get("loc", "")) for e in errors)

    def test_rejects_empty_string(self):
        """deal_grade rejects empty string."""
        with pytest.raises(ValidationError):
            DealValidation(
                deal_grade="",
                deal_score=50,
                confidence_level="medium",
                one_liner="Test",
            )



# ════════════════════════════════════════════════════════════════════════════
# ParcelEntitlementResponse with new sub-model types
# ════════════════════════════════════════════════════════════════════════════


class TestParcelEntitlementResponseSubModels:
    """ParcelEntitlementResponse integration with sub-model types."""

    def test_setbacks_as_sub_model(self):
        """ParcelEntitlementResponse accepts SetbackInfo instance."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            setbacks=SetbackInfo(front_m=3.0, rear_m=7.5),
        )
        assert isinstance(resp.setbacks, SetbackInfo)
        assert resp.setbacks.front_m == Decimal("3.0")

    def test_setbacks_as_dict_coerced(self):
        """ParcelEntitlementResponse coerces a raw dict to SetbackInfo (Pydantic v2)."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            setbacks={"front_m": 3.0, "rear_m": 7.5},
        )
        assert isinstance(resp.setbacks, SetbackInfo)
        assert resp.setbacks.front_m == Decimal("3.0")
        assert resp.setbacks.rear_m == Decimal("7.5")

    def test_bill44_as_dict_coerced(self):
        """ParcelEntitlementResponse coerces a raw dict to Bill44Info."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            bill44={"eligible": True, "max_units": 4, "transit_bonus": False},
        )
        assert isinstance(resp.bill44, Bill44Info)
        assert resp.bill44.eligible is True
        assert resp.bill44.max_units == 4

    def test_community_plan_as_dict_coerced(self):
        """ParcelEntitlementResponse coerces a raw dict to CommunityPlanInfo."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            community_plan={"plan_name": "Broadway Plan", "max_fsr": 5.0, "max_storeys": 20},
        )
        assert isinstance(resp.community_plan, CommunityPlanInfo)
        assert resp.community_plan.plan_name == "Broadway Plan"
        assert resp.community_plan.max_fsr == Decimal("5.0")

    def test_full_response_with_all_sub_models(self):
        """ParcelEntitlementResponse can be created with all new sub-model types populated."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=True,
            setbacks={"front_m": 3.0, "rear_m": 7.5, "side_m": 1.2, "site_coverage_pct": 60},
            bill44={"eligible": True, "max_units": 6, "transit_bonus": True, "description": "SSMUH"},
            community_plan={"plan_name": "Cambie Corridor", "max_fsr": 4.5, "max_storeys": 18},
            heritage_category="B",
            market_data_date="2025-01-15",
        )
        assert isinstance(resp.setbacks, SetbackInfo)
        assert isinstance(resp.bill44, Bill44Info)
        assert isinstance(resp.community_plan, CommunityPlanInfo)
        assert resp.heritage_category == "B"
        assert resp.market_data_date == "2025-01-15"

    def test_all_sub_models_none(self):
        """ParcelEntitlementResponse works with all sub-model fields as None."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            setbacks=None,
            bill44=None,
            community_plan=None,
            heritage_category=None,
            market_data_date=None,
        )
        assert resp.setbacks is None
        assert resp.bill44 is None
        assert resp.community_plan is None
        assert resp.heritage_category is None
        assert resp.market_data_date is None

    def test_partial_setback_dict_coerced(self):
        """Partial dict coerces to SetbackInfo with remaining fields as None."""
        resp = ParcelEntitlementResponse(
            pid="001-234-567",
            in_toa=False,
            setbacks={"front_m": 3.0},
        )
        assert isinstance(resp.setbacks, SetbackInfo)
        assert resp.setbacks.front_m == Decimal("3.0")
        assert resp.setbacks.rear_m is None
        assert resp.setbacks.side_m is None
        assert resp.setbacks.site_coverage_pct is None
