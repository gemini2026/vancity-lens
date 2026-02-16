"""
VanCity Lens — Political Risk Score Engine (FR-OPP-003)

Computes neighborhood-level political risk scores (1-10) based on:
1. Opposition rate — % of applications with opposition signals
2. Delay attribution — opposition-caused delays in pipeline
3. Sentiment intensity — recency-weighted negative sentiment
4. Council resistance — voting patterns against development

Scores are materialized monthly and stored in political_risk_scores table.
"""

import logging
import math
from datetime import date, timedelta, timezone, datetime
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Vancouver neighborhoods (canonical list)
VANCOUVER_NEIGHBORHOODS = [
    "Arbutus Ridge", "Downtown", "Dunbar-Southlands", "Fairview",
    "Grandview-Woodland", "Hastings-Sunrise", "Kensington-Cedar Cottage",
    "Kerrisdale", "Killarney", "Kitsilano", "Marpole", "Mount Pleasant",
    "Oakridge", "Renfrew-Collingwood", "Riley Park", "Shaughnessy",
    "South Cambie", "Strathcona", "Sunset", "Victoria-Fraserview",
    "West End", "West Point Grey",
]

# Component weights for composite score
WEIGHT_OPPOSITION_RATE = 0.30
WEIGHT_DELAY = 0.20
WEIGHT_SENTIMENT = 0.30
WEIGHT_COUNCIL = 0.20

# Minimum thresholds
MIN_APPLICATIONS = 5        # AC-OPP: need at least 5 applications
MIN_SIGNALS = 10            # Need at least 10 signals for theme/sentiment analysis


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))


