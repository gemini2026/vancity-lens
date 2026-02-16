"""
Supply Pipeline Tracking for VanCity Lens.

This module tracks residential development projects from rezoning application
through completion, providing insights into housing supply by neighborhood
and development stage.

Features:
- Add/update pipeline entries for development projects
- Track stage transitions with audit trail
- Query pipeline by neighborhood, stage, or date
- Compute supply statistics and forecasts
- Ingest pipeline data from intelligence signals
"""

import logging
import re
from datetime import date, datetime
from enum import Enum
from typing import Optional, List

import asyncpg
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# ENUMS AND MODELS
# ════════════════════════════════════════════════════════════════════════════

class PipelineStage(str, Enum):
    """Development stages in the supply pipeline."""
    ENQUIRY = "enquiry"
    APPLICATION_SUBMITTED = "application_submitted"
    UNDER_STAFF_REVIEW = "under_staff_review"
    REFERRED_TO_PUBLIC_HEARING = "referred_to_public_hearing"
    APPROVED = "approved"
    UNDER_CONSTRUCTION = "under_construction"
    COMPLETED = "completed"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"


# Backward-compatibility map: old stage names -> new PipelineStage values
STAGE_MIGRATION_MAP = {
    "rezoning_application": PipelineStage.APPLICATION_SUBMITTED,
    "public_hearing": PipelineStage.REFERRED_TO_PUBLIC_HEARING,
    "council_decision": PipelineStage.APPROVED,
    "development_permit": PipelineStage.UNDER_STAFF_REVIEW,
    "building_permit": PipelineStage.APPLICATION_SUBMITTED,
    "under_construction": PipelineStage.UNDER_CONSTRUCTION,
    "completed": PipelineStage.COMPLETED,
}


class PipelineEntry(BaseModel):
    """A single development project in the pipeline."""
    id: int
    parcel_pid: str
    address: str
    neighborhood: Optional[str] = None
    pipeline_stage: PipelineStage
    current_zoning: Optional[str] = None
    proposed_zoning: Optional[str] = None
    proposed_storeys: Optional[int] = None
    proposed_units: Optional[int] = None
    proposed_sqft: Optional[float] = None
    developer: Optional[str] = None
    estimated_completion: Optional[date] = None
    signal_ids: List[int] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


_PID_PATTERN = re.compile(r"^\d{3}-?\d{3}-?\d{3}$")

# Vancouver bounding box (WGS84) for geocode validation
_VAN_BBOX = {
    "min_lng": -123.27, "max_lng": -123.02,
    "min_lat": 49.20, "max_lat": 49.32,
}


class PipelineEntryCreate(BaseModel):
    """Request model for creating a pipeline entry."""
    parcel_pid: str
    address: str
    neighborhood: Optional[str] = None
    pipeline_stage: PipelineStage
    current_zoning: Optional[str] = None
    proposed_zoning: Optional[str] = None
    proposed_storeys: Optional[int] = None
    proposed_units: Optional[int] = None
    proposed_sqft: Optional[float] = None
    developer: Optional[str] = None
    estimated_completion: Optional[date] = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("parcel_pid")
    @classmethod
    def validate_pid(cls, v: str) -> str:
        if not _PID_PATTERN.match(v):
            raise ValueError(
                f"Invalid PID format: '{v}'. Must be 9 digits (NNN-NNN-NNN)."
            )
        return v

    @field_validator("proposed_storeys")
    @classmethod
    def validate_storeys(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 100):
            raise ValueError(f"proposed_storeys must be 1-100, got {v}")
        return v

    @field_validator("proposed_units")
    @classmethod
    def validate_units(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5000):
            raise ValueError(f"proposed_units must be 1-5000, got {v}")
        return v

    @field_validator("estimated_completion")
    @classmethod
    def validate_completion_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None:
            if v < date(2020, 1, 1):
                raise ValueError(f"estimated_completion {v} is before 2020 — likely a data error")
            if v > date(2050, 1, 1):
                raise ValueError(f"estimated_completion {v} is after 2050 — likely a data error")
        return v


