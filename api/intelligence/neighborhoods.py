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
        _total = await conn.fetchval("SELECT COUNT(*) FROM neighborhoods")  # noqa: F841

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
    Uses a single CTE query for neighborhood info + composite + category scores
    (2 queries total: 1 main CTE + 1 signal stats).
    """
    async with db_pool.acquire() as conn:
        # Single CTE query: neighborhood + composite + category scores
        row = await conn.fetchrow("""
            WITH hood AS (
                SELECT id, name, slug FROM neighborhoods WHERE slug = $1
            ),
            latest_composite AS (
                SELECT overall_score, rank
                FROM neighborhood_composite_scores
                WHERE neighborhood_id = (SELECT id FROM hood)
                ORDER BY period_start DESC LIMIT 1
            )
            SELECT
                h.id, h.name, h.slug,
                lc.overall_score, lc.rank
            FROM hood h
            LEFT JOIN latest_composite lc ON TRUE
        """, slug)

        if not row:
            return None

        hood_id = row["id"]
        hood_name = row["name"]

        # Category scores — still need a second query for the DISTINCT ON
        cat_scores = await conn.fetch("""
            SELECT DISTINCT ON (category)
                category, score, raw_value, percentile, trend, trend_change
            FROM neighborhood_scores
            WHERE neighborhood_id = $1
            ORDER BY category, period_start DESC
        """, hood_id)

        # Signal stats (graceful if table empty)
        try:
            signal_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE signal_type = 'rezoning_decision') as active_rezonings,
                    COUNT(*) FILTER (WHERE signal_type = 'permit_approval') as recent_permits,
                    COUNT(*) as recent_signals
                FROM intelligence_signals
                WHERE neighborhood = $1
                  AND extracted_at > NOW() - INTERVAL '90 days'
            """, hood_name)
        except Exception:
            logger.warning("intelligence_signals query failed for %s", hood_name)
            signal_stats = None

        return _format_scorecard(row, cat_scores, signal_stats)


def _format_scorecard(hood_row, cat_scores, signal_stats) -> dict:
    """Format raw DB rows into a scorecard response dict."""
    return {
        "neighborhood": {
            "name": hood_row["name"],
            "slug": hood_row["slug"],
        },
        "overall_score": float(hood_row["overall_score"]) if hood_row.get("overall_score") else 0.0,
        "rank": hood_row["rank"] if hood_row.get("rank") else None,
        "category_scores": [
            {
                "category": row["category"],
                "score": float(row["score"]),
                "trend": row.get("trend", "stable"),
                "trend_delta": float(row["trend_change"]) if row.get("trend_change") else 0.0,
            }
            for row in cat_scores
        ],
        "active_rezonings": signal_stats["active_rezonings"] if signal_stats else 0,
        "recent_permits": signal_stats["recent_permits"] if signal_stats else 0,
    }


async def compare_neighborhoods(db_pool, slugs: list[str]) -> Optional[dict]:
    """Compare 2-4 neighborhoods side by side.

    Batched: 3 queries total regardless of neighborhood count
    (was: 4 queries × N neighborhoods = up to 16 queries for 4 slugs).
    """
    if not (2 <= len(slugs) <= 4):
        return None

    async with db_pool.acquire() as conn:
        # Query 1: All neighborhoods + composite scores in one shot
        hoods = await conn.fetch("""
            SELECT
                n.id, n.name, n.slug,
                c.overall_score, c.rank
            FROM neighborhoods n
            LEFT JOIN LATERAL (
                SELECT overall_score, rank
                FROM neighborhood_composite_scores
                WHERE neighborhood_id = n.id
                ORDER BY period_start DESC LIMIT 1
            ) c ON TRUE
            WHERE n.slug = ANY($1)
        """, slugs)

        if len(hoods) < 2:
            return None

        hood_ids = [h["id"] for h in hoods]
        hood_names = [h["name"] for h in hoods]

        # Query 2: All category scores for all requested neighborhoods
        all_cat_scores = await conn.fetch("""
            SELECT DISTINCT ON (neighborhood_id, category)
                neighborhood_id, category, score, raw_value,
                percentile, trend, trend_change
            FROM neighborhood_scores
            WHERE neighborhood_id = ANY($1)
            ORDER BY neighborhood_id, category, period_start DESC
        """, hood_ids)

        # Query 3: Signal stats for all requested neighborhoods
        try:
            all_signal_stats = await conn.fetch("""
                SELECT
                    neighborhood,
                    COUNT(*) FILTER (WHERE signal_type = 'rezoning_decision') as active_rezonings,
                    COUNT(*) FILTER (WHERE signal_type = 'permit_approval') as recent_permits,
                    COUNT(*) as recent_signals
                FROM intelligence_signals
                WHERE neighborhood = ANY($1)
                  AND extracted_at > NOW() - INTERVAL '90 days'
                GROUP BY neighborhood
            """, hood_names)
        except Exception:
            logger.warning("intelligence_signals batch query failed")
            all_signal_stats = []

    # Index results for fast lookup
    cat_by_hood = {}
    for row in all_cat_scores:
        cat_by_hood.setdefault(row["neighborhood_id"], []).append(row)

    sig_by_name = {row["neighborhood"]: row for row in all_signal_stats}

    # Assemble scorecards
    scorecards = []
    for hood in hoods:
        cats = cat_by_hood.get(hood["id"], [])
        sigs = sig_by_name.get(hood["name"])
        scorecards.append(_format_scorecard(hood, cats, sigs))

    return {
        "neighborhoods": scorecards,
        "categories": list(METRIC_DIRECTIONS.keys()),
    }
