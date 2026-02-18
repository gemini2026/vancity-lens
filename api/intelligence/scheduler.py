"""
VCL-80 [DATA-004] Automated Daily Scraping Cron for VanCity Lens

Implements a cron-based scheduler for running multiple web scrapers on a schedule.
Supports background loop execution, manual triggering, and comprehensive run tracking.

Key components:
- CronSchedule: Simple cron parser for basic matching (hour, minute, day_of_week)
- ScraperSchedule: Configuration dataclass for a scraper's schedule
- ScraperResult: Result tracking dataclass for each run
- ScraperScheduler: Main scheduler class managing all scrapers

F05-006: Political risk score weekly refresh
F02-001 / F04-001: Ingestion SLA monitoring via data_source_freshness
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
import json

import asyncpg

logger = logging.getLogger(__name__)


class ScraperStatus(str, Enum):
    """Status of a scraper run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class CronSchedule:
    """
    Simple cron expression parser supporting:
    - minute: 0-59 or * (every)
    - hour: 0-23 or * (every)
    - day_of_month: 1-31 or * (every)
    - month: 1-12 or * (every)
    - day_of_week: 0-6 (0=Monday, 6=Sunday) or * (every)

    Examples:
    - "0 6 * * *" → every day at 6:00 AM
    - "0 */6 * * *" → every 6 hours at :00
    - "0 3 * * 1" → every Monday at 3:00 AM
    """

    cron_expr: str

    def __post_init__(self):
        """Parse and validate cron expression."""
        parts = self.cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron: expected 5 parts, got {len(parts)}")

        try:
            self.minute = self._parse_field(parts[0], 0, 59, "minute")
            self.hour = self._parse_field(parts[1], 0, 23, "hour")
            self.day_of_month = self._parse_field(parts[2], 1, 31, "day_of_month")
            self.month = self._parse_field(parts[3], 1, 12, "month")
            self.day_of_week = self._parse_field(parts[4], 0, 6, "day_of_week")
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{self.cron_expr}': {e}")

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int, name: str) -> set:
        """Parse a cron field and return set of valid values."""
        if field == "*":
            return set(range(min_val, max_val + 1))

        # Handle */n (every n)
        if field.startswith("*/"):
            try:
                step = int(field[2:])
                return set(range(min_val, max_val + 1, step))
            except ValueError:
                raise ValueError(f"Invalid step in {name}: {field}")

        # Handle comma-separated values
        if "," in field:
            values = set()
            for part in field.split(","):
                part = part.strip()
                if part.isdigit():
                    val = int(part)
                    if min_val <= val <= max_val:
                        values.add(val)
                    else:
                        raise ValueError(f"{name} out of range: {val}")
                else:
                    raise ValueError(f"Invalid {name} value: {part}")
            return values

        # Handle single digit
        if field.isdigit():
            val = int(field)
            if min_val <= val <= max_val:
                return {val}
            else:
                raise ValueError(f"{name} out of range: {val}")

        raise ValueError(f"Invalid {name} format: {field}")

    def should_run(self, dt: Optional[datetime] = None) -> bool:
        """Check if this schedule should run at the given datetime."""
        if dt is None:
            dt = datetime.now()

        # Check all fields match
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day_of_month
            and dt.month in self.month
            and dt.weekday() in self.day_of_week  # weekday() 0=Monday, 6=Sunday
        )


@dataclass
class ScraperSchedule:
    """Configuration for a scraper's schedule."""

    scraper_name: str
    cron_expression: str
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    max_retries: int = 3
    timeout_seconds: int = 300

    def __post_init__(self):
        """Validate cron expression."""
        self.cron = CronSchedule(self.cron_expression)


