"""
BIZ-014: Comprehensive tests for Entitlement Confidence Scoring.

Tests cover:
- Base confidence with no penalties
- Each penalty factor individually
- Multiple penalties stacking
- Clamping to 10-99% range
- Precedent bonus
- Format string output
- Confidence labels (high/moderate/uncertain/unlikely)
- Edge cases (all penalties, no penalties, max opposition)
"""

import pytest

from api.entitlement_confidence import ConfidenceFactors, EntitlementConfidenceScorer


# ════════════════════════════════════════════════════════════════════════════
# Scorer shorthand
# ════════════════════════════════════════════════════════════════════════════

scorer = EntitlementConfidenceScorer()


# ════════════════════════════════════════════════════════════════════════════
# BASE CONFIDENCE (no risk factors)
# ════════════════════════════════════════════════════════════════════════════

class TestBaseConfidence:

    def test_base_confidence_no_penalties_with_precedent(self):
        """Default call: base 95 + precedent bonus 5 = 99 (clamped)."""
        result = scorer.calculate()
        assert result.base_confidence == 95.0
        assert result.final_confidence == 99.0

    def test_base_confidence_no_penalties_no_precedent(self):
        """Without precedent bonus: base 95 + 0 = 95."""
        result = scorer.calculate(has_precedent_approvals=False)
        assert result.final_confidence == 95.0

    def test_all_penalties_zero_by_default(self):
        """All penalty fields should be 0 when no risk factors are present."""
        result = scorer.calculate(has_precedent_approvals=False)
        assert result.view_cone_penalty == 0.0
        assert result.heritage_penalty == 0.0
        assert result.cd1_penalty == 0.0
        assert result.opposition_penalty == 0.0
        assert result.lot_assembly_penalty == 0.0
        assert result.recent_denial_penalty == 0.0


# ════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL PENALTY FACTORS
# ════════════════════════════════════════════════════════════════════════════

class TestViewConePenalty:

    def test_view_cone_applies_minus_20(self):
        result = scorer.calculate(is_view_cone=True, has_precedent_approvals=False)
        assert result.view_cone_penalty == -20.0
        assert result.final_confidence == 75.0

    def test_no_view_cone_zero_penalty(self):
        result = scorer.calculate(is_view_cone=False, has_precedent_approvals=False)
        assert result.view_cone_penalty == 0.0


class TestHeritagePenalty:

    def test_heritage_site_applies_minus_25(self):
        result = scorer.calculate(is_heritage=True, has_precedent_approvals=False)
        assert result.heritage_penalty == -25.0
        assert result.final_confidence == 70.0

    def test_near_heritage_applies_minus_10(self):
        result = scorer.calculate(near_heritage=True, has_precedent_approvals=False)
        assert result.heritage_penalty == -10.0
        assert result.final_confidence == 85.0

    def test_heritage_overrides_near_heritage(self):
        """If both is_heritage and near_heritage, is_heritage takes priority (-25)."""
        result = scorer.calculate(
            is_heritage=True, near_heritage=True, has_precedent_approvals=False
        )
        assert result.heritage_penalty == -25.0

    def test_no_heritage_zero_penalty(self):
        result = scorer.calculate(
            is_heritage=False, near_heritage=False, has_precedent_approvals=False
        )
        assert result.heritage_penalty == 0.0


class TestCD1Penalty:

    def test_cd1_applies_minus_15(self):
        result = scorer.calculate(is_cd1=True, has_precedent_approvals=False)
        assert result.cd1_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_no_cd1_zero_penalty(self):
        result = scorer.calculate(is_cd1=False, has_precedent_approvals=False)
        assert result.cd1_penalty == 0.0