def compute_opposition_rate(
    total_applications: int,
    opposed_applications: int,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Compute opposition rate and its score (0-10).

    Returns (raw_rate_pct, score_0_10, status).
    When total_applications < MIN_APPLICATIONS, returns (None, None, status_message)
    so callers can distinguish "low risk" from "no data".
    """
    if total_applications < MIN_APPLICATIONS:
        return None, None, "Insufficient application history"

    rate = (opposed_applications / total_applications) * 100.0
    # Scale: 0% opposition = 0, 50%+ = 10
    score = _clamp(rate / 5.0)
    return round(rate, 2), round(score, 1), None


def compute_delay_score(
    avg_delay_months: Optional[float],
) -> float:
    """
    Compute delay attribution score (0-10).

    Typical rezoning takes 12-18 months. Delays beyond 18 months
    attributed to opposition/political factors.
    """
    if avg_delay_months is None or avg_delay_months <= 0:
        return 0.0

    # Baseline: 12 months is normal (no penalty)
    # Each additional 6 months beyond 12 adds 2.5 points
    excess = max(0, avg_delay_months - 12)
    score = _clamp(excess / 2.4)
    return round(score, 1)


def compute_sentiment_intensity(
    signals: list[dict],
    period_months: int = 36,
) -> float:
    """
    Compute recency-weighted negative sentiment score (0-10).

    More recent negative signals contribute more to the score.
    Uses exponential decay with half-life of 6 months.
    """
    if not signals or len(signals) < MIN_SIGNALS:
        return 0.0

    now = datetime.now(timezone.utc).date()
    half_life_days = 180  # ~6 months
    decay_constant = math.log(2) / half_life_days

    weighted_negative = 0.0
    total_weight = 0.0

    for sig in signals:
        event_date = sig.get("event_date")
        sentiment = sig.get("sentiment", "")
        confidence = float(sig.get("confidence", 0.5))

        if confidence < 0.60:
            continue

        if event_date is None:
            continue
        if isinstance(event_date, str):
            try:
                event_date = date.fromisoformat(event_date)
            except (ValueError, TypeError):
                continue

        days_ago = (now - event_date).days
        if days_ago < 0:
            days_ago = 0

        weight = math.exp(-decay_constant * days_ago)
        total_weight += weight

        if sentiment == "negative_for_development":
            weighted_negative += weight

    if total_weight == 0:
        return 0.0

    negative_ratio = weighted_negative / total_weight
    # Scale: 0% negative = 0, 60%+ negative = 10
    score = _clamp(negative_ratio * 100 / 6.0)
    return round(score, 1)


def compute_council_resistance(
    vote_records: list[dict],
) -> tuple[float, float]:
    """
    Compute council voting resistance score (0-10).

    Analyzes vote_for/vote_against patterns for development-related decisions.
    Returns (avg_against_pct, score_0_10).
    """
    if not vote_records:
        return 0.0, 0.0

    total_against_pct = 0.0
    valid_records = 0

    for record in vote_records:
        vote_for = record.get("vote_for") or 0
        vote_against = record.get("vote_against") or 0
        total_votes = vote_for + vote_against

        if total_votes == 0:
            continue

        against_pct = (vote_against / total_votes) * 100
        total_against_pct += against_pct
        valid_records += 1

    if valid_records == 0:
        return 0.0, 0.0

    avg_against = total_against_pct / valid_records
    # Scale: 0% against = 0, 50%+ against = 10
    score = _clamp(avg_against / 5.0)
    return round(avg_against, 2), round(score, 1)


def compute_composite_score(
    opposition_score: Optional[float],
    delay_score: float,
    sentiment_score: float,
    council_score: float,
) -> tuple[Optional[float], Optional[str]]:
    """
    Compute composite Political Risk Score (1-10).

    Weighted average of component scores, clamped to [1, 10].
    Returns (score, status). When opposition_score is None (insufficient
    application data), returns (None, "Insufficient application history").
    """
    if opposition_score is None:
        return None, "Insufficient application history"

    raw = (
        WEIGHT_OPPOSITION_RATE * opposition_score
        + WEIGHT_DELAY * delay_score
        + WEIGHT_SENTIMENT * sentiment_score
        + WEIGHT_COUNCIL * council_score
    )
    # Scale from 0-10 to 1-10
    score = 1.0 + (raw * 0.9)
    return round(_clamp(score, 1.0, 10.0), 1), None


async def compute_neighborhood_risk(
    db_pool: asyncpg.Pool,
    neighborhood: str,
    period_months: int = 36,
) -> dict:
    """
    Compute political risk score for a single neighborhood.

    Returns a dict with all component scores and raw data.
    """
    cutoff = date.today() - timedelta(days=period_months * 30)

    async with db_pool.acquire() as conn:
        # 1. Opposition rate: count applications vs opposed applications
        app_stats = await conn.fetchrow("""
            SELECT
                COUNT(DISTINCT sp.id) AS total_apps,
                COUNT(DISTINCT CASE
                    WHEN EXISTS (
                        SELECT 1 FROM intelligence_signals s
                        WHERE s.neighborhood = $1
                          AND s.sentiment = 'negative_for_development'
                          AND s.event_date >= $2
                          AND s.parcel_pid = sp.parcel_pid
                    ) THEN sp.id
                END) AS opposed_apps
            FROM supply_pipeline sp
            WHERE sp.neighborhood = $1
              AND sp.created_at >= $2
        """, neighborhood, cutoff)

        total_apps = app_stats["total_apps"] if app_stats else 0
        opposed_apps = app_stats["opposed_apps"] if app_stats else 0
        opp_rate, opp_score, opp_status = compute_opposition_rate(total_apps, opposed_apps)

        # 2. Delay attribution: avg time between rezoning_application and council_decision
        delay_row = await conn.fetchrow("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (h2.changed_at - h1.changed_at)) / (30.0 * 86400)
            ) AS avg_delay_months
            FROM pipeline_stage_history h1
            JOIN pipeline_stage_history h2 ON h2.pipeline_id = h1.pipeline_id
            JOIN supply_pipeline sp ON sp.id = h1.pipeline_id
            WHERE h1.to_stage = 'rezoning_application'
              AND h2.to_stage IN ('council_decision', 'development_permit')
              AND sp.neighborhood = $1
              AND h1.changed_at >= $2
        """, neighborhood, cutoff)

        avg_delay = float(delay_row["avg_delay_months"]) if delay_row and delay_row["avg_delay_months"] else None
        d_score = compute_delay_score(avg_delay)

        # 3. Sentiment intensity: fetch signals for this neighborhood
        signals = await conn.fetch("""
            SELECT sentiment, event_date, confidence
            FROM intelligence_signals
            WHERE neighborhood = $1
              AND event_date >= $2
              AND confidence >= 0.60
        """, neighborhood, cutoff)

        signal_list = [dict(s) for s in signals]
        s_score = compute_sentiment_intensity(signal_list, period_months)

        # 4. Council resistance: voting patterns
        votes = await conn.fetch("""
            SELECT vote_for, vote_against
            FROM intelligence_signals
            WHERE neighborhood = $1
              AND event_date >= $2
              AND signal_type IN ('rezoning_decision', 'council_decision')
              AND (vote_for IS NOT NULL OR vote_against IS NOT NULL)
        """, neighborhood, cutoff)

        vote_list = [dict(v) for v in votes]
        avg_against_pct, c_score = compute_council_resistance(vote_list)

        # Composite
        composite, score_status = compute_composite_score(opp_score, d_score, s_score, c_score)

        neg_signals = sum(1 for s in signal_list if s.get("sentiment") == "negative_for_development")

        # Determine themes_status based on signal count
        themes_status = None
        if len(signal_list) < MIN_SIGNALS:
            themes_status = "Insufficient data for theme analysis"

        result = {
            "neighborhood": neighborhood,
            "risk_score": composite,
            "opposition_rate": opp_rate if opp_rate is not None else 0.0,
            "delay_score": d_score,
            "sentiment_intensity": s_score,
            "council_resistance": c_score,
            "total_applications": total_apps,
            "opposed_applications": opposed_apps,
            "total_signals": len(signal_list),
            "negative_signals": neg_signals,
            "avg_delay_months": round(avg_delay, 1) if avg_delay else None,
            "avg_vote_against_pct": avg_against_pct,
            "period_months": period_months,
        }

        # Add status fields when data is insufficient
        if score_status:
            result["score_status"] = score_status
        if themes_status:
            result["themes_status"] = themes_status

        return result


