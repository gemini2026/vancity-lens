"""
VCL-42 [INTEL-007] Weekly digest generator for VanCity Lens.

This module handles:
- Digest subscriptions management (CRUD)
- Weekly digest generation from intelligence signals
- Digest content summarization and formatting
- Delivery tracking and status management
- Digest scheduler for batch processing
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────────────────

class DigestFrequency(str, Enum):
    """Frequency options for digest subscriptions."""
    DAILY = "daily"
    WEEKLY = "weekly"


class DeliveryStatus(str, Enum):
    """Status of digest delivery."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────

class DigestSubscription(BaseModel):
    """User digest subscription configuration."""
    id: Optional[int] = None
    user_id: int
    neighborhoods: List[str] = Field(default_factory=list)
    signal_types: List[str] = Field(default_factory=list)
    frequency: DigestFrequency = DigestFrequency.WEEKLY
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DigestHighlight(BaseModel):
    """Top highlight from digest period."""
    signal_id: int
    headline: str
    summary: str
    signal_type: str
    neighborhood: Optional[str]
    severity: str
    event_date: Optional[date]
    confidence: float


class DigestStats(BaseModel):
    """Statistical summary for digest period."""
    total_signals: int
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_neighborhood: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    trend_change_pct: float = 0.0
    period_days: int


class NeighborhoodUpdate(BaseModel):
    """Summary of signals for one neighborhood."""
    neighborhood: str
    signal_count: int
    signal_types: List[str] = Field(default_factory=list)
    top_signal: Optional[DigestHighlight] = None
    key_events: List[str] = Field(default_factory=list)
    severity_distribution: Dict[str, int] = Field(default_factory=dict)


class DigestContent(BaseModel):
    """Complete content of a generated digest."""
    subscription_id: int
    digest_date: date
    date_from: date
    date_to: date
    highlights: List[DigestHighlight] = Field(default_factory=list)
    statistics: DigestStats
    neighborhood_updates: List[NeighborhoodUpdate] = Field(default_factory=list)
    summary_text: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class DigestDelivery(BaseModel):
    """Record of a digest delivery."""
    id: Optional[int] = None
    subscription_id: int
    digest_date: date
    content_json: Dict[str, Any]
    signal_count: int
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None


# ────────────────────────────────────────────────────────────────────────────
# DigestGenerator Class
# ────────────────────────────────────────────────────────────────────────────

