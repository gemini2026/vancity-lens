"""Neighborhood scoring engine for Madlan-style quality-of-life ratings.

Handles:
- Metric normalization (0-10 scale)
- Composite score computation (weighted average)
- Neighborhood ranking
- Trend detection
- Top/bottom category identification
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────

# Direction of each metric category: whether higher raw values mean better or worse
METRIC_DIRECTIONS: dict[str, str] = {
    "safety": "lower_is_better",       # Crime rate: lower = safer
    "schools": "higher_is_better",     # School quality: higher = better
    "transit": "higher_is_better",     # Transit density: more stops = better
    "parks": "higher_is_better",       # Green space: more = better
    "development": "higher_is_better", # Active development: more pipeline = better for investment
    "air_quality": "higher_is_better", # AQI reading: we invert during ingestion so higher = cleaner
    "affordability": "lower_is_better",# Price per sqft: lower = more affordable
    "walkability": "higher_is_better", # Walk score: higher = more walkable
}

# Default scoring weights (must sum to 1.0)
DEFAULT_WEIGHTS: dict[str, float] = {
    "safety": 0.15,
    "schools": 0.15,
    "transit": 0.15,
    "parks": 0.10,
    "development": 0.15,
    "air_quality": 0.05,
    "affordability": 0.15,
    "walkability": 0.10,
}

# Trend detection threshold (score change must exceed this to be non-stable)
TREND_THRESHOLD = 0.3


# ── Core Functions ────────────────────────────────────────────

def normalize_metric(
    value: float,
    min_val: float,
    max_val: float,
    higher_is_better: bool = True,
) -> float:
    """Normalize a raw metric value to a 0-10 scale.

    Args:
        value: The raw metric value to normalize.
        min_val: Minimum value across all neighborhoods for this metric.
        max_val: Maximum value across all neighborhoods for this metric.
        higher_is_better: If True, higher raw values → higher scores.
                         If False, lower raw values → higher scores (e.g., crime).

    Returns:
        Normalized score between 0.0 and 10.0.
    """
    # Edge case: all neighborhoods have the same value
    if max_val == min_val:
        return 5.0

    # Normalize to 0-1 range
    normalized = (value - min_val) / (max_val - min_val)

    # Invert if lower is better (e.g., crime rate)
    if not higher_is_better:
        normalized = 1.0 - normalized

    # Scale to 0-10, with a floor of 0.5 (nobody gets a true zero for UX)
    score = normalized * 9.5 + 0.5

    # Clamp to [0, 10]
    return round(max(0.0, min(10.0, score)), 1)


def compute_composite_score(
    category_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute weighted composite score from individual category scores.

    Args:
        category_scores: Dict mapping category name → score (0-10).
        weights: Dict mapping category name → weight (should sum to 1.0).

    Returns:
        Weighted average score between 0.0 and 10.0.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for category, weight in weights.items():
        if category in category_scores:
            weighted_sum += category_scores[category] * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    # Renormalize: if only a subset of categories are present,
    # divide by the sum of present weights so the score stays on a 0-10 scale.
    score = weighted_sum / total_weight

    return round(max(0.0, min(10.0, score)), 1)


def rank_neighborhoods(
    all_scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> list[dict]:
    """Rank neighborhoods by composite score.

    Args:
        all_scores: Dict mapping neighborhood name → {category: score}.
        weights: Scoring weights.

    Returns:
        List of dicts with 'name', 'score', 'rank', sorted by score descending.
    """
    composites = []
    for name, scores in all_scores.items():
        composite = compute_composite_score(scores, weights)
        composites.append({"name": name, "score": composite})

    # Sort by score descending
    composites.sort(key=lambda x: x["score"], reverse=True)

    # Assign ranks
    for i, entry in enumerate(composites):
        entry["rank"] = i + 1

    return composites


def detect_trend(
    current_score: float,
    previous_score: Optional[float],
    threshold: float = TREND_THRESHOLD,
) -> tuple[str, float]:
    """Detect trend direction between two scoring periods.

    Args:
        current_score: Current period's score.
        previous_score: Previous period's score (None if no history).
        threshold: Minimum change to be non-stable.

    Returns:
        Tuple of (trend_direction, change_amount).
        trend_direction is one of: 'improving', 'declining', 'stable'.
    """
    if previous_score is None:
        return "stable", 0.0

    change = round(current_score - previous_score, 2)

    if change > threshold:
        return "improving", change
    elif change < -threshold:
        return "declining", change
    else:
        return "stable", change


def get_top_and_bottom(
    category_scores: dict[str, float],
) -> tuple[str, str]:
    """Identify the highest and lowest scoring categories.

    Args:
        category_scores: Dict mapping category → score.

    Returns:
        Tuple of (top_category, bottom_category).
    """
    if not category_scores:
        return ("", "")

    sorted_cats = sorted(category_scores.items(), key=lambda x: x[1])
    bottom = sorted_cats[0][0]
    top = sorted_cats[-1][0]

    return top, bottom


# ── Database Operations ───────────────────────────────────────

async def get_all_neighborhood_summaries(db_pool) -> list[dict]:
    """Get all neighborhoods with their latest composite scores.

    Returns a list of NeighborhoodSummary-compatible dicts.
    """
    async with db_pool.acquire() as conn:
        # FIX: Use per-neighborhood MAX(period_start) instead of global MAX
        rows = await conn.fetch("""
            SELECT
                n.name,
                n.slug,
                COALESCE(c.overall_score, 0) as overall_score,
                c.rank,
                c.category_scores
            FROM neighborhoods n
            LEFT JOIN neighborhood_composite_scores c ON c.neighborhood_id = n.id
                AND c.period_start = (
                    SELECT MAX(c2.period_start)
                    FROM neighborhood_composite_scores c2
                    WHERE c2.neighborhood_id = n.id
                )
            ORDER BY c.rank NULLS LAST, n.name
        """)

        # Get actual count instead of hardcoding
        total = await conn.fetchval("SELECT COUNT(*) FROM neighborhoods")

        summaries = []
        for i, row in enumerate(rows):
            cat_scores = row.get("category_scores") or {}
            top, bottom = get_top_and_bottom(cat_scores) if cat_scores else ("", "")

            summaries.append({
                "name": row["name"],
                "slug": row["slug"],
                "overall_score": float(row["overall_score"]),
                "rank": row.get("rank") or (i + 1),  # Fallback rank if no scores yet
                "top_category": top or None,
                "bottom_category": bottom or None,
            })

        return summaries


async def get_neighborhood_scorecard(db_pool, slug: str) -> Optional[dict]:
    """Get full scorecard for a single neighborhood.

    Returns a NeighborhoodScorecard-compatible dict, or None if not found.
    """
    async with db_pool.acquire() as conn:
        # Get neighborhood info
        hood = await conn.fetchrow(
            "SELECT id, name, slug, population, area_km2 FROM neighborhoods WHERE slug = $1",
            slug,
        )
        if not hood:
            return None

        hood_id = hood["id"]

        # Get latest composite score
        composite = await conn.fetchrow("""
            SELECT overall_score, rank, category_scores, weights_used,
                   period_start, period_end, computed_at
            FROM neighborhood_composite_scores
            WHERE neighborhood_id = $1
            ORDER BY period_start DESC LIMIT 1
        """, hood_id)

        # FIX: Get category scores for LATEST PERIOD ONLY using DISTINCT ON
        cat_scores = await conn.fetch("""
            SELECT DISTINCT ON (category)
                category, score, raw_value, percentile, trend, trend_change
            FROM neighborhood_scores
            WHERE neighborhood_id = $1
            ORDER BY category, period_start DESC
        """, hood_id)

        # Get signal stats from intelligence_signals (graceful if table empty)
        try:
            signal_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE signal_type = 'rezoning_decision') as active_rezonings,
                    COUNT(*) FILTER (WHERE signal_type = 'permit_approval') as recent_permits,
                    COUNT(*) as recent_signals
                FROM intelligence_signals
                WHERE neighborhood = $1
                  AND extracted_at > NOW() - INTERVAL '90 days'
            """, hood["name"])
        except Exception:
            logger.warning("intelligence_signals query failed for %s", hood["name"])
            signal_stats = None

        return {
            "neighborhood": {
                "name": hood["name"],
                "slug": hood["slug"],
            },
            "overall_score": float(composite["overall_score"]) if composite else 0.0,
            "rank": composite["rank"] if composite else None,
            "category_scores": [
                {
                    "category": row["category"],
                    "score": float(row["score"]),
                    "trend": row.get("trend", "stable"),
                    # FIX: Use trend_delta consistently (matches frontend TypeScript)
                    "trend_delta": float(row["trend_change"]) if row.get("trend_change") else 0.0,
                }
                for row in cat_scores
            ],
            "active_rezonings": signal_stats["active_rezonings"] if signal_stats else 0,
            "recent_permits": signal_stats["recent_permits"] if signal_stats else 0,
        }


async def compare_neighborhoods(db_pool, slugs: list[str]) -> Optional[dict]:
    """Compare 2-4 neighborhoods side by side.

    Returns a NeighborhoodComparison-compatible dict.
    """
    if not (2 <= len(slugs) <= 4):
        return None

    scorecards = []
    for slug in slugs:
        card = await get_neighborhood_scorecard(db_pool, slug)
        if card:
            scorecards.append(card)

    if len(scorecards) < 2:
        return None

    return {
        "neighborhoods": scorecards,
        "categories": list(METRIC_DIRECTIONS.keys()),
    }
