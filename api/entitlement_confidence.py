"""
VanCity Lens -- BIZ-014: Entitlement Confidence Scoring

Calculates the probability (0-100%) that a parcel will achieve its entitled
height/FSR under Bill 47, based on risk factors such as view cones, heritage
designation, CD-1 zoning, neighbourhood opposition, lot assembly requirements,
and recent denial history.
"""

from dataclasses import dataclass


@dataclass
class ConfidenceFactors:
    base_confidence: float  # Start at 95% (Bill 47 is by-right)
    view_cone_penalty: float  # -20% if in view cone
    heritage_penalty: float  # -25% if heritage site, -10% if near heritage
    cd1_penalty: float  # -15% if CD-1 zoning
    opposition_penalty: float  # -5% to -15% based on opposition score
    lot_assembly_penalty: float  # -10% if lot too small (assembly needed)
    recent_denial_penalty: float  # -10% if similar projects denied nearby
    final_confidence: float  # Clamped to 10-99%


class EntitlementConfidenceScorer:
    """Calculate confidence percentage for achieving entitled height."""

    @staticmethod
    def calculate(
        is_view_cone: bool = False,
        is_heritage: bool = False,
        near_heritage: bool = False,
        is_cd1: bool = False,
        opposition_score: int = 0,  # 0-10
        lot_too_small: bool = False,
        recent_denials_nearby: int = 0,
        has_precedent_approvals: bool = True,
    ) -> ConfidenceFactors:
        base = 95.0
        view_cone_penalty = -20.0 if is_view_cone else 0.0
        heritage_penalty = -25.0 if is_heritage else (-10.0 if near_heritage else 0.0)
        cd1_penalty = -15.0 if is_cd1 else 0.0
        opposition_penalty = min(-1.0 * opposition_score, -15.0) if opposition_score > 2 else 0.0
        lot_assembly_penalty = -10.0 if lot_too_small else 0.0
        recent_denial_penalty = min(-5.0 * recent_denials_nearby, -15.0) if recent_denials_nearby > 0 else 0.0

        precedent_bonus = 5.0 if has_precedent_approvals else 0.0

        raw = (
            base
            + view_cone_penalty
            + heritage_penalty
            + cd1_penalty
            + opposition_penalty
            + lot_assembly_penalty
            + recent_denial_penalty
            + precedent_bonus
        )
        final = max(10.0, min(99.0, raw))

        return ConfidenceFactors(
            base_confidence=base,
            view_cone_penalty=view_cone_penalty,
            heritage_penalty=heritage_penalty,
            cd1_penalty=cd1_penalty,
            opposition_penalty=opposition_penalty,
            lot_assembly_penalty=lot_assembly_penalty,
            recent_denial_penalty=recent_denial_penalty,
            final_confidence=round(final, 1),
        )

    @staticmethod
    def format_entitlement(storeys: int, confidence: float) -> str:
        """Format: '12 storeys (87% confidence)'"""
        return f"{storeys} storeys ({confidence:.0f}% confidence)"

    @staticmethod
    def confidence_label(confidence: float) -> str:
        if confidence >= 85:
            return "high"
        elif confidence >= 60:
            return "moderate"
        elif confidence >= 40:
            return "uncertain"
        else:
            return "unlikely"