class PipelineStageChange(BaseModel):
    """A stage transition in pipeline history."""
    id: int
    pipeline_id: int
    from_stage: Optional[str] = None
    to_stage: str
    changed_at: datetime
    signal_id: Optional[int] = None
    notes: Optional[str] = None


class PipelineStageCounts(BaseModel):
    """Count of projects by stage."""
    stage: str
    count: int
    total_units: int
    total_sqft: float


class PipelineSummary(BaseModel):
    """High-level summary of pipeline."""
    total_entries: int
    total_units: int
    total_sqft: float
    by_stage: List[PipelineStageCounts]
    by_neighborhood: dict = Field(default_factory=dict)


class NeighborhoodSupply(BaseModel):
    """Supply analysis for a single neighborhood."""
    neighborhood: str
    total_projects: int
    total_units: int
    total_sqft: float
    by_stage: dict = Field(default_factory=dict)
    estimated_completion_range: dict = Field(default_factory=dict)


class PipelineStats(BaseModel):
    """Detailed pipeline statistics."""
    total_projects: int
    total_units: int
    total_sqft: float
    average_units_per_project: float
    average_storeys_per_project: Optional[float] = None
    projects_by_stage: dict = Field(default_factory=dict)
    projects_by_neighborhood: dict = Field(default_factory=dict)
    near_completion_count: int  # projects in approved or under_construction


# ════════════════════════════════════════════════════════════════════════════
# SUPPLY PIPELINE TRACKER
# ════════════════════════════════════════════════════════════════════════════