class DigestGenerator:
    """Generates digests from intelligence signals for specified neighborhoods and types."""

    @staticmethod
    async def generate_weekly_digest(
        db_pool: asyncpg.Pool,
        user_id: int,
        neighborhoods: Optional[List[str]] = None,
        signal_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> DigestContent:
        """
        Generate a weekly digest for the specified period and filters.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of user requesting digest
            neighborhoods: List of neighborhoods to include (None = all)
            signal_types: List of signal types to include (None = all)
            date_from: Start date (default: 7 days ago)
            date_to: End date (default: today)

        Returns:
            DigestContent object with full digest information
        """
        try:
            # Set default date range based on frequency
            if date_to is None:
                date_to = date.today()
            if date_from is None:
                # Default: 7 days for weekly, 1 day for daily
                date_from = date_to - timedelta(days=7)

            logger.info(
                f"Generating digest for user {user_id} from {date_from} to {date_to}"
            )

            # Fetch signals matching criteria
            signals = await DigestGenerator._fetch_signals_for_period(
                db_pool,
                date_from,
                date_to,
                neighborhoods,
                signal_types,
            )

            logger.info(f"Fetched {len(signals)} signals for digest")

            # Summarize signals
            _summary = DigestGenerator._summarize_signals(signals)  # noqa: F841

            # Generate highlights (top 5 most impactful)
            highlights = DigestGenerator._generate_highlights(signals)

            # Compute statistics
            stats = DigestGenerator._compute_statistics(signals, date_from, date_to)

            # Format neighborhood updates
            neighborhood_updates = DigestGenerator._format_neighborhood_updates(signals)

            # Create summary text
            summary_text = DigestGenerator._create_summary_text(
                len(signals),
                stats,
                neighborhoods or [],
                highlights,
            )

            digest = DigestContent(
                subscription_id=0,  # Will be set by caller
                digest_date=date_to,
                date_from=date_from,
                date_to=date_to,
                highlights=highlights,
                statistics=stats,
                neighborhood_updates=neighborhood_updates,
                summary_text=summary_text,
            )

            logger.info(f"Generated digest with {len(highlights)} highlights")
            return digest

        except Exception as e:
            logger.error(f"Error generating digest: {e}", exc_info=True)
            raise

    @staticmethod
    async def _fetch_signals_for_period(
        db_pool: asyncpg.Pool,
        date_from: date,
        date_to: date,
        neighborhoods: Optional[List[str]] = None,
        signal_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch signals matching period and optional filters.

        Returns list of signal dictionaries with all relevant fields.
        """
        try:
            query = """
                SELECT
                    isig.id,
                    isig.document_id,
                    isig.signal_type,
                    isig.summary,
                    isig.headline,
                    isig.addresses,
                    isig.neighborhood,
                    isig.decision,
                    isig.vote_for,
                    isig.vote_against,
                    isig.sentiment,
                    isig.severity,
                    isig.confidence,
                    isig.event_date,
                    d.title AS source_title,
                    d.source_url,
                    d.source_type,
                    d.published_date AS source_date
                FROM intelligence_signals isig
                JOIN documents d ON isig.document_id = d.id
                WHERE isig.event_date >= $1 AND isig.event_date <= $2
            """

            params = [date_from, date_to]

            # Add neighborhood filter if specified
            if neighborhoods:
                placeholders = ", ".join(
                    f"${i + 3}" for i in range(len(neighborhoods))
                )
                query += f" AND isig.neighborhood = ANY(ARRAY[{placeholders}])"
                params.extend(neighborhoods)

            # Add signal type filter if specified
            if signal_types:
                signal_params = signal_types
                start_idx = len(params) + 1
                placeholders = ", ".join(
                    f"${start_idx + i}" for i in range(len(signal_params))
                )
                query += f" AND isig.signal_type = ANY(ARRAY[{placeholders}])"
                params.extend(signal_params)

            query += " ORDER BY isig.event_date DESC"

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            signals = [dict(row) for row in rows]
            logger.info(f"Fetched {len(signals)} signals for period {date_from} to {date_to}")
            return signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}", exc_info=True)
            raise

    @staticmethod
    def _summarize_signals(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize signals by grouping into categories.

        Returns dictionary with signal counts by type, neighborhood, and severity.
        """
        summary = {
            "by_type": {},
            "by_neighborhood": {},
            "by_severity": {},
        }

        for signal in signals:
            # By type
            sig_type = signal.get("signal_type", "unknown")
            summary["by_type"][sig_type] = summary["by_type"].get(sig_type, 0) + 1

            # By neighborhood
            neighborhood = signal.get("neighborhood")
            if neighborhood:
                summary["by_neighborhood"][neighborhood] = (
                    summary["by_neighborhood"].get(neighborhood, 0) + 1
                )

            # By severity
            severity = signal.get("severity", "info")
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1

        return summary

    @staticmethod
    def _generate_highlights(signals: List[Dict[str, Any]]) -> List[DigestHighlight]:
        """
        Generate top 5 most impactful signals as highlights.

        Prioritizes by: severity (critical/high), confidence, and recency.
        """
        if not signals:
            return []

        # Sort by severity weight, then confidence, then recency
        severity_weight = {
            "critical": 5,
            "high": 4,
            "medium": 3,
            "low": 2,
            "info": 1,
        }

        def score_signal(sig: Dict[str, Any]) -> tuple:
            severity = sig.get("severity", "info")
            confidence = float(sig.get("confidence", 0.5))
            event_date = sig.get("event_date") or date.min
            return (
                severity_weight.get(severity, 0),
                confidence,
                event_date,  # More recent first (reversed in sort)
            )

        sorted_signals = sorted(signals, key=score_signal, reverse=True)

        highlights = []
        for signal in sorted_signals[:5]:
            highlight = DigestHighlight(
                signal_id=signal["id"],
                headline=signal.get("headline") or signal.get("summary", "")[:100],
                summary=signal.get("summary", "")[:500],
                signal_type=signal.get("signal_type", "other"),
                neighborhood=signal.get("neighborhood"),
                severity=signal.get("severity", "info"),
                event_date=signal.get("event_date"),
                confidence=float(signal.get("confidence", 0.5)),
            )
            highlights.append(highlight)

        logger.info(f"Generated {len(highlights)} highlights from {len(signals)} signals")
        return highlights

    @staticmethod
    def _compute_statistics(
        signals: List[Dict[str, Any]],
        date_from: date,
        date_to: date,
    ) -> DigestStats:
        """
        Compute statistics for the digest period.

        Includes counts, trends, and comparisons to previous period.
        """
        period_days = (date_to - date_from).days + 1

        # Count by categories
        by_type = {}
        by_neighborhood = {}
        by_severity = {}

        for signal in signals:
            sig_type = signal.get("signal_type", "unknown")
            by_type[sig_type] = by_type.get(sig_type, 0) + 1

            neighborhood = signal.get("neighborhood")
            if neighborhood:
                by_neighborhood[neighborhood] = by_neighborhood.get(neighborhood, 0) + 1

            severity = signal.get("severity", "info")
            by_severity[severity] = by_severity.get(severity, 0) + 1

        # Simple trend calculation (would be enhanced with historical data)
        trend_change_pct = 0.0

        stats = DigestStats(
            total_signals=len(signals),
            by_type=by_type,
            by_neighborhood=by_neighborhood,
            by_severity=by_severity,
            trend_change_pct=trend_change_pct,
            period_days=period_days,
        )

        return stats

    @staticmethod
    def _format_neighborhood_updates(
        signals: List[Dict[str, Any]],
    ) -> List[NeighborhoodUpdate]:
        """
        Format signals by neighborhood with summaries.

        Groups signals by neighborhood and generates key event summaries.
        """
        # Group by neighborhood
        neighborhoods = {}
        for signal in signals:
            neighborhood = signal.get("neighborhood")
            if not neighborhood:
                continue

            if neighborhood not in neighborhoods:
                neighborhoods[neighborhood] = []
            neighborhoods[neighborhood].append(signal)

        updates = []
        for neighborhood, neighborhood_signals in sorted(neighborhoods.items()):
            # Count signal types
            signal_types = {}
            severity_dist = {}
            for sig in neighborhood_signals:
                sig_type = sig.get("signal_type", "other")
                signal_types[sig_type] = signal_types.get(sig_type, 0) + 1

                severity = sig.get("severity", "info")
                severity_dist[severity] = severity_dist.get(severity, 0) + 1

            # Top signal by severity/confidence
            top_signal = None
            if neighborhood_signals:
                sorted_sigs = sorted(
                    neighborhood_signals,
                    key=lambda s: (
                        {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}.get(
                            s.get("severity", "info"), 0
                        ),
                        float(s.get("confidence", 0.5)),
                    ),
                    reverse=True,
                )
                top_sig = sorted_sigs[0]
                top_signal = DigestHighlight(
                    signal_id=top_sig["id"],
                    headline=top_sig.get("headline") or top_sig.get("summary", "")[:100],
                    summary=top_sig.get("summary", "")[:500],
                    signal_type=top_sig.get("signal_type", "other"),
                    neighborhood=neighborhood,
                    severity=top_sig.get("severity", "info"),
                    event_date=top_sig.get("event_date"),
                    confidence=float(top_sig.get("confidence", 0.5)),
                )

            # Key events (headlines of top 3 signals)
            key_events = [
                sig.get("headline") or sig.get("summary", "")[:100]
                for sig in sorted(
                    neighborhood_signals,
                    key=lambda s: (
                        {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}.get(
                            s.get("severity", "info"), 0
                        ),
                        float(s.get("confidence", 0.5)),
                    ),
                    reverse=True,
                )[:3]
            ]

            update = NeighborhoodUpdate(
                neighborhood=neighborhood,
                signal_count=len(neighborhood_signals),
                signal_types=list(signal_types.keys()),
                top_signal=top_signal,
                key_events=key_events,
                severity_distribution=severity_dist,
            )
            updates.append(update)

        return updates

    @staticmethod
    def _create_summary_text(
        total_signals: int,
        stats: DigestStats,
        neighborhoods: List[str],
        highlights: List[DigestHighlight],
    ) -> str:
        """
        Create human-readable summary text for digest.

        Provides overview of period, key stats, and major highlights.
        """
        lines = []

        lines.append("VanCity Lens Weekly Digest")
        lines.append(f"Period: {stats.period_days} days")
        lines.append("")

        if total_signals == 0:
            lines.append("No intelligence signals were recorded during this period.")
        else:
            lines.append(
                f"This digest summarizes {total_signals} intelligence signals "
                f"across {len(stats.by_neighborhood)} neighborhoods."
            )
            lines.append("")

            # Top signal types
            if stats.by_type:
                top_types = sorted(
                    stats.by_type.items(), key=lambda x: x[1], reverse=True
                )[:3]
                lines.append("Top Signal Types:")
                for sig_type, count in top_types:
                    lines.append(f"  - {sig_type.replace('_', ' ')}: {count}")
                lines.append("")

            # Severity breakdown
            if stats.by_severity:
                lines.append("Severity Distribution:")
                for severity in ["critical", "high", "medium", "low", "info"]:
                    count = stats.by_severity.get(severity, 0)
                    if count > 0:
                        lines.append(f"  - {severity.title()}: {count}")
                lines.append("")

            # Top highlights
            if highlights:
                lines.append("Top Highlights:")
                for i, highlight in enumerate(highlights[:3], 1):
                    lines.append(f"  {i}. {highlight.headline}")
                lines.append("")

        return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# DigestScheduler Class
# ────────────────────────────────────────────────────────────────────────────

class DigestScheduler:
    """Manages batch digest generation and delivery."""

    @staticmethod
    async def get_active_subscriptions(
        db_pool: asyncpg.Pool,
        frequency: Optional[DigestFrequency] = None,
    ) -> List[DigestSubscription]:
        """
        Retrieve all active digest subscriptions.

        Args:
            db_pool: AsyncPG connection pool
            frequency: Filter by frequency (None = all)

        Returns:
            List of DigestSubscription objects
        """
        try:
            query = "SELECT * FROM digest_subscriptions WHERE is_active = true"
            params = []

            if frequency:
                query += " AND frequency = $1"
                params.append(frequency.value)

            query += " ORDER BY user_id ASC"

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            subscriptions = [
                DigestSubscription(
                    id=row["id"],
                    user_id=row["user_id"],
                    neighborhoods=list(row["neighborhoods"] or []),
                    signal_types=list(row["signal_types"] or []),
                    frequency=DigestFrequency(row["frequency"]),
                    is_active=row["is_active"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

            logger.info(f"Retrieved {len(subscriptions)} active subscriptions")
            return subscriptions

        except Exception as e:
            logger.error(f"Error retrieving subscriptions: {e}", exc_info=True)
            raise

    @staticmethod
    async def process_subscription(
        db_pool: asyncpg.Pool,
        subscription: DigestSubscription,
    ) -> DigestDelivery:
        """
        Generate and deliver digest for a single subscription.

        Args:
            db_pool: AsyncPG connection pool
            subscription: Subscription to process

        Returns:
            DigestDelivery record
        """
        try:
            logger.info(f"Processing subscription {subscription.id} for user {subscription.user_id}")

            # Generate digest content with frequency-aware date range
            days_back = 1 if subscription.frequency == DigestFrequency.DAILY else 7
            digest_date_from = date.today() - timedelta(days=days_back)
            digest_content = await DigestGenerator.generate_weekly_digest(
                db_pool,
                subscription.user_id,
                neighborhoods=subscription.neighborhoods if subscription.neighborhoods else None,
                signal_types=subscription.signal_types if subscription.signal_types else None,
                date_from=digest_date_from,
            )

            # Create delivery record
            digest_date = date.today()
            content_json = digest_content.model_dump()

            # Check if delivery already exists for this date
            async with db_pool.acquire() as conn:
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM digest_deliveries
                    WHERE subscription_id = $1 AND digest_date = $2
                    """,
                    subscription.id,
                    digest_date,
                )

            if existing:
                logger.info(
                    f"Digest already exists for subscription {subscription.id} on {digest_date}"
                )
                # Update existing delivery
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE digest_deliveries
                        SET content_json = $1, signal_count = $2
                        WHERE id = $3
                        """,
                        content_json,
                        len(digest_content.highlights),
                        existing["id"],
                    )
                delivery_id = existing["id"]
            else:
                # Insert new delivery
                async with db_pool.acquire() as conn:
                    delivery_id = await conn.fetchval(
                        """
                        INSERT INTO digest_deliveries
                        (subscription_id, digest_date, content_json, signal_count, delivery_status)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                        """,
                        subscription.id,
                        digest_date,
                        content_json,
                        len(digest_content.highlights),
                        DeliveryStatus.PENDING.value,
                    )

            delivery = DigestDelivery(
                id=delivery_id,
                subscription_id=subscription.id,
                digest_date=digest_date,
                content_json=content_json,
                signal_count=len(digest_content.highlights),
                delivery_status=DeliveryStatus.PENDING,
            )

            logger.info(f"Created delivery record {delivery_id} for subscription {subscription.id}")
            return delivery

        except Exception as e:
            logger.error(f"Error processing subscription {subscription.id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def run_digest_cycle(
        db_pool: asyncpg.Pool,
        frequency: DigestFrequency = DigestFrequency.WEEKLY,
    ) -> List[DigestDelivery]:
        """
        Process all active subscriptions for a given frequency.

        Generates and stores digests for all matching subscriptions.

        Args:
            db_pool: AsyncPG connection pool
            frequency: Frequency to process (default: WEEKLY)

        Returns:
            List of DigestDelivery records created
        """
        try:
            logger.info(f"Starting digest cycle for frequency: {frequency.value}")

            # Get active subscriptions for this frequency
            subscriptions = await DigestScheduler.get_active_subscriptions(
                db_pool, frequency
            )

            logger.info(f"Processing {len(subscriptions)} subscriptions")

            # Process each subscription
            deliveries = []
            for subscription in subscriptions:
                try:
                    delivery = await DigestScheduler.process_subscription(db_pool, subscription)
                    deliveries.append(delivery)
                except Exception as e:
                    logger.error(
                        f"Error processing subscription {subscription.id}: {e}", exc_info=True
                    )
                    # Continue with next subscription

            logger.info(f"Digest cycle completed with {len(deliveries)} deliveries")
            return deliveries

        except Exception as e:
            logger.error(f"Error running digest cycle: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_delivery_sent(
        db_pool: asyncpg.Pool,
        delivery_id: int,
    ) -> bool:
        """
        Mark a digest delivery as sent.

        Args:
            db_pool: AsyncPG connection pool
            delivery_id: ID of delivery to mark

        Returns:
            True if successful
        """
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE digest_deliveries
                    SET delivery_status = $1, sent_at = NOW()
                    WHERE id = $2
                    """,
                    DeliveryStatus.SENT.value,
                    delivery_id,
                )

            logger.info(f"Marked delivery {delivery_id} as sent")
            return True

        except Exception as e:
            logger.error(f"Error marking delivery as sent: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_delivery_failed(
        db_pool: asyncpg.Pool,
        delivery_id: int,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Mark a digest delivery as failed.

        Args:
            db_pool: AsyncPG connection pool
            delivery_id: ID of delivery to mark
            error_message: Optional error message

        Returns:
            True if successful
        """
        try:
            # Would update with error_message if schema had error column
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE digest_deliveries
                    SET delivery_status = $1
                    WHERE id = $2
                    """,
                    DeliveryStatus.FAILED.value,
                    delivery_id,
                )

            logger.info(f"Marked delivery {delivery_id} as failed")
            return True

        except Exception as e:
            logger.error(f"Error marking delivery as failed: {e}", exc_info=True)
            raise
