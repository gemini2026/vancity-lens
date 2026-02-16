"""
Alert system and watchlist management for VanCity Lens (VCL-38 / INTEL-006).

This module provides:
- Watchlist CRUD operations
- Rule matching and evaluation
- Alert generation from signals
- Alert retrieval and management
- Read/unread status tracking
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert type categories."""
    SIGNAL_MATCH = "signal_match"
    STAGE_TRANSITION = "stage_transition"
    UNDERVALUED_MATCH = "undervalued_match"


class RuleType(str, Enum):
    """Types of watchlist rules."""
    NEIGHBORHOOD = "neighborhood"
    ADDRESS = "address"
    ZONING = "zoning"
    SIGNAL_TYPE = "signal_type"
    KEYWORD = "keyword"
    SEVERITY = "severity"
    PIPELINE_STAGE = "pipeline_stage"
    APPLICATION_TYPE = "application_type"
    HEIGHT_RANGE = "height_range"
    UNIT_RANGE = "unit_range"
    GEOGRAPHIC_SCOPE = "geographic_scope"
    CHANGE_TYPE = "change_type"
    UNDERVALUED_DISCOUNT = "undervalued_discount"
    UNDERVALUED_LOT_AREA = "undervalued_lot_area"
    UNDERVALUED_TOD_TIER = "undervalued_tod_tier"
    PID = "pid"


class WatchlistRule(BaseModel):
    """A single rule in a watchlist."""
    rule_type: RuleType
    rule_value: str

    class Config:
        from_attributes = True


class WatchlistCreate(BaseModel):
    """Request model for creating a watchlist."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    rules: List[WatchlistRule] = Field(default_factory=list)


class WatchlistUpdate(BaseModel):
    """Request model for updating a watchlist."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    rules: Optional[List[WatchlistRule]] = None


class Watchlist(BaseModel):
    """Response model for a watchlist."""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    is_active: bool
    rules: List[WatchlistRule] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    """Request model for creating an alert."""
    watchlist_id: int
    signal_id: int
    alert_type: AlertType = AlertType.SIGNAL_MATCH
    headline: str
    summary: Optional[str] = None
    severity: Severity


class Alert(BaseModel):
    """Response model for an alert."""
    id: int
    watchlist_id: int
    signal_id: int
    alert_type: AlertType
    headline: str
    summary: Optional[str]
    severity: Severity
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertCount(BaseModel):
    """Alert count summary."""
    total: int
    unread: int


# ────────────────────────────────────────────────────────────────────────────
# WatchlistManager
# ────────────────────────────────────────────────────────────────────────────