async def materialize_all_scores(
    db_pool: asyncpg.Pool,
    period_months: int = 36,
) -> dict:
    """
    Compute and store political risk scores for all 22 neighborhoods.

    Returns summary stats: neighborhoods_computed, errors.
    """
    stats = {"neighborhoods_computed": 0, "errors": 0, "scores": {}}

    for neighborhood in VANCOUVER_NEIGHBORHOODS:
        try:
            result = await compute_neighborhood_risk(db_pool, neighborhood, period_months)

            # Skip DB materialization when score is None (insufficient data)
            if result["risk_score"] is None:
                logger.info(
                    "Skipping materialization for %s: %s",
                    neighborhood,
                    result.get("score_status", "insufficient data"),
                )
                stats["scores"][neighborhood] = None
                stats["neighborhoods_computed"] += 1
                continue

            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO political_risk_scores (
                        neighborhood, risk_score, opposition_rate,
                        delay_score, sentiment_intensity, council_resistance,
                        total_applications, opposed_applications,
                        total_signals, negative_signals,
                        avg_delay_months, avg_vote_against_pct,
                        period_months
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                    result["neighborhood"],
                    result["risk_score"],
                    result["opposition_rate"],
                    result["delay_score"],
                    result["sentiment_intensity"],
                    result["council_resistance"],
                    result["total_applications"],
                    result["opposed_applications"],
                    result["total_signals"],
                    result["negative_signals"],
                    result["avg_delay_months"],
                    result["avg_vote_against_pct"],
                    result["period_months"],
                )

            stats["neighborhoods_computed"] += 1
            stats["scores"][neighborhood] = result["risk_score"]

        except Exception as e:
            logger.error("Error computing risk for %s: %s", neighborhood, str(e)[:200])
            stats["errors"] += 1

    logger.info("Political risk materialization complete: %s", stats)
    return stats