@dataclass
class ScraperResult:
    """Result of a single scraper run."""

    scraper_name: str
    started_at: datetime
    completed_at: datetime
    documents_found: int
    documents_new: int
    documents_skipped: int
    errors: List[str] = field(default_factory=list)
    status: ScraperStatus = ScraperStatus.SUCCESS

    @property
    def duration_seconds(self) -> float:
        """Calculate run duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scraper_name": self.scraper_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "documents_found": self.documents_found,
            "documents_new": self.documents_new,
            "documents_skipped": self.documents_skipped,
            "errors": self.errors,
            "status": self.status.value,
        }


class ScraperScheduler:
    """
    Main scheduler managing multiple scrapers with cron-based execution.

    Features:
    - Register scrapers with cron schedules
    - Check if scraper should run based on cron
    - Execute individual scrapers with timeout and error handling
    - Run all due scrapers
    - Background loop that checks every minute
    - Track run history in database
    """

    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize scheduler with database pool.

        Args:
            db_pool: asyncpg connection pool for run tracking
        """
        self.db_pool = db_pool
        self.scrapers: Dict[str, tuple] = {}  # {name: (func, ScraperSchedule)}
        self.background_task: Optional[asyncio.Task] = None
        self._running = False

        # Register default scrapers
        self._register_defaults()

    def _register_defaults(self):
        """Register default scrapers with standard schedules."""
        # These are placeholders - actual scraper functions come from intelligence module
        # They'll be set via register_scraper() in real usage
        default_schedules = {
            "council": "0 6 * * *",  # daily 6am
            "dpb": "0 7 * * *",  # daily 7am
            "rezoning": "0 8 * * *",  # daily 8am
            "news": "0 */6 * * *",  # every 6 hours
            "opendata": "0 3 * * 1",  # weekly Monday 3am
            "political_risk": "0 2 * * 0",  # weekly Sunday 2am UTC (F05-006)
            "undervalued": "0 15 * * 1",  # weekly Monday 3pm UTC (8am Pacific)
            "freshness_check": "0 */4 * * *",  # every 4 hours (F02-001/F04-001)
        }

        for name, cron in default_schedules.items():
            schedule = ScraperSchedule(
                scraper_name=name,
                cron_expression=cron,
                enabled=True,
                max_retries=3,
                timeout_seconds=300,
            )
            # Store with None function (will be set later)
            self.scrapers[name] = (None, schedule)

    def register_scraper(
        self,
        name: str,
        func: Callable,
        cron_expr: str,
        enabled: bool = True,
        max_retries: int = 3,
        timeout_seconds: int = 300,
    ):
        """
        Register a scraper with schedule.

        Args:
            name: Unique scraper name
            func: Async function(db_pool, start_date, end_date) -> dict
            cron_expr: Cron expression (e.g., "0 6 * * *")
            enabled: Whether scraper is enabled
            max_retries: Max retry attempts on failure
            timeout_seconds: Timeout for scraper execution
        """
        schedule = ScraperSchedule(
            scraper_name=name,
            cron_expression=cron_expr,
            enabled=enabled,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        self.scrapers[name] = (func, schedule)
        logger.info(f"Registered scraper '{name}' with schedule '{cron_expr}'")

    def should_run(self, name: str, dt: Optional[datetime] = None) -> bool:
        """
        Check if a scraper should run at the given datetime.

        Args:
            name: Scraper name
            dt: Datetime to check (default: now)

        Returns:
            True if scraper is due to run
        """
        if name not in self.scrapers:
            return False

        func, schedule = self.scrapers[name]
        if not schedule.enabled or func is None:
            return False

        return schedule.cron.should_run(dt)

    async def run_scraper(self, name: str) -> ScraperResult:
        """
        Execute a single scraper with timeout, error handling, and dedup.

        Args:
            name: Scraper name

        Returns:
            ScraperResult with execution details
        """
        if name not in self.scrapers:
            raise ValueError(f"Unknown scraper: {name}")

        func, schedule = self.scrapers[name]
        if func is None:
            raise ValueError(f"Scraper '{name}' has no function registered")

        started_at = datetime.now()
        completed_at = None
        documents_found = 0
        documents_new = 0
        documents_skipped = 0
        errors: List[str] = []
        status = ScraperStatus.SUCCESS

        try:
            # Calculate date range (last 7 days by default)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

            logger.info(f"Starting scraper '{name}'")

            # Execute with timeout
            result = await asyncio.wait_for(
                func(self.db_pool, start_date, end_date),
                timeout=schedule.timeout_seconds,
            )

            # Extract stats from result dict
            documents_found = result.get("documents_found", 0)
            documents_new = result.get("documents_new", 0)
            documents_skipped = result.get("documents_skipped", 0)

            logger.info(
                f"Scraper '{name}' completed: "
                f"{documents_found} found, {documents_new} new, {documents_skipped} skipped"
            )

            # Record successful ingestion for freshness monitoring (F02-001)
            try:
                from ..retrieval_logging import record_ingestion_success

                await record_ingestion_success(self.db_pool, name)
            except Exception as freshness_err:
                logger.debug(
                    "Failed to record freshness for '%s': %s", name, freshness_err
                )

        except asyncio.TimeoutError:
            error_msg = f"Scraper '{name}' timed out after {schedule.timeout_seconds}s"
            logger.error(error_msg)
            errors.append(error_msg)
            status = ScraperStatus.FAILED
        except Exception as e:
            error_msg = f"Scraper '{name}' failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
            status = ScraperStatus.FAILED

        completed_at = datetime.now()

        # Create result object
        result_obj = ScraperResult(
            scraper_name=name,
            started_at=started_at,
            completed_at=completed_at,
            documents_found=documents_found,
            documents_new=documents_new,
            documents_skipped=documents_skipped,
            errors=errors,
            status=status,
        )

        # Store in database
        await self._store_run(result_obj)

        # Update schedule
        self.scrapers[name][1].last_run = completed_at
        self.scrapers[name][1].next_run = self._calculate_next_run(name, completed_at)

        return result_obj

    async def run_all_due(self) -> List[ScraperResult]:
        """
        Run all scrapers that are due based on their cron schedule.

        Returns:
            List of ScraperResult objects
        """
        results = []
        dt = datetime.now()

        for name in self.scrapers:
            try:
                if self.should_run(name, dt):
                    result = await self.run_scraper(name)
                    results.append(result)
            except Exception as e:
                logger.error(
                    f"Error checking/running scraper '{name}': {e}", exc_info=True
                )

        return results

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all registered scrapers.

        Returns:
            Dict with scraper statuses
        """
        status = {
            "running": self._running,
            "total_scrapers": len(self.scrapers),
            "scrapers": {},
        }

        for name, (func, schedule) in self.scrapers.items():
            status["scrapers"][name] = {
                "enabled": schedule.enabled,
                "cron": schedule.cron_expression,
                "last_run": schedule.last_run.isoformat()
                if schedule.last_run
                else None,
                "next_run": schedule.next_run.isoformat()
                if schedule.next_run
                else None,
                "timeout_seconds": schedule.timeout_seconds,
                "max_retries": schedule.max_retries,
                "has_function": func is not None,
            }

        return status

    async def start_background_loop(self):
        """
        Start background asyncio task that checks every minute for due scrapers.
        Can be safely called even if already running.
        """
        if self._running:
            logger.info("Scheduler already running")
            return

        self._running = True
        logger.info("Starting scheduler background loop")
        self.background_task = asyncio.create_task(self._background_loop())

    async def _background_loop(self):
        """Background task that runs every minute."""
        # Counter to track freshness check intervals (every 240 minutes = 4 hours)
        tick_count = 0
        FRESHNESS_CHECK_INTERVAL_TICKS = 240  # minutes

        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break

                tick_count += 1

                results = await self.run_all_due()
                if results:
                    logger.info(f"Background loop ran {len(results)} scrapers")

                # Run freshness SLA check every 4 hours (F02-001/F04-001)
                if tick_count % FRESHNESS_CHECK_INTERVAL_TICKS == 0:
                    try:
                        await self.check_data_freshness_sla()
                    except Exception as sla_err:
                        logger.error(
                            "Freshness SLA check failed: %s", sla_err, exc_info=True
                        )

            except Exception as e:
                logger.error(f"Error in background loop: {e}", exc_info=True)

    async def stop(self):
        """
        Stop the background loop.
        Can be safely called even if not running.
        """
        if not self._running:
            logger.info("Scheduler not running")
            return

        logger.info("Stopping scheduler background loop")
        self._running = False

        if self.background_task:
            try:
                await asyncio.wait_for(self.background_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("Background task did not stop within timeout")
                self.background_task.cancel()
            except Exception as e:
                logger.warning(f"Error waiting for background task: {e}")

        self.background_task = None

    async def check_data_freshness_sla(self) -> list:
        """Check all data sources for SLA violations (F02-001 / F04-001).

        Queries the ``data_source_freshness`` table and logs a WARNING for
        any source whose ``last_successful_retrieval`` exceeds its
        ``expected_cadence_hours`` by 50%.

        Returns:
            List of dicts describing stale sources (for programmatic use).
        """
        stale_sources: list = []
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT source_id,
                           source_name,
                           expected_cadence_hours,
                           last_successful_retrieval,
                           EXTRACT(EPOCH FROM (NOW() - last_successful_retrieval)) / 3600.0
                               AS hours_since_last
                    FROM data_source_freshness
                    ORDER BY source_id
                """)

                for row in rows:
                    source_id = row["source_id"]
                    source_name = row["source_name"]
                    cadence_h = row["expected_cadence_hours"]
                    last_retrieval = row["last_successful_retrieval"]
                    hours_since = row["hours_since_last"]

                    if last_retrieval is None:
                        # Never retrieved — always stale
                        logger.warning(
                            "DATA FRESHNESS SLA BREACH: %s (%s) has NEVER been retrieved "
                            "(expected every %dh)",
                            source_name,
                            source_id,
                            cadence_h,
                        )
                        stale_sources.append(
                            {
                                "source_id": source_id,
                                "source_name": source_name,
                                "expected_cadence_hours": cadence_h,
                                "hours_since_last": None,
                                "breach_ratio": None,
                            }
                        )
                        continue

                    threshold = cadence_h * 1.5  # 50% grace period
                    if hours_since > threshold:
                        breach_ratio = round(hours_since / cadence_h, 2)
                        logger.warning(
                            "DATA FRESHNESS SLA BREACH: %s (%s) last retrieved %.1fh ago "
                            "(expected every %dh, threshold %.0fh, breach ratio %.2fx)",
                            source_name,
                            source_id,
                            hours_since,
                            cadence_h,
                            threshold,
                            breach_ratio,
                        )
                        stale_sources.append(
                            {
                                "source_id": source_id,
                                "source_name": source_name,
                                "expected_cadence_hours": cadence_h,
                                "hours_since_last": round(hours_since, 1),
                                "breach_ratio": breach_ratio,
                            }
                        )

            if stale_sources:
                logger.warning(
                    "Data freshness check: %d/%d sources breaching SLA",
                    len(stale_sources),
                    len(rows),
                )
            else:
                logger.info(
                    "Data freshness check: all %d sources within SLA", len(rows)
                )

        except Exception as exc:
            logger.error("Failed to check data freshness SLA: %s", exc, exc_info=True)

        return stale_sources

    async def _store_run(self, result: ScraperResult) -> None:
        """Store run result in database."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO scraper_runs (
                        scraper_name, started_at, completed_at, status,
                        documents_found, documents_new, documents_skipped, errors, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    result.scraper_name,
                    result.started_at,
                    result.completed_at,
                    result.status.value,
                    result.documents_found,
                    result.documents_new,
                    result.documents_skipped,
                    json.dumps(result.errors),
                    datetime.now(),
                )
        except Exception as e:
            logger.error(f"Failed to store run result for '{result.scraper_name}': {e}")

    def _calculate_next_run(self, name: str, last_run: datetime) -> datetime:
        """Calculate the next scheduled run time for a scraper."""
        if name not in self.scrapers:
            return last_run

        func, schedule = self.scrapers[name]
        cron = schedule.cron

        # Check every minute for the next 30 days
        check_time = last_run + timedelta(minutes=1)
        max_check = last_run + timedelta(days=30)

        while check_time <= max_check:
            if cron.should_run(check_time):
                return check_time
            check_time += timedelta(minutes=1)

        # Fallback: return last_run + 1 day if no match found
        return last_run + timedelta(days=1)