class WatchlistManager:
    """Manages watchlist CRUD operations and rule storage."""

    @staticmethod
    async def create_watchlist(
        db_pool: asyncpg.Pool,
        user_id: int,
        name: str,
        description: Optional[str] = None,
        rules: Optional[List[WatchlistRule]] = None
    ) -> Watchlist:
        """
        Create a new watchlist with rules.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of the user creating the watchlist
            name: Name of the watchlist
            description: Optional description
            rules: List of WatchlistRule objects

        Returns:
            Created Watchlist object

        Raises:
            Exception: If database operation fails
        """
        try:
            rules = rules or []

            async with db_pool.acquire() as conn:
                # Insert watchlist
                watchlist_row = await conn.fetchrow(
                    """
                    INSERT INTO watchlists (user_id, name, description, created_at, updated_at)
                    VALUES ($1, $2, $3, NOW(), NOW())
                    RETURNING id, user_id, name, description, is_active, created_at, updated_at
                    """,
                    user_id, name, description
                )

                watchlist_id = watchlist_row['id']

                # Insert rules
                for rule in rules:
                    await conn.execute(
                        """
                        INSERT INTO watchlist_rules (watchlist_id, rule_type, rule_value, created_at)
                        VALUES ($1, $2, $3, NOW())
                        """,
                        watchlist_id, rule.rule_type.value, rule.rule_value
                    )

            # Fetch rules to return complete watchlist
            rules_fetched = await WatchlistManager.get_watchlist_rules(db_pool, watchlist_id)

            watchlist = Watchlist(
                id=watchlist_row['id'],
                user_id=watchlist_row['user_id'],
                name=watchlist_row['name'],
                description=watchlist_row['description'],
                is_active=watchlist_row['is_active'],
                rules=rules_fetched,
                created_at=watchlist_row['created_at'],
                updated_at=watchlist_row['updated_at']
            )

            logger.info(f"Created watchlist {watchlist_id} for user {user_id}")
            return watchlist

        except Exception as e:
            logger.error(f"Error creating watchlist: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_watchlists(
        db_pool: asyncpg.Pool,
        user_id: int,
        active_only: bool = True
    ) -> List[Watchlist]:
        """
        Retrieve all watchlists for a user.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of the user
            active_only: Only return active watchlists

        Returns:
            List of Watchlist objects
        """
        try:
            query = "SELECT * FROM watchlists WHERE user_id = $1"
            params = [user_id]

            if active_only:
                query += " AND is_active = true"

            query += " ORDER BY created_at DESC"

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            watchlists = []
            for row in rows:
                rules = await WatchlistManager.get_watchlist_rules(db_pool, row['id'])
                watchlist = Watchlist(
                    id=row['id'],
                    user_id=row['user_id'],
                    name=row['name'],
                    description=row['description'],
                    is_active=row['is_active'],
                    rules=rules,
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                watchlists.append(watchlist)

            logger.info(f"Retrieved {len(watchlists)} watchlists for user {user_id}")
            return watchlists

        except Exception as e:
            logger.error(f"Error retrieving watchlists for user {user_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_watchlist(
        db_pool: asyncpg.Pool,
        watchlist_id: int
    ) -> Optional[Watchlist]:
        """
        Retrieve a specific watchlist by ID.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist

        Returns:
            Watchlist object or None if not found
        """
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM watchlists WHERE id = $1",
                    watchlist_id
                )

            if not row:
                logger.info(f"Watchlist {watchlist_id} not found")
                return None

            rules = await WatchlistManager.get_watchlist_rules(db_pool, watchlist_id)

            watchlist = Watchlist(
                id=row['id'],
                user_id=row['user_id'],
                name=row['name'],
                description=row['description'],
                is_active=row['is_active'],
                rules=rules,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

            logger.info(f"Retrieved watchlist {watchlist_id}")
            return watchlist

        except Exception as e:
            logger.error(f"Error retrieving watchlist {watchlist_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_watchlist_rules(
        db_pool: asyncpg.Pool,
        watchlist_id: int
    ) -> List[WatchlistRule]:
        """
        Retrieve all rules for a watchlist.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist

        Returns:
            List of WatchlistRule objects
        """
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT rule_type, rule_value FROM watchlist_rules WHERE watchlist_id = $1 ORDER BY id",
                    watchlist_id
                )

            rules = [
                WatchlistRule(rule_type=row['rule_type'], rule_value=row['rule_value'])
                for row in rows
            ]

            return rules

        except Exception as e:
            logger.error(f"Error retrieving rules for watchlist {watchlist_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def update_watchlist(
        db_pool: asyncpg.Pool,
        watchlist_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        rules: Optional[List[WatchlistRule]] = None
    ) -> Watchlist:
        """
        Update a watchlist and optionally its rules.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist to update
            name: New name (optional)
            description: New description (optional)
            rules: New rules list (replaces existing if provided)

        Returns:
            Updated Watchlist object

        Raises:
            Exception: If watchlist not found or database operation fails
        """
        try:
            async with db_pool.acquire() as conn:
                # Update watchlist metadata
                update_parts = ["updated_at = NOW()"]
                params = []

                if name is not None:
                    update_parts.append(f"name = ${len(params) + 1}")
                    params.append(name)

                if description is not None:
                    update_parts.append(f"description = ${len(params) + 1}")
                    params.append(description)

                params.append(watchlist_id)

                watchlist_row = await conn.fetchrow(
                    f"""
                    UPDATE watchlists
                    SET {', '.join(update_parts)}
                    WHERE id = ${len(params)}
                    RETURNING id, user_id, name, description, is_active, created_at, updated_at
                    """,
                    *params
                )

                if not watchlist_row:
                    raise ValueError(f"Watchlist {watchlist_id} not found")

                # Update rules if provided
                if rules is not None:
                    # Delete existing rules
                    await conn.execute(
                        "DELETE FROM watchlist_rules WHERE watchlist_id = $1",
                        watchlist_id
                    )

                    # Insert new rules
                    for rule in rules:
                        await conn.execute(
                            """
                            INSERT INTO watchlist_rules (watchlist_id, rule_type, rule_value, created_at)
                            VALUES ($1, $2, $3, NOW())
                            """,
                            watchlist_id, rule.rule_type.value, rule.rule_value
                        )

            # Fetch updated rules
            rules_fetched = await WatchlistManager.get_watchlist_rules(db_pool, watchlist_id)

            watchlist = Watchlist(
                id=watchlist_row['id'],
                user_id=watchlist_row['user_id'],
                name=watchlist_row['name'],
                description=watchlist_row['description'],
                is_active=watchlist_row['is_active'],
                rules=rules_fetched,
                created_at=watchlist_row['created_at'],
                updated_at=watchlist_row['updated_at']
            )

            logger.info(f"Updated watchlist {watchlist_id}")
            return watchlist

        except Exception as e:
            logger.error(f"Error updating watchlist {watchlist_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def delete_watchlist(
        db_pool: asyncpg.Pool,
        watchlist_id: int
    ) -> bool:
        """
        Delete a watchlist and all associated rules and alerts.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            async with db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM watchlists WHERE id = $1",
                    watchlist_id
                )

            # Check if any rows were affected
            deleted = result != "DELETE 0"

            if deleted:
                logger.info(f"Deleted watchlist {watchlist_id}")
            else:
                logger.info(f"Watchlist {watchlist_id} not found")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting watchlist {watchlist_id}: {e}", exc_info=True)
            raise


# ────────────────────────────────────────────────────────────────────────────
# AlertEngine
# ────────────────────────────────────────────────────────────────────────────

class AlertEngine:
    """Evaluates signals against watchlist rules and manages alerts."""

    @staticmethod
    async def evaluate_signal(
        db_pool: asyncpg.Pool,
        signal: Dict[str, Any]
    ) -> List[int]:
        """
        Evaluate a signal against all active watchlists and create matching alerts.

        Args:
            db_pool: AsyncPG connection pool
            signal: Signal dictionary with keys like 'signal_type', 'neighborhood', etc.

        Returns:
            List of created alert IDs

        Raises:
            Exception: If database operation fails
        """
        try:
            signal_id = signal.get('id')
            if not signal_id:
                logger.warning("Signal missing 'id' field, skipping alert evaluation")
                return []

            # Get all active watchlists
            async with db_pool.acquire() as conn:
                watchlists = await conn.fetch(
                    "SELECT id FROM watchlists WHERE is_active = true"
                )

            created_alert_ids = []

            for watchlist_row in watchlists:
                watchlist_id = watchlist_row['id']

                # Get rules for this watchlist
                rules = await WatchlistManager.get_watchlist_rules(db_pool, watchlist_id)

                # Check if signal matches any rule
                if AlertEngine.match_rules(signal, rules):
                    # Check if alert already exists for this signal+watchlist
                    existing = await AlertEngine._alert_exists(
                        db_pool, watchlist_id, signal_id
                    )

                    if not existing:
                        # Create alert
                        alert_id = await AlertEngine.create_alert(
                            db_pool,
                            watchlist_id=watchlist_id,
                            signal_id=signal_id,
                            alert_type="signal_match",
                            headline=signal.get('headline') or signal.get('summary', 'New Signal'),
                            summary=signal.get('summary'),
                            severity=signal.get('severity', 'info')
                        )
                        created_alert_ids.append(alert_id)

            logger.info(f"Signal {signal_id} matched {len(created_alert_ids)} watchlists")
            return created_alert_ids

        except Exception as e:
            logger.error(f"Error evaluating signal: {e}", exc_info=True)
            raise

    @staticmethod
    def match_rules(
        signal: Dict[str, Any],
        rules: List[WatchlistRule]
    ) -> bool:
        """
        Check if a signal matches any of the provided rules (OR logic).

        Args:
            signal: Signal dictionary
            rules: List of WatchlistRule objects

        Returns:
            True if signal matches at least one rule, False otherwise
        """
        if not rules:
            return True  # Empty rules match all signals

        for rule in rules:
            if AlertEngine.match_rule(signal, rule):
                return True

        return False

    @staticmethod
    def match_rule(
        signal: Dict[str, Any],
        rule: WatchlistRule
    ) -> bool:
        """
        Check if a signal matches a single rule.

        Args:
            signal: Signal dictionary
            rule: WatchlistRule object

        Returns:
            True if signal matches the rule, False otherwise
        """
        rule_type = rule.rule_type
        rule_value = rule.rule_value.lower()

        if rule_type == RuleType.NEIGHBORHOOD:
            signal_neighborhood = signal.get('neighborhood', '').lower()
            return rule_value in signal_neighborhood or signal_neighborhood in rule_value

        elif rule_type == RuleType.ADDRESS:
            addresses = signal.get('addresses', [])
            return any(rule_value in addr.lower() for addr in addresses)

        elif rule_type == RuleType.ZONING:
            # Match zoning_from or zoning_to
            zoning_from = (signal.get('zoning_from') or '').lower()
            zoning_to = (signal.get('zoning_to') or '').lower()
            return rule_value in zoning_from or rule_value in zoning_to

        elif rule_type == RuleType.SIGNAL_TYPE:
            signal_type = signal.get('signal_type', '').lower()
            return rule_value == signal_type

        elif rule_type == RuleType.KEYWORD:
            headline = (signal.get('headline') or '').lower()
            summary = (signal.get('summary') or '').lower()
            return rule_value in headline or rule_value in summary

        elif rule_type == RuleType.SEVERITY:
            signal_severity = signal.get('severity', '').lower()
            return rule_value == signal_severity

        elif rule_type == RuleType.PIPELINE_STAGE:
            pipeline_stage = (signal.get("pipeline_stage") or "").lower()
            return rule_value == pipeline_stage

        elif rule_type == RuleType.APPLICATION_TYPE:
            app_type = (signal.get("application_type") or "").lower()
            return rule_value == app_type

        elif rule_type == RuleType.HEIGHT_RANGE:
            try:
                parts = rule_value.split("-")
                range_min, range_max = int(parts[0]), int(parts[1])
                storeys = signal.get("proposed_storeys") or signal.get("height_after")
                if storeys is None:
                    return False
                return range_min <= int(storeys) <= range_max
            except (ValueError, IndexError):
                return False

        elif rule_type == RuleType.UNIT_RANGE:
            try:
                parts = rule_value.split("-")
                range_min, range_max = int(parts[0]), int(parts[1])
                units = signal.get("unit_count") or signal.get("proposed_units")
                if units is None:
                    return False
                return range_min <= int(units) <= range_max
            except (ValueError, IndexError):
                return False

        elif rule_type == RuleType.GEOGRAPHIC_SCOPE:
            geo_scope = (signal.get("geographic_scope") or "").lower()
            if geo_scope == "citywide":
                return rule_value == "citywide"
            affected = [a.lower() for a in (signal.get("affected_areas") or [])]
            return rule_value in affected

        elif rule_type == RuleType.CHANGE_TYPE:
            change_type = (signal.get("change_type") or "").lower()
            return rule_value == change_type

        elif rule_type == RuleType.UNDERVALUED_DISCOUNT:
            try:
                min_discount = float(rule_value)
                discount = signal.get("discount_pct", 0)
                return float(discount) >= min_discount
            except (ValueError, TypeError):
                return False

        elif rule_type == RuleType.UNDERVALUED_LOT_AREA:
            try:
                min_area = float(rule_value)
                area = signal.get("lot_area_sqft", 0)
                return float(area) >= min_area
            except (ValueError, TypeError):
                return False

        elif rule_type == RuleType.UNDERVALUED_TOD_TIER:
            try:
                tier_val = int(rule_value)
                signal_tier = signal.get("tod_tier")
                if signal_tier is None:
                    return False
                return int(signal_tier) == tier_val
            except (ValueError, TypeError):
                return False

        elif rule_type == RuleType.PID:
            # Match PID against the signal's affected_areas list
            affected = signal.get("affected_areas") or []
            return any(rule_value == pid.lower() for pid in affected)

        else:
            logger.warning(f"Unknown rule type: {rule_type}")
            return False

    @staticmethod
    async def _alert_exists(
        db_pool: asyncpg.Pool,
        watchlist_id: int,
        signal_id: int
    ) -> bool:
        """
        Check if an alert already exists for a signal+watchlist pair.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist
            signal_id: ID of the signal

        Returns:
            True if alert exists, False otherwise
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM alerts
                WHERE watchlist_id = $1 AND signal_id = $2
                LIMIT 1
                """,
                watchlist_id, signal_id
            )

        return row is not None

    @staticmethod
    async def create_alert(
        db_pool: asyncpg.Pool,
        watchlist_id: int,
        signal_id: int,
        alert_type: str,
        headline: str,
        summary: Optional[str],
        severity: str
    ) -> int:
        """
        Create a new alert.

        Args:
            db_pool: AsyncPG connection pool
            watchlist_id: ID of the watchlist
            signal_id: ID of the signal
            alert_type: Type of alert
            headline: Alert headline
            summary: Alert summary
            severity: Severity level

        Returns:
            ID of the created alert

        Raises:
            Exception: If database operation fails
        """
        try:
            async with db_pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    INSERT INTO alerts
                    (watchlist_id, signal_id, alert_type, headline, summary, severity, is_read, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, false, NOW())
                    RETURNING id
                    """,
                    watchlist_id, signal_id, alert_type, headline, summary, severity
                )

            alert_id = result['id']
            logger.info(f"Created alert {alert_id} for watchlist {watchlist_id}")
            return alert_id

        except Exception as e:
            logger.error(f"Error creating alert: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_alerts(
        db_pool: asyncpg.Pool,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Alert]:
        """
        Retrieve alerts for a user with optional filtering.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of the user
            unread_only: Only return unread alerts
            limit: Maximum number of alerts to return (max 100)
            offset: Pagination offset

        Returns:
            List of Alert objects
        """
        try:
            limit = min(limit, 100)
            offset = max(offset, 0)

            query = """
                SELECT a.* FROM alerts a
                JOIN watchlists w ON a.watchlist_id = w.id
                WHERE w.user_id = $1
            """
            params = [user_id]

            if unread_only:
                query += " AND a.is_read = false"

            query += " ORDER BY a.created_at DESC LIMIT $" + str(len(params) + 1) + " OFFSET $" + str(len(params) + 2)
            params.extend([limit, offset])

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            alerts = [
                Alert(
                    id=row['id'],
                    watchlist_id=row['watchlist_id'],
                    signal_id=row['signal_id'],
                    alert_type=row['alert_type'],
                    headline=row['headline'],
                    summary=row['summary'],
                    severity=row['severity'],
                    is_read=row['is_read'],
                    created_at=row['created_at'],
                    read_at=row['read_at']
                )
                for row in rows
            ]

            logger.info(f"Retrieved {len(alerts)} alerts for user {user_id}")
            return alerts

        except Exception as e:
            logger.error(f"Error retrieving alerts for user {user_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_read(
        db_pool: asyncpg.Pool,
        alert_id: int
    ) -> bool:
        """
        Mark an alert as read.

        Args:
            db_pool: AsyncPG connection pool
            alert_id: ID of the alert

        Returns:
            True if updated, False if not found
        """
        try:
            async with db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE alerts
                    SET is_read = true, read_at = NOW()
                    WHERE id = $1
                    """,
                    alert_id
                )

            updated = result != "UPDATE 0"

            if updated:
                logger.info(f"Marked alert {alert_id} as read")
            else:
                logger.info(f"Alert {alert_id} not found")

            return updated

        except Exception as e:
            logger.error(f"Error marking alert {alert_id} as read: {e}", exc_info=True)
            raise

    @staticmethod
    async def mark_all_read(
        db_pool: asyncpg.Pool,
        user_id: int
    ) -> int:
        """
        Mark all alerts for a user as read.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of the user

        Returns:
            Number of alerts marked as read
        """
        try:
            async with db_pool.acquire() as conn:
                # Update all unread alerts for user's watchlists
                result = await conn.execute(
                    """
                    UPDATE alerts a
                    SET is_read = true, read_at = NOW()
                    FROM watchlists w
                    WHERE a.watchlist_id = w.id
                    AND w.user_id = $1
                    AND a.is_read = false
                    """,
                    user_id
                )

            # Parse the result string "UPDATE n"
            count = 0
            if result and result.startswith("UPDATE"):
                try:
                    count = int(result.split()[-1])
                except (ValueError, IndexError):
                    pass

            logger.info(f"Marked {count} alerts as read for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Error marking all alerts as read for user {user_id}: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_alert_count(
        db_pool: asyncpg.Pool,
        user_id: int,
        unread_only: bool = True
    ) -> AlertCount:
        """
        Get alert counts for a user.

        Args:
            db_pool: AsyncPG connection pool
            user_id: ID of the user
            unread_only: If True, return only unread count; if False, return both

        Returns:
            AlertCount object with total and unread counts
        """
        try:
            async with db_pool.acquire() as conn:
                # Get total count
                total_row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count FROM alerts a
                    JOIN watchlists w ON a.watchlist_id = w.id
                    WHERE w.user_id = $1
                    """,
                    user_id
                )

                # Get unread count
                unread_row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count FROM alerts a
                    JOIN watchlists w ON a.watchlist_id = w.id
                    WHERE w.user_id = $1 AND a.is_read = false
                    """,
                    user_id
                )

            total = total_row['count'] if total_row else 0
            unread = unread_row['count'] if unread_row else 0

            logger.info(f"Alert counts for user {user_id}: total={total}, unread={unread}")
            return AlertCount(total=total, unread=unread)

        except Exception as e:
            logger.error(f"Error getting alert counts for user {user_id}: {e}", exc_info=True)
            raise