class SupplyPipelineTracker:
    """Core class for supply pipeline management."""

    @staticmethod
    async def add_entry(
        db_pool: asyncpg.Pool,
        entry: PipelineEntryCreate
    ) -> PipelineEntry:
        """
        Add a new project to the supply pipeline.

        Args:
            db_pool: AsyncPG connection pool
            entry: Pipeline entry creation data

        Returns:
            Created PipelineEntry with generated ID and timestamps

        Raises:
            Exception: If parcel_pid already exists or database error
        """
        try:
            query = """
                INSERT INTO supply_pipeline (
                    parcel_pid, address, neighborhood, pipeline_stage,
                    current_zoning, proposed_zoning,
                    proposed_storeys, proposed_units, proposed_sqft,
                    developer, estimated_completion, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING
                    id, parcel_pid, address, neighborhood, pipeline_stage,
                    current_zoning, proposed_zoning,
                    proposed_storeys, proposed_units, proposed_sqft,
                    developer, estimated_completion, signal_ids, metadata,
                    created_at, updated_at
            """

            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    entry.parcel_pid,
                    entry.address,
                    entry.neighborhood,
                    entry.pipeline_stage.value,
                    entry.current_zoning,
                    entry.proposed_zoning,
                    entry.proposed_storeys,
                    entry.proposed_units,
                    entry.proposed_sqft,
                    entry.developer,
                    entry.estimated_completion,
                    entry.metadata
                )

            if not row:
                raise Exception("Failed to insert pipeline entry")

            logger.info(f"Added pipeline entry for parcel {entry.parcel_pid}")
            return _row_to_entry(row)

        except asyncpg.UniqueViolationError:
            logger.error(f"Parcel {entry.parcel_pid} already exists in pipeline")
            raise ValueError(f"Parcel {entry.parcel_pid} already in pipeline")
        except Exception as e:
            logger.error(f"Error adding pipeline entry: {e}", exc_info=True)
            raise

    @staticmethod
    async def update_stage(
        db_pool: asyncpg.Pool,
        pipeline_id: int,
        new_stage: PipelineStage,
        signal_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> PipelineEntry:
        """
        Update a project's pipeline stage and record the transition.

        Args:
            db_pool: AsyncPG connection pool
            pipeline_id: ID of pipeline entry to update
            new_stage: New pipeline stage
            signal_id: Optional intelligence signal that triggered transition
            notes: Optional transition notes

        Returns:
            Updated PipelineEntry

        Raises:
            Exception: If entry not found or database error
        """
        try:
            # Get current stage before updating
            get_query = "SELECT pipeline_stage FROM supply_pipeline WHERE id = $1"

            async with db_pool.acquire() as conn:
                current_row = await conn.fetchrow(get_query, pipeline_id)

                if not current_row:
                    raise ValueError(f"Pipeline entry {pipeline_id} not found")

                old_stage = current_row['pipeline_stage']

                # Update the stage
                update_query = """
                    UPDATE supply_pipeline
                    SET pipeline_stage = $1, updated_at = now()
                    WHERE id = $2
                    RETURNING
                        id, parcel_pid, address, neighborhood, pipeline_stage,
                        current_zoning, proposed_zoning,
                        proposed_storeys, proposed_units, proposed_sqft,
                        developer, estimated_completion, signal_ids, metadata,
                        created_at, updated_at
                """

                updated_row = await conn.fetchrow(update_query, new_stage.value, pipeline_id)

                # Record the stage transition
                history_query = """
                    INSERT INTO pipeline_stage_history (
                        pipeline_id, from_stage, to_stage, signal_id, notes
                    )
                    VALUES ($1, $2, $3, $4, $5)
                """

                await conn.execute(
                    history_query,
                    pipeline_id,
                    old_stage,
                    new_stage.value,
                    signal_id,
                    notes
                )

                # AC-PIPE-005: Generate stage transition alerts for matching watchlists
                await _generate_stage_transition_alerts(
                    conn, updated_row, old_stage, new_stage.value
                )

            logger.info(
                f"Updated pipeline {pipeline_id} from {old_stage} to {new_stage.value}"
            )
            return _row_to_entry(updated_row)

        except Exception as e:
            logger.error(f"Error updating pipeline stage: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_pipeline(
        db_pool: asyncpg.Pool,
        neighborhood: Optional[str] = None,
        stage: Optional[str] = None,
        height_min: Optional[int] = None,
        height_max: Optional[int] = None,
        units_min: Optional[int] = None,
        units_max: Optional[int] = None,
        developer: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[PipelineEntry], int]:
        """
        Query pipeline entries with optional filters.

        Args:
            db_pool: AsyncPG connection pool
            neighborhood: Filter by neighborhood (optional)
            stage: Filter by pipeline stage (optional)
            height_min: Minimum proposed storeys (optional)
            height_max: Maximum proposed storeys (optional)
            units_min: Minimum proposed units (optional)
            units_max: Maximum proposed units (optional)
            developer: Developer name search (partial, case-insensitive) (optional)
            limit: Maximum results (max 100, default 50)
            offset: Pagination offset

        Returns:
            Tuple of (list of PipelineEntry, total_count)
        """
        try:
            limit = min(limit, 100)
            offset = max(offset, 0)

            # Build dynamic query
            where_clauses = []
            params = []

            if neighborhood:
                where_clauses.append("neighborhood = $" + str(len(params) + 1))
                params.append(neighborhood)

            if stage:
                where_clauses.append("pipeline_stage = $" + str(len(params) + 1))
                params.append(stage)

            if height_min is not None:
                where_clauses.append("proposed_storeys >= $" + str(len(params) + 1))
                params.append(height_min)

            if height_max is not None:
                where_clauses.append("proposed_storeys <= $" + str(len(params) + 1))
                params.append(height_max)

            if units_min is not None:
                where_clauses.append("proposed_units >= $" + str(len(params) + 1))
                params.append(units_min)

            if units_max is not None:
                where_clauses.append("proposed_units <= $" + str(len(params) + 1))
                params.append(units_max)

            if developer:
                where_clauses.append("developer ILIKE $" + str(len(params) + 1))
                params.append(f"%{developer}%")

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Count query
            count_query = f"SELECT COUNT(*) as total FROM supply_pipeline WHERE {where_sql}"

            # Fetch query
            fetch_query = f"""
                SELECT
                    id, parcel_pid, address, neighborhood, pipeline_stage,
                    current_zoning, proposed_zoning,
                    proposed_storeys, proposed_units, proposed_sqft,
                    developer, estimated_completion, signal_ids, metadata,
                    created_at, updated_at
                FROM supply_pipeline
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ${ len(params) + 1} OFFSET ${len(params) + 2}
            """

            async with db_pool.acquire() as conn:
                count_row = await conn.fetchrow(count_query, *params)
                total_count = count_row['total'] if count_row else 0

                rows = await conn.fetch(fetch_query, *params, limit, offset)

            entries = [_row_to_entry(row) for row in rows]
            logger.info(f"Retrieved {len(entries)} pipeline entries")
            return entries, total_count

        except Exception as e:
            logger.error(f"Error retrieving pipeline: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_pipeline_in_polygon(
        db_pool: asyncpg.Pool,
        geojson_polygon: dict,
        stage: Optional[str] = None,
        limit: int = 100,
    ) -> List[PipelineEntry]:
        """
        FR-PIPE-005: Get pipeline entries whose parcels intersect a GeoJSON polygon.

        Uses spatial join: supply_pipeline.parcel_pid → parcels.geom.

        Args:
            db_pool: AsyncPG connection pool
            geojson_polygon: GeoJSON Polygon or MultiPolygon geometry dict
            stage: Optional stage filter
            limit: Max results (default 100)

        Returns:
            List of PipelineEntry within the polygon
        """
        import json

        try:
            geojson_str = json.dumps(geojson_polygon)

            where_extra = ""
            params = [geojson_str, limit]
            if stage:
                where_extra = "AND sp.pipeline_stage = $3"
                params.append(stage)

            query = f"""
                SELECT
                    sp.id, sp.parcel_pid, sp.address, sp.neighborhood,
                    sp.pipeline_stage, sp.current_zoning, sp.proposed_zoning,
                    sp.proposed_storeys, sp.proposed_units, sp.proposed_sqft,
                    sp.developer, sp.estimated_completion, sp.signal_ids,
                    sp.metadata, sp.created_at, sp.updated_at
                FROM supply_pipeline sp
                JOIN parcels p ON p.pid = sp.parcel_pid
                WHERE ST_Intersects(
                    p.geom,
                    ST_SetSRID(ST_GeomFromGeoJSON($1), 4326)
                )
                {where_extra}
                ORDER BY sp.created_at DESC
                LIMIT $2
            """

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            entries = [_row_to_entry(row) for row in rows]
            logger.info(f"Found {len(entries)} pipeline entries in polygon")
            return entries

        except Exception as e:
            logger.error(f"Error querying pipeline in polygon: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_entry(
        db_pool: asyncpg.Pool,
        pipeline_id: int
    ) -> Optional[PipelineEntry]:
        """
        Get a single pipeline entry by ID.

        Args:
            db_pool: AsyncPG connection pool
            pipeline_id: ID to retrieve

        Returns:
            PipelineEntry or None if not found
        """
        try:
            query = """
                SELECT
                    id, parcel_pid, address, neighborhood, pipeline_stage,
                    current_zoning, proposed_zoning,
                    proposed_storeys, proposed_units, proposed_sqft,
                    developer, estimated_completion, signal_ids, metadata,
                    created_at, updated_at
                FROM supply_pipeline
                WHERE id = $1
            """

            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, pipeline_id)

            if not row:
                logger.info(f"Pipeline entry {pipeline_id} not found")
                return None

            logger.info(f"Retrieved pipeline entry {pipeline_id}")
            return _row_to_entry(row)

        except Exception as e:
            logger.error(f"Error retrieving pipeline entry: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_entry_by_parcel(
        db_pool: asyncpg.Pool,
        parcel_pid: str
    ) -> Optional[PipelineEntry]:
        """
        Get a pipeline entry by parcel PID.

        Args:
            db_pool: AsyncPG connection pool
            parcel_pid: Parcel PID to lookup

        Returns:
            PipelineEntry or None if not found
        """
        try:
            query = """
                SELECT
                    id, parcel_pid, address, neighborhood, pipeline_stage,
                    current_zoning, proposed_zoning,
                    proposed_storeys, proposed_units, proposed_sqft,
                    developer, estimated_completion, signal_ids, metadata,
                    created_at, updated_at
                FROM supply_pipeline
                WHERE parcel_pid = $1
            """

            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, parcel_pid)

            if not row:
                logger.info(f"No pipeline entry for parcel {parcel_pid}")
                return None

            return _row_to_entry(row)

        except Exception as e:
            logger.error(f"Error retrieving entry by parcel: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_stage_history(
        db_pool: asyncpg.Pool,
        pipeline_id: int
    ) -> List[PipelineStageChange]:
        """
        Get the stage transition history for a pipeline entry.

        Args:
            db_pool: AsyncPG connection pool
            pipeline_id: Pipeline ID to get history for

        Returns:
            List of PipelineStageChange ordered by changed_at DESC
        """
        try:
            query = """
                SELECT
                    id, pipeline_id, from_stage, to_stage, changed_at,
                    signal_id, notes
                FROM pipeline_stage_history
                WHERE pipeline_id = $1
                ORDER BY changed_at DESC
            """

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, pipeline_id)

            changes = [
                PipelineStageChange(
                    id=row['id'],
                    pipeline_id=row['pipeline_id'],
                    from_stage=row['from_stage'],
                    to_stage=row['to_stage'],
                    changed_at=row['changed_at'],
                    signal_id=row['signal_id'],
                    notes=row['notes']
                )
                for row in rows
            ]

            logger.info(f"Retrieved {len(changes)} stage changes for pipeline {pipeline_id}")
            return changes

        except Exception as e:
            logger.error(f"Error retrieving stage history: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_pipeline_summary(
        db_pool: asyncpg.Pool
    ) -> PipelineSummary:
        """
        Get high-level summary of the entire pipeline.

        Includes:
        - Total entries, units, and sqft
        - Breakdown by stage
        - Breakdown by neighborhood

        Args:
            db_pool: AsyncPG connection pool

        Returns:
            PipelineSummary with aggregated data
        """
        try:
            # Total counts
            total_query = """
                SELECT
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft
                FROM supply_pipeline
            """

            # By stage
            stage_query = """
                SELECT
                    pipeline_stage,
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft
                FROM supply_pipeline
                GROUP BY pipeline_stage
                ORDER BY pipeline_stage
            """

            # By neighborhood
            neighborhood_query = """
                SELECT
                    neighborhood,
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft
                FROM supply_pipeline
                WHERE neighborhood IS NOT NULL
                GROUP BY neighborhood
                ORDER BY units DESC
            """

            async with db_pool.acquire() as conn:
                total_row = await conn.fetchrow(total_query)
                stage_rows = await conn.fetch(stage_query)
                neighborhood_rows = await conn.fetch(neighborhood_query)

            by_stage = [
                PipelineStageCounts(
                    stage=row['pipeline_stage'],
                    count=row['count'],
                    total_units=row['units'],
                    total_sqft=float(row['sqft'])
                )
                for row in stage_rows
            ]

            by_neighborhood = {
                row['neighborhood']: {
                    'count': row['count'],
                    'units': row['units'],
                    'sqft': float(row['sqft'])
                }
                for row in neighborhood_rows
            }

            logger.info("Retrieved pipeline summary")
            return PipelineSummary(
                total_entries=total_row['count'],
                total_units=total_row['units'],
                total_sqft=float(total_row['sqft']),
                by_stage=by_stage,
                by_neighborhood=by_neighborhood
            )

        except Exception as e:
            logger.error(f"Error retrieving pipeline summary: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_neighborhood_supply(
        db_pool: asyncpg.Pool,
        neighborhood: str
    ) -> NeighborhoodSupply:
        """
        Get detailed supply analysis for a neighborhood.

        Args:
            db_pool: AsyncPG connection pool
            neighborhood: Neighborhood name

        Returns:
            NeighborhoodSupply with stage breakdown and completion estimates
        """
        try:
            # Overall stats
            overall_query = """
                SELECT
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft
                FROM supply_pipeline
                WHERE neighborhood = $1
            """

            # By stage
            stage_query = """
                SELECT
                    pipeline_stage,
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft
                FROM supply_pipeline
                WHERE neighborhood = $1
                GROUP BY pipeline_stage
            """

            # Completion timeline
            completion_query = """
                SELECT
                    DATE_TRUNC('quarter', estimated_completion)::date as quarter,
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units
                FROM supply_pipeline
                WHERE neighborhood = $1 AND estimated_completion IS NOT NULL
                GROUP BY quarter
                ORDER BY quarter ASC
            """

            async with db_pool.acquire() as conn:
                overall_row = await conn.fetchrow(overall_query, neighborhood)
                stage_rows = await conn.fetch(stage_query, neighborhood)
                completion_rows = await conn.fetch(completion_query, neighborhood)

            by_stage = {
                row['pipeline_stage']: {
                    'count': row['count'],
                    'units': row['units'],
                    'sqft': float(row['sqft'])
                }
                for row in stage_rows
            }

            completion_range = {
                str(row['quarter']): {
                    'count': row['count'],
                    'units': row['units']
                }
                for row in completion_rows
            }

            logger.info(f"Retrieved supply for neighborhood {neighborhood}")
            return NeighborhoodSupply(
                neighborhood=neighborhood,
                total_projects=overall_row['count'],
                total_units=overall_row['units'],
                total_sqft=float(overall_row['sqft']),
                by_stage=by_stage,
                estimated_completion_range=completion_range
            )

        except Exception as e:
            logger.error(f"Error retrieving neighborhood supply: {e}", exc_info=True)
            raise

    @staticmethod
    async def ingest_from_signal(
        db_pool: asyncpg.Pool,
        signal: dict
    ) -> PipelineEntry:
        """
        Auto-create or update a pipeline entry from an intelligence signal.

        Uses signal data (addresses, neighborhood, unit_count, etc.) to populate
        a pipeline entry. If parcel already exists, updates it.

        Args:
            db_pool: AsyncPG connection pool
            signal: Dictionary with signal data from intelligence_signals table

        Returns:
            Created or updated PipelineEntry

        Raises:
            Exception: If signal lacks critical data or database error
        """
        try:
            # Extract required data
            if not signal.get('addresses') or len(signal['addresses']) == 0:
                raise ValueError("Signal must have at least one address")

            address = signal['addresses'][0]
            neighborhood = signal.get('neighborhood')
            parcel_pid = signal.get('parcel_pid', f"signal_{signal.get('id')}")

            # Check if entry already exists
            existing = await SupplyPipelineTracker.get_entry_by_parcel(
                db_pool, parcel_pid
            )

            if existing:
                # Update existing entry
                query = """
                    UPDATE supply_pipeline
                    SET
                        neighborhood = COALESCE($2, neighborhood),
                        zoning_to = COALESCE($3, zoning_to),
                        proposed_units = COALESCE($4, proposed_units),
                        signal_ids = array_append(signal_ids, $5),
                        updated_at = now()
                    WHERE parcel_pid = $1
                    RETURNING
                        id, parcel_pid, address, neighborhood, pipeline_stage,
                        current_zoning, proposed_zoning,
                        proposed_storeys, proposed_units, proposed_sqft,
                        developer, estimated_completion, signal_ids, metadata,
                        created_at, updated_at
                """

                async with db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        query,
                        parcel_pid,
                        neighborhood,
                        signal.get('zoning_to'),
                        signal.get('unit_count'),
                        signal.get('id')
                    )

                logger.info(f"Updated pipeline entry from signal {signal.get('id')}")
                return _row_to_entry(row)

            else:
                # Create new entry
                entry = PipelineEntryCreate(
                    parcel_pid=parcel_pid,
                    address=address,
                    neighborhood=neighborhood,
                    pipeline_stage=PipelineStage.APPLICATION_SUBMITTED,
                    current_zoning=signal.get('zoning_from'),
                    proposed_zoning=signal.get('zoning_to'),
                    proposed_storeys=signal.get('height_after'),
                    proposed_units=signal.get('unit_count'),
                    proposed_sqft=signal.get('sqft'),
                    metadata={
                        'sourced_from_signal': signal.get('id'),
                        'signal_type': signal.get('signal_type'),
                        'confidence': signal.get('confidence')
                    }
                )

                result = await SupplyPipelineTracker.add_entry(db_pool, entry)

                # Link the signal to this pipeline entry
                link_query = """
                    UPDATE supply_pipeline
                    SET signal_ids = array_append(signal_ids, $2)
                    WHERE id = $1
                """

                async with db_pool.acquire() as conn:
                    await conn.execute(link_query, result.id, signal.get('id'))

                logger.info(f"Created pipeline entry from signal {signal.get('id')}")
                return result

        except Exception as e:
            logger.error(f"Error ingesting from signal: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_pipeline_stats(
        db_pool: asyncpg.Pool,
        neighborhood: Optional[str] = None
    ) -> PipelineStats:
        """
        Get detailed pipeline statistics.

        Includes total projects, units, sqft, and breakdowns by stage
        and neighborhood.

        Args:
            db_pool: AsyncPG connection pool
            neighborhood: Optional filter to neighborhood

        Returns:
            PipelineStats with aggregated metrics
        """
        try:
            where_clause = ""
            params = []

            if neighborhood:
                where_clause = "WHERE neighborhood = $1"
                params = [neighborhood]

            # Overall stats
            total_query = f"""
                SELECT
                    COUNT(*) as count,
                    COALESCE(SUM(proposed_units), 0) as units,
                    COALESCE(SUM(proposed_sqft), 0) as sqft,
                    COALESCE(AVG(proposed_units), 0) as avg_units,
                    COALESCE(AVG(proposed_storeys), 0) as avg_storeys
                FROM supply_pipeline
                {where_clause}
            """

            # By stage
            stage_query = f"""
                SELECT
                    pipeline_stage,
                    COUNT(*) as count
                FROM supply_pipeline
                {where_clause}
                GROUP BY pipeline_stage
            """

            # By neighborhood (only if not already filtered)
            neighborhood_query = """
                SELECT
                    neighborhood,
                    COUNT(*) as count
                FROM supply_pipeline
                WHERE neighborhood IS NOT NULL
                GROUP BY neighborhood
                ORDER BY count DESC
            """

            # Near completion count
            near_completion_query = f"""
                SELECT COUNT(*) as count
                FROM supply_pipeline
                WHERE pipeline_stage IN ('approved', 'under_construction')
                {"AND neighborhood = $1" if neighborhood else ""}
            """

            async with db_pool.acquire() as conn:
                total_row = await conn.fetchrow(total_query, *params)
                stage_rows = await conn.fetch(stage_query, *params)
                neighborhood_rows = await conn.fetch(neighborhood_query)
                near_completion_row = await conn.fetchrow(
                    near_completion_query,
                    *(params if neighborhood else [])
                )

            projects_by_stage = {
                row['pipeline_stage']: row['count']
                for row in stage_rows
            }

            projects_by_neighborhood = {
                row['neighborhood']: row['count']
                for row in neighborhood_rows
            }

            logger.info("Retrieved pipeline statistics")
            return PipelineStats(
                total_projects=total_row['count'],
                total_units=total_row['units'],
                total_sqft=float(total_row['sqft']),
                average_units_per_project=float(total_row['avg_units']),
                average_storeys_per_project=float(total_row['avg_storeys']),
                projects_by_stage=projects_by_stage,
                projects_by_neighborhood=projects_by_neighborhood,
                near_completion_count=near_completion_row['count']
            )

        except Exception as e:
            logger.error(f"Error retrieving pipeline statistics: {e}", exc_info=True)
            raise

    @staticmethod
    async def delete_entry(
        db_pool: asyncpg.Pool,
        pipeline_id: int
    ) -> bool:
        """
        Delete a pipeline entry and its history.

        Args:
            db_pool: AsyncPG connection pool
            pipeline_id: ID of entry to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            query = "DELETE FROM supply_pipeline WHERE id = $1"

            async with db_pool.acquire() as conn:
                result = await conn.execute(query, pipeline_id)

            # Check if any rows were deleted
            deleted = result != "DELETE 0"
            if deleted:
                logger.info(f"Deleted pipeline entry {pipeline_id}")
            else:
                logger.info(f"Pipeline entry {pipeline_id} not found")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting pipeline entry: {e}", exc_info=True)
            raise


# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def _row_to_entry(row) -> PipelineEntry:
    """Convert database row to PipelineEntry model."""
    raw_stage = row['pipeline_stage']
    if raw_stage in STAGE_MIGRATION_MAP:
        stage = STAGE_MIGRATION_MAP[raw_stage]
    else:
        stage = PipelineStage(raw_stage)
    return PipelineEntry(
        id=row['id'],
        parcel_pid=row['parcel_pid'],
        address=row['address'],
        neighborhood=row['neighborhood'],
        pipeline_stage=stage,
        current_zoning=row['current_zoning'],
        proposed_zoning=row['proposed_zoning'],
        proposed_storeys=row['proposed_storeys'],
        proposed_units=row['proposed_units'],
        proposed_sqft=float(row['proposed_sqft']) if row['proposed_sqft'] else None,
        developer=row['developer'],
        estimated_completion=row['estimated_completion'],
        signal_ids=row['signal_ids'] or [],
        metadata=row['metadata'] or {},
        created_at=row['created_at'],
        updated_at=row['updated_at']
    )


async def _generate_stage_transition_alerts(
    conn,
    pipeline_row,
    old_stage: str,
    new_stage: str,
) -> None:
    """
    AC-PIPE-005: Generate alerts for watchlists that match a pipeline stage transition.

    Matches watchlists with rules targeting:
    - The pipeline entry's neighborhood
    - The pipeline entry's zoning
    - signal_type='stage_transition'
    """
    address = pipeline_row["address"] or "Unknown address"
    neighborhood = pipeline_row["neighborhood"]
    headline = f"Stage change: {address} moved from {old_stage} → {new_stage}"
    summary = (
        f"Pipeline project at {address}"
        f"{' in ' + neighborhood if neighborhood else ''}"
        f" transitioned from '{old_stage}' to '{new_stage}'."
    )
    severity = "info"
    if new_stage in ("under_construction", "completed"):
        severity = "high"
    elif new_stage in ("approved", "under_staff_review"):
        severity = "medium"

    # Find matching watchlists (neighborhood or signal_type rules)
    match_query = """
        SELECT DISTINCT w.id AS watchlist_id
        FROM watchlists w
        JOIN watchlist_rules wr ON wr.watchlist_id = w.id
        WHERE w.is_active = true
          AND (
            (wr.rule_type = 'neighborhood' AND LOWER(wr.rule_value) = LOWER($1))
            OR (wr.rule_type = 'signal_type' AND wr.rule_value = 'stage_transition')
            OR (wr.rule_type = 'zoning' AND LOWER(wr.rule_value) = LOWER($2))
          )
    """
    zoning = pipeline_row.get("proposed_zoning") or pipeline_row.get("current_zoning") or ""

    try:
        watchlist_rows = await conn.fetch(match_query, neighborhood or "", zoning)
        for wl in watchlist_rows:
            await conn.execute(
                """
                INSERT INTO alerts
                (watchlist_id, signal_id, alert_type, headline, summary, severity, is_read, created_at)
                VALUES ($1, 0, 'stage_transition', $2, $3, $4, false, NOW())
                """,
                wl["watchlist_id"], headline, summary, severity,
            )
        if watchlist_rows:
            logger.info(
                f"Generated {len(watchlist_rows)} stage transition alerts for pipeline "
                f"{pipeline_row['id']}: {old_stage} → {new_stage}"
            )
    except Exception as e:
        # Don't fail the stage update if alert generation fails
        logger.warning(f"Failed to generate stage transition alerts: {e}")