async def get_neighborhood_risk(
    db_pool: asyncpg.Pool,
    neighborhood: str,
) -> Optional[dict]:
    """Get the latest political risk score for a neighborhood."""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM latest_political_risk
                WHERE neighborhood = $1
            """, neighborhood)
            return dict(row) if row else None
    except Exception as e:
        logger.debug("Error fetching risk for %s: %s", neighborhood, e)
        return None


async def get_all_risk_scores(
    db_pool: asyncpg.Pool,
) -> list[dict]:
    """Get latest political risk scores for all neighborhoods."""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM latest_political_risk
                ORDER BY risk_score DESC
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("Error fetching all risk scores: %s", e)
        return []


# ── Sprint 8: Opposition Themes & Risk Narrative ────────────────────


# Common opposition theme keywords
THEME_KEYWORDS = {
    "traffic_congestion": ["traffic", "congestion", "parking", "transportation", "transit"],
    "building_height": ["height", "shadow", "tower", "storey", "tall", "high-rise"],
    "density": ["density", "overcrowd", "too many units", "overbuilt", "densification"],
    "neighborhood_character": ["character", "heritage", "neighborhood feel", "scale", "out of place"],
    "infrastructure": ["sewer", "water", "infrastructure", "capacity", "school"],
    "affordability": ["affordable", "affordability", "expensive", "market housing"],
    "environment": ["tree", "green space", "environment", "sustainability", "contamination"],
    "noise": ["noise", "construction", "disturbance", "disruption"],
    "view_impact": ["view", "sight line", "view cone", "obstruct"],
    "process": ["consultation", "process", "notification", "input", "rushed"],
}


def extract_opposition_themes(
    signals: list[dict],
    top_n: int = 3,
) -> tuple[list[dict], Optional[str]]:
    """
    Extract top opposition themes from negative signals.

    Returns (themes_list, themes_status).
    AC-OPP-004: Top 3 themes from 10+ signals.
    When signal count < MIN_SIGNALS (10), returns empty list with status message.
    """
    if len(signals) < MIN_SIGNALS:
        status = "Insufficient data for theme analysis" if signals else None
        return [], status

    theme_counts: dict[str, int] = {}
    theme_examples: dict[str, str] = {}

    for sig in signals:
        sentiment = sig.get("sentiment", "")
        if sentiment != "negative_for_development":
            continue

        text = (sig.get("summary", "") + " " + sig.get("headline", "")).lower()
        if not text.strip():
            continue

        for theme, keywords in THEME_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
                if theme not in theme_examples:
                    theme_examples[theme] = sig.get("summary", "")[:150]

    # Sort by frequency descending
    sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

    return [
        {
            "theme": theme.replace("_", " ").title(),
            "count": count,
            "example": theme_examples.get(theme, ""),
        }
        for theme, count in sorted_themes[:top_n]
    ], None


def generate_risk_narrative(
    neighborhood: str,
    risk_score: float,
    opposition_rate: float,
    themes: list[dict],
    total_signals: int,
    negative_signals: int,
) -> str:
    """
    Generate a risk narrative under 150 words.

    AC-OPP-005: Risk narrative <150 words.
    """
    if risk_score <= 3:
        risk_level = "low"
        outlook = "generally supportive of development"
    elif risk_score <= 6:
        risk_level = "moderate"
        outlook = "mixed, with some organized opposition"
    else:
        risk_level = "high"
        outlook = "frequently oppositional toward new development"

    parts = [
        f"{neighborhood} has a {risk_level} political risk score of {risk_score}/10."
    ]

    if total_signals > 0:
        neg_pct = (negative_signals / total_signals) * 100 if total_signals else 0
        parts.append(
            f"Analysis of {total_signals} intelligence signals over the trailing 36 months "
            f"shows {neg_pct:.0f}% negative sentiment toward development."
        )

    if opposition_rate > 0:
        parts.append(
            f"Approximately {opposition_rate:.0f}% of development applications "
            f"encountered community opposition."
        )

    if themes:
        theme_names = ", ".join(t["theme"].lower() for t in themes[:3])
        parts.append(f"Primary opposition themes include {theme_names}.")

    parts.append(f"The political environment is {outlook}.")

    narrative = " ".join(parts)
    # Truncate if over ~150 words
    words = narrative.split()
    if len(words) > 150:
        narrative = " ".join(words[:147]) + "..."

    return narrative


async def get_opposition_themes(
    db_pool: asyncpg.Pool,
    neighborhood: str,
    period_months: int = 36,
) -> tuple[list[dict], Optional[str]]:
    """Get top opposition themes for a neighborhood from signals.

    Returns (themes_list, themes_status).
    """
    cutoff = date.today() - timedelta(days=period_months * 30)

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT summary, headline, sentiment
                FROM intelligence_signals
                WHERE neighborhood = $1
                  AND event_date >= $2
                  AND confidence >= 0.60
            """, neighborhood, cutoff)

            return extract_opposition_themes([dict(r) for r in rows])
    except Exception as e:
        logger.debug("Error getting themes for %s: %s", neighborhood, e)
        return [], None