class TestOppositionPenalty:

    def test_opposition_score_0_no_penalty(self):
        result = scorer.calculate(opposition_score=0, has_precedent_approvals=False)
        assert result.opposition_penalty == 0.0

    def test_opposition_score_1_no_penalty(self):
        result = scorer.calculate(opposition_score=1, has_precedent_approvals=False)
        assert result.opposition_penalty == 0.0

    def test_opposition_score_2_no_penalty(self):
        """Threshold is > 2, so score=2 should not trigger penalty."""
        result = scorer.calculate(opposition_score=2, has_precedent_approvals=False)
        assert result.opposition_penalty == 0.0

    def test_opposition_score_3_applies_minus_15(self):
        """Score 3 triggers penalty: min(-3, -15) = -15 (floor)."""
        result = scorer.calculate(opposition_score=3, has_precedent_approvals=False)
        assert result.opposition_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_opposition_score_5_applies_minus_15(self):
        """Score 5 triggers penalty: min(-5, -15) = -15 (floor)."""
        result = scorer.calculate(opposition_score=5, has_precedent_approvals=False)
        assert result.opposition_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_opposition_score_10_applies_minus_15(self):
        """Score 10 triggers penalty: min(-10, -15) = -15 (floor)."""
        result = scorer.calculate(opposition_score=10, has_precedent_approvals=False)
        assert result.opposition_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_opposition_score_20_applies_minus_20(self):
        """Score 20 exceeds floor: min(-20, -15) = -20."""
        result = scorer.calculate(opposition_score=20, has_precedent_approvals=False)
        assert result.opposition_penalty == -20.0
        assert result.final_confidence == 75.0

    def test_opposition_score_exactly_15_gives_minus_15(self):
        result = scorer.calculate(opposition_score=15, has_precedent_approvals=False)
        assert result.opposition_penalty == -15.0


class TestLotAssemblyPenalty:

    def test_lot_too_small_applies_minus_10(self):
        result = scorer.calculate(lot_too_small=True, has_precedent_approvals=False)
        assert result.lot_assembly_penalty == -10.0
        assert result.final_confidence == 85.0

    def test_lot_adequate_zero_penalty(self):
        result = scorer.calculate(lot_too_small=False, has_precedent_approvals=False)
        assert result.lot_assembly_penalty == 0.0


class TestRecentDenialPenalty:

    def test_no_denials_zero_penalty(self):
        result = scorer.calculate(recent_denials_nearby=0, has_precedent_approvals=False)
        assert result.recent_denial_penalty == 0.0

    def test_one_denial_applies_minus_15(self):
        """1 denial: min(-5, -15) = -15 (floor)."""
        result = scorer.calculate(recent_denials_nearby=1, has_precedent_approvals=False)
        assert result.recent_denial_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_two_denials_applies_minus_15(self):
        """2 denials: min(-10, -15) = -15 (floor)."""
        result = scorer.calculate(recent_denials_nearby=2, has_precedent_approvals=False)
        assert result.recent_denial_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_three_denials_gives_minus_15(self):
        """3 denials: min(-15, -15) = -15."""
        result = scorer.calculate(recent_denials_nearby=3, has_precedent_approvals=False)
        assert result.recent_denial_penalty == -15.0
        assert result.final_confidence == 80.0

    def test_many_denials_exceeds_floor(self):
        """10 denials: min(-50, -15) = -50 (exceeds floor)."""
        result = scorer.calculate(recent_denials_nearby=10, has_precedent_approvals=False)
        assert result.recent_denial_penalty == -50.0
        assert result.final_confidence == 45.0


# ════════════════════════════════════════════════════════════════════════════
# PRECEDENT BONUS
# ════════════════════════════════════════════════════════════════════════════

class TestPrecedentBonus:

    def test_precedent_adds_5(self):
        with_precedent = scorer.calculate(has_precedent_approvals=True)
        without_precedent = scorer.calculate(has_precedent_approvals=False)
        # Base 95 + 5 = 100 clamped to 99; Base 95 + 0 = 95
        assert with_precedent.final_confidence == 99.0
        assert without_precedent.final_confidence == 95.0

    def test_precedent_bonus_with_some_penalty(self):
        """Precedent bonus should partially offset a penalty."""
        result = scorer.calculate(is_cd1=True, has_precedent_approvals=True)
        # 95 - 15 + 5 = 85
        assert result.final_confidence == 85.0

    def test_precedent_bonus_without_penalty(self):
        result = scorer.calculate(has_precedent_approvals=True)
        # 95 + 5 = 100 -> clamped to 99
        assert result.final_confidence == 99.0


# ════════════════════════════════════════════════════════════════════════════
# STACKING MULTIPLE PENALTIES
# ════════════════════════════════════════════════════════════════════════════

