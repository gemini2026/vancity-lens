"""
Intelligence signals CRUD and feed endpoints for VanCity Lens.

This module handles:
- Querying and filtering intelligence signals
- Paginated feed with rich metadata
- Spatial queries (signals near parcels using PostGIS)
- Dashboard statistics and aggregations
- Neighborhood enumeration
"""

import json
import logging
from datetime import date
from typing import Optional, List, Dict, Any

import asyncpg

from .models import SignalResponse, SignalFeedResponse, Severity

logger = logging.getLogger(__name__)


async def get_signal_feed(
    db_pool: asyncpg.Pool,
    neighborhood: Optional[str] = None,
    signal_type: Optional[str] = None,
    severity_min: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 20,
    offset: int = 0
) -> SignalFeedResponse:
    """
    Retrieve a paginated feed of intelligence signals with optional filters.

    Joins with documents table to include source information.
    Results sorted by event_date DESC (most recent first).

    Args:
        db_pool: AsyncPG connection pool
        neighborhood: Filter by neighborhood (exact match)
        signal_type: Filter by signal type (e.g., "rezoning_decision")
        severity_min: Filter by minimum severity ("info", "low", "medium", "high", "critical")
        date_from: Filter for signals after this date
        date_to: Filter for signals before this date
        limit: Number of results per page (max 100)
        offset: Pagination offset

    Returns:
        SignalFeedResponse with paginated signals and total count
    """

    try:
        # Validate and limit parameters
        limit = min(limit, 100)
        offset = max(offset, 0)

        # Build WHERE clause dynamically
        where_conditions = []
        params = []

        if neighborhood:
            where_conditions.append("isig.neighborhood = ${}".format(len(params) + 1))
            params.append(neighborhood)

        if signal_type:
            where_conditions.append("isig.signal_type = ${}".format(len(params) + 1))
            params.append(signal_type)

        if severity_min:
            # Map severity to numeric for comparison
            severity_levels = {
                "info": 0,
                "low": 1,
                "medium": 2,
                "high": 3,
                "critical": 4
            }
            severity_val = severity_levels.get(severity_min.lower(), 0)
            severity_col = "CASE isig.severity WHEN 'info' THEN 0 WHEN 'low' THEN 1 WHEN 'medium' THEN 2 WHEN 'high' THEN 3 WHEN 'critical' THEN 4 ELSE 0 END"
            where_conditions.append(f"{severity_col} >= {severity_val}")

        if date_from:
            where_conditions.append("isig.event_date >= ${}".format(len(params) + 1))
            params.append(date_from)

        if date_to:
            where_conditions.append("isig.event_date <= ${}".format(len(params) + 1))
            params.append(date_to)

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total
            FROM intelligence_signals isig
            WHERE {where_clause}
        """

        # Get paginated results
        feed_query = f"""
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
            WHERE {where_clause}
            ORDER BY isig.event_date DESC, isig.id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """

        async with db_pool.acquire() as conn:
            # Get count
            count_row = await conn.fetchrow(count_query, *params)
            total_count = count_row['total'] if count_row else 0

            # Get paginated results
            rows = await conn.fetch(feed_query, *params, limit, offset)

        # Convert rows to SignalResponse objects
        signals = []
        for row in rows:
            signal = SignalResponse(
                id=row['id'],
                document_id=row['document_id'],
                signal_type=row['signal_type'],
                summary=row['summary'],
                headline=row['headline'],
                addresses=row['addresses'] or [],
                neighborhood=row['neighborhood'],
                decision=row['decision'],
                vote_for=row['vote_for'],
                vote_against=row['vote_against'],
                sentiment=row['sentiment'],
                severity=row['severity'],
                confidence=row['confidence'],
                event_date=row['event_date'],
                source_title=row['source_title'],
                source_url=row['source_url'],
                source_type=row['source_type'],
                source_date=row['source_date']
            )
            signals.append(signal)

        has_more = (offset + limit) < total_count

        logger.info(f"Signal feed query returned {len(signals)} of {total_count} total signals")
        return SignalFeedResponse(
            signals=signals,
            total_count=total_count,
            has_more=has_more
        )

    except Exception as e:
        logger.error(f"Error retrieving signal feed: {e}", exc_info=True)
        raise


async def get_signal_by_id(
    db_pool: asyncpg.Pool,
    signal_id: int
) -> Optional[SignalResponse]:
    """
    Retrieve a single intelligence signal by ID.

    Joins with documents table to get source information.

    Args:
        db_pool: AsyncPG connection pool
        signal_id: ID of the signal to retrieve

    Returns:
        SignalResponse or None if not found
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
            WHERE isig.id = $1
        """

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, signal_id)

        if not row:
            logger.info(f"Signal {signal_id} not found")
            return None

        signal = SignalResponse(
            id=row['id'],
            document_id=row['document_id'],
            signal_type=row['signal_type'],
            summary=row['summary'],
            headline=row['headline'],
            addresses=row['addresses'] or [],
            neighborhood=row['neighborhood'],
            decision=row['decision'],
            vote_for=row['vote_for'],
            vote_against=row['vote_against'],
            sentiment=row['sentiment'],
            severity=row['severity'],
            confidence=row['confidence'],
            event_date=row['event_date'],
            source_title=row['source_title'],
            source_url=row['source_url'],
            source_type=row['source_type'],
            source_date=row['source_date']
        )

        logger.info(f"Retrieved signal {signal_id}")
        return signal

    except Exception as e:
        logger.error(f"Error retrieving signal {signal_id}: {e}", exc_info=True)
        raise


async def get_signals_for_parcel(
    db_pool: asyncpg.Pool,
    parcel_pid: str,
    radius_meters: float = 500
) -> List[SignalResponse]:
    """
    Retrieve intelligence signals near a parcel using spatial proximity.

    Uses PostGIS ST_DWithin to find signals within radius_meters of the parcel geometry.
    This bridges V1 (map/spatial) with V2 (intelligence analysis).

    Args:
        db_pool: AsyncPG connection pool
        parcel_pid: BC Land Title PID of the parcel
        radius_meters: Search radius in metres (default 500m)

    Returns:
        List of SignalResponse objects for nearby signals

    Raises:
        Exception: If parcel not found or query fails
    """

    try:
        logger.info(f"Finding signals within {radius_meters}m of parcel {parcel_pid}")

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
                d.published_date AS source_date,
                ROUND(ST_Distance(
                    ST_Transform(p.geom, 3005),
                    ST_Transform(ST_SetSRID(ST_MakePoint(
                        CAST(sig_geom ->> 'coordinates' ->> 0 AS FLOAT),
                        CAST(sig_geom ->> 'coordinates' ->> 1 AS FLOAT)
                    ), 4326), 3005)
                )::numeric, 1) AS distance_m
            FROM intelligence_signals isig
            JOIN documents d ON isig.document_id = d.id
            JOIN parcels p ON p.pid = $1
            WHERE
                isig.geom IS NOT NULL
                AND ST_DWithin(
                    ST_Transform(p.geom, 3005),
                    ST_Transform(isig.geom, 3005),
                    $2
                )
            ORDER BY isig.event_date DESC, distance_m ASC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, parcel_pid, radius_meters)

        if not rows:
            logger.info(f"No signals found within {radius_meters}m of parcel {parcel_pid}")
            return []

        signals = []
        for row in rows:
            signal = SignalResponse(
                id=row['id'],
                document_id=row['document_id'],
                signal_type=row['signal_type'],
                summary=row['summary'],
                headline=row['headline'],
                addresses=row['addresses'] or [],
                neighborhood=row['neighborhood'],
                decision=row['decision'],
                vote_for=row['vote_for'],
                vote_against=row['vote_against'],
                sentiment=row['sentiment'],
                severity=row['severity'],
                confidence=row['confidence'],
                event_date=row['event_date'],
                source_title=row['source_title'],
                source_url=row['source_url'],
                source_type=row['source_type'],
                source_date=row['source_date']
            )
            signals.append(signal)

        logger.info(f"Found {len(signals)} signals for parcel {parcel_pid}")
        return signals

    except Exception as e:
        logger.error(f"Error retrieving signals for parcel {parcel_pid}: {e}", exc_info=True)
        raise


async def get_signal_stats(
    db_pool: asyncpg.Pool
) -> Dict[str, Any]:
    """
    Retrieve dashboard statistics about intelligence signals.

    Returns aggregate counts by type, neighborhood, and severity.

    Args:
        db_pool: AsyncPG connection pool

    Returns:
        Dictionary with statistics including:
        - total_signals: Total signal count
        - by_type: Dict of signal type -> count
        - by_neighborhood: Dict of neighborhood -> count
        - by_severity: Dict of severity -> count
        - recent_count_7d: Signals from last 7 days
        - recent_count_30d: Signals from last 30 days
    """

    try:
        query = """
            SELECT
                COUNT(*) AS total_signals,
                (SELECT COUNT(*) FROM intelligence_signals WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') AS recent_7d,
                (SELECT COUNT(*) FROM intelligence_signals WHERE event_date >= CURRENT_DATE - INTERVAL '30 days') AS recent_30d
            FROM intelligence_signals
        """

        type_query = """
            SELECT signal_type, COUNT(*) as count
            FROM intelligence_signals
            GROUP BY signal_type
            ORDER BY count DESC
        """

        neighborhood_query = """
            SELECT neighborhood, COUNT(*) as count
            FROM intelligence_signals
            WHERE neighborhood IS NOT NULL
            GROUP BY neighborhood
            ORDER BY count DESC
        """

        severity_query = """
            SELECT severity, COUNT(*) as count
            FROM intelligence_signals
            GROUP BY severity
            ORDER BY count DESC
        """

        async with db_pool.acquire() as conn:
            stats_row = await conn.fetchrow(query)
            type_rows = await conn.fetch(type_query)
            neighborhood_rows = await conn.fetch(neighborhood_query)
            severity_rows = await conn.fetch(severity_query)

        result = {
            "total_signals": stats_row['total_signals'] if stats_row else 0,
            "recent_count_7d": stats_row['recent_7d'] if stats_row else 0,
            "recent_count_30d": stats_row['recent_30d'] if stats_row else 0,
            "by_type": {row['signal_type']: row['count'] for row in type_rows},
            "by_neighborhood": {row['neighborhood']: row['count'] for row in neighborhood_rows},
            "by_severity": {row['severity']: row['count'] for row in severity_rows}
        }

        logger.info("Retrieved signal statistics")
        return result

    except Exception as e:
        logger.error(f"Error retrieving signal statistics: {e}", exc_info=True)
        raise


async def get_neighborhoods(
    db_pool: asyncpg.Pool
) -> List[str]:
    """
    Retrieve distinct neighborhoods from intelligence signals.

    Used for populating filter dropdowns and neighborhood validation.

    Args:
        db_pool: AsyncPG connection pool

    Returns:
        Sorted list of neighborhood names
    """

    try:
        query = """
            SELECT DISTINCT neighborhood
            FROM intelligence_signals
            WHERE neighborhood IS NOT NULL
            ORDER BY neighborhood ASC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query)

        neighborhoods = [row['neighborhood'] for row in rows]

        logger.info(f"Retrieved {len(neighborhoods)} distinct neighborhoods")
        return neighborhoods

    except Exception as e:
        logger.error(f"Error retrieving neighborhoods: {e}", exc_info=True)
        raise