async def get_parcel_political_risk(
    db_pool: asyncpg.Pool,
    pid: str,
) -> Optional[dict]:
    """
    Get political risk summary for a specific parcel.

    Looks up the parcel's neighborhood and returns its risk score
    plus parcel-specific signals.
    """
    try:
        async with db_pool.acquire() as conn:
            # Get parcel neighborhood
            parcel = await conn.fetchrow(
                "SELECT geo_local_area FROM parcels WHERE pid = $1", pid
            )
            if not parcel or not parcel["geo_local_area"]:
                return None

            neighborhood = parcel["geo_local_area"]

            # Get neighborhood risk score
            risk = await conn.fetchrow("""
                SELECT * FROM latest_political_risk
                WHERE neighborhood = $1
            """, neighborhood)

            # Get parcel-specific opposition signals
            parcel_signals = await conn.fetch("""
                SELECT summary, headline, sentiment, event_date, confidence
                FROM intelligence_signals
                WHERE parcel_pid = $1
                  AND sentiment = 'negative_for_development'
                  AND confidence >= 0.60
                ORDER BY event_date DESC
                LIMIT 5
            """, pid)

            result = {
                "pid": pid,
                "neighborhood": neighborhood,
                "risk_score": float(risk["risk_score"]) if risk else None,
                "opposition_rate": float(risk["opposition_rate"]) if risk else None,
                "parcel_signals": [dict(s) for s in parcel_signals],
                "parcel_signal_count": len(parcel_signals),
            }

            # Get themes for the neighborhood
            cutoff = date.today() - timedelta(days=36 * 30)
            all_signals = await conn.fetch("""
                SELECT summary, headline, sentiment
                FROM intelligence_signals
                WHERE neighborhood = $1
                  AND event_date >= $2
                  AND confidence >= 0.60
            """, neighborhood, cutoff)

            themes, themes_status = extract_opposition_themes([dict(r) for r in all_signals])
            result["themes"] = themes
            if themes_status:
                result["themes_status"] = themes_status

            # Generate narrative
            if risk:
                result["narrative"] = generate_risk_narrative(
                    neighborhood,
                    float(risk["risk_score"]),
                    float(risk["opposition_rate"]) if risk["opposition_rate"] else 0,
                    themes,
                    int(risk["total_signals"]) if risk["total_signals"] else 0,
                    int(risk["negative_signals"]) if risk["negative_signals"] else 0,
                )

            return result
    except Exception as e:
        logger.debug("Error getting parcel risk for %s: %s", pid, e)
        return None