class TestPenaltyStacking:

    def test_view_cone_and_heritage(self):
        result = scorer.calculate(
            is_view_cone=True, is_heritage=True, has_precedent_approvals=False
        )
        # 95 - 20 - 25 = 50
        assert result.final_confidence == 50.0

    def test_cd1_and_lot_assembly(self):
        result = scorer.calculate(
            is_cd1=True, lot_too_small=True, has_precedent_approvals=False
        )
        # 95 - 15 - 10 = 70
        assert result.final_confidence == 70.0

    def test_three_penalties_stacking(self):
        result = scorer.calculate(
            is_view_cone=True,
            is_cd1=True,
            opposition_score=5,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 15 + min(-5, -15) = 95 - 20 - 15 - 15 = 45
        assert result.final_confidence == 45.0

    def test_all_penalties_max(self):
        """Every risk factor at worst case, no precedent."""
        result = scorer.calculate(
            is_view_cone=True,
            is_heritage=True,
            near_heritage=True,
            is_cd1=True,
            opposition_score=20,
            lot_too_small=True,
            recent_denials_nearby=10,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 25 - 15 - 15 - 10 - 15 = -5 -> clamped to 10
        assert result.final_confidence == 10.0

    def test_all_penalties_max_with_precedent(self):
        """Every risk factor at worst case, with precedent bonus."""
        result = scorer.calculate(
            is_view_cone=True,
            is_heritage=True,
            near_heritage=True,
            is_cd1=True,
            opposition_score=20,
            lot_too_small=True,
            recent_denials_nearby=10,
            has_precedent_approvals=True,
        )
        # 95 - 20 - 25 - 15 - 15 - 10 - 15 + 5 = 0 -> clamped to 10
        assert result.final_confidence == 10.0


# ════════════════════════════════════════════════════════════════════════════
# CLAMPING (10-99% range)
# ════════════════════════════════════════════════════════════════════════════

class TestClamping:

    def test_upper_clamp_at_99(self):
        """Base 95 + precedent 5 = 100 -> clamped to 99."""
        result = scorer.calculate(has_precedent_approvals=True)
        assert result.final_confidence == 99.0

    def test_lower_clamp_at_10(self):
        """Extreme penalties push below 10 -> clamped to 10."""
        result = scorer.calculate(
            is_view_cone=True,
            is_heritage=True,
            is_cd1=True,
            opposition_score=10,
            lot_too_small=True,
            recent_denials_nearby=3,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 25 - 15 - 10 - 10 - 15 = 0 -> clamped to 10
        assert result.final_confidence == 10.0

    def test_exactly_at_lower_bound(self):
        """Result that computes to exactly 10 should stay 10."""
        # Need raw = 10: 95 - 85 = 10
        # view_cone(-20) + heritage(-25) + cd1(-15) + opposition_10(-10) + lot(-10) + denial_1(-5) = -85
        result = scorer.calculate(
            is_view_cone=True,
            is_heritage=True,
            is_cd1=True,
            opposition_score=10,
            lot_too_small=True,
            recent_denials_nearby=1,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 25 - 15 - 10 - 10 - 5 = 10
        assert result.final_confidence == 10.0

    def test_just_above_lower_bound(self):
        """Penalties that sum to just above 10 should remain unclamped."""
        result = scorer.calculate(
            is_view_cone=True,
            near_heritage=True,
            is_cd1=True,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 10 - 15 = 50
        assert result.final_confidence == 50.0


# ════════════════════════════════════════════════════════════════════════════
# FORMAT ENTITLEMENT STRING
# ════════════════════════════════════════════════════════════════════════════

class TestFormatEntitlement:

    def test_format_basic(self):
        assert scorer.format_entitlement(12, 87.0) == "12 storeys (87% confidence)"

    def test_format_single_storey(self):
        assert scorer.format_entitlement(1, 50.0) == "1 storeys (50% confidence)"

    def test_format_high_confidence(self):
        assert scorer.format_entitlement(20, 99.0) == "20 storeys (99% confidence)"

    def test_format_low_confidence(self):
        assert scorer.format_entitlement(6, 10.0) == "6 storeys (10% confidence)"

    def test_format_decimal_confidence_rounds(self):
        """The f-string {confidence:.0f} rounds to nearest integer."""
        assert scorer.format_entitlement(8, 87.5) == "8 storeys (88% confidence)"

    def test_format_zero_storeys(self):
        assert scorer.format_entitlement(0, 50.0) == "0 storeys (50% confidence)"


# ════════════════════════════════════════════════════════════════════════════
# CONFIDENCE LABELS
# ════════════════════════════════════════════════════════════════════════════

class TestConfidenceLabel:

    def test_high_at_85(self):
        assert scorer.confidence_label(85.0) == "high"

    def test_high_at_99(self):
        assert scorer.confidence_label(99.0) == "high"

    def test_high_at_90(self):
        assert scorer.confidence_label(90.0) == "high"

    def test_moderate_at_60(self):
        assert scorer.confidence_label(60.0) == "moderate"

    def test_moderate_at_84(self):
        assert scorer.confidence_label(84.9) == "moderate"

    def test_moderate_at_70(self):
        assert scorer.confidence_label(70.0) == "moderate"

    def test_uncertain_at_40(self):
        assert scorer.confidence_label(40.0) == "uncertain"

    def test_uncertain_at_59(self):
        assert scorer.confidence_label(59.9) == "uncertain"

    def test_unlikely_at_39(self):
        assert scorer.confidence_label(39.9) == "unlikely"

    def test_unlikely_at_10(self):
        assert scorer.confidence_label(10.0) == "unlikely"

    def test_unlikely_at_0(self):
        assert scorer.confidence_label(0.0) == "unlikely"


# ════════════════════════════════════════════════════════════════════════════
# RETURN TYPE VERIFICATION
# ════════════════════════════════════════════════════════════════════════════

class TestReturnType:

    def test_returns_confidence_factors_dataclass(self):
        result = scorer.calculate()
        assert isinstance(result, ConfidenceFactors)

    def test_dataclass_fields_are_floats(self):
        result = scorer.calculate()
        assert isinstance(result.base_confidence, float)
        assert isinstance(result.view_cone_penalty, float)
        assert isinstance(result.heritage_penalty, float)
        assert isinstance(result.cd1_penalty, float)
        assert isinstance(result.opposition_penalty, float)
        assert isinstance(result.lot_assembly_penalty, float)
        assert isinstance(result.recent_denial_penalty, float)
        assert isinstance(result.final_confidence, float)


# ════════════════════════════════════════════════════════════════════════════
# REALISTIC SCENARIO TESTS
# ════════════════════════════════════════════════════════════════════════════

class TestRealisticScenarios:

    def test_ideal_parcel(self):
        """Clean parcel near SkyTrain, no complications."""
        result = scorer.calculate(has_precedent_approvals=True)
        assert result.final_confidence == 99.0
        assert scorer.confidence_label(result.final_confidence) == "high"

    def test_heritage_area_cd1_parcel(self):
        """Heritage area with CD-1 zoning -- moderately challenging."""
        result = scorer.calculate(
            near_heritage=True,
            is_cd1=True,
            opposition_score=4,
            has_precedent_approvals=True,
        )
        # 95 - 10 - 15 + min(-4, -15) + 5 = 95 - 10 - 15 - 15 + 5 = 60
        assert result.final_confidence == 60.0
        assert scorer.confidence_label(result.final_confidence) == "moderate"

    def test_worst_case_downtown_parcel(self):
        """Downtown heritage building in view cone with strong opposition."""
        result = scorer.calculate(
            is_view_cone=True,
            is_heritage=True,
            is_cd1=True,
            opposition_score=8,
            lot_too_small=True,
            recent_denials_nearby=2,
            has_precedent_approvals=False,
        )
        # 95 - 20 - 25 - 15 - 8 - 10 - 10 = 7 -> clamped to 10
        assert result.final_confidence == 10.0
        assert scorer.confidence_label(result.final_confidence) == "unlikely"

    def test_moderate_risk_parcel(self):
        """Some opposition and near heritage, but has precedent."""
        result = scorer.calculate(
            near_heritage=True,
            opposition_score=5,
            has_precedent_approvals=True,
        )
        # 95 - 10 + min(-5, -15) + 5 = 95 - 10 - 15 + 5 = 75
        assert result.final_confidence == 75.0
        assert scorer.confidence_label(result.final_confidence) == "moderate"