async def get_signals_geojson(
    db_pool: asyncpg.Pool,
    limit: int = 200,
    days: int = 90
) -> Dict[str, Any]:
    """
    Return intelligence signals as a GeoJSON FeatureCollection for map display.

    Only includes signals that have been geocoded (geom IS NOT NULL).
    Returns most recent signals within the given date window.
    """
    try:
        query = """
            SELECT
                isig.id,
                isig.signal_type,
                isig.headline,
                isig.summary,
                isig.neighborhood,
                isig.severity,
                isig.decision,
                isig.confidence,
                isig.event_date,
                isig.addresses,
                ST_X(isig.geom) AS lng,
                ST_Y(isig.geom) AS lat,
                d.title AS source_title,
                d.source_url,
                d.source_type
            FROM intelligence_signals isig
            JOIN documents d ON isig.document_id = d.id
            WHERE
                isig.geom IS NOT NULL
                AND isig.event_date >= CURRENT_DATE - $1 * INTERVAL '1 day'
            ORDER BY isig.event_date DESC
            LIMIT $2
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, days, limit)

        features = []
        for row in rows:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['lng']), float(row['lat'])]
                },
                "properties": {
                    "id": row['id'],
                    "signal_type": row['signal_type'],
                    "headline": row['headline'] or row['summary'][:60],
                    "summary": row['summary'],
                    "neighborhood": row['neighborhood'],
                    "severity": row['severity'],
                    "decision": row['decision'],
                    "confidence": float(row['confidence']),
                    "event_date": str(row['event_date']) if row['event_date'] else None,
                    "addresses": row['addresses'] or [],
                    "source_title": row['source_title'],
                    "source_url": row['source_url'],
                    "source_type": row['source_type'],
                }
            }
            features.append(feature)

        logger.info(f"Generated GeoJSON with {len(features)} signal features")
        return {
            "type": "FeatureCollection",
            "features": features
        }

    except Exception as e:
        logger.error(f"Error generating signals GeoJSON: {e}", exc_info=True)
        raise
