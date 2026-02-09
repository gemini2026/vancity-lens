"""
VCL-50 [INTEL-009] Proactive opportunity alerts engine.

Manages user-defined opportunity profiles and detects matching parcels
based on customizable criteria (lot size, price, zoning, transit proximity,
storey/FSR uplift potential).
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field
import asyncpg

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────────────────────────────


class OpportunityProfileCreate(BaseModel):
    """Request model for creating an opportunity profile."""
    profile_name: str = Field(..., max_length=255)
    min_lot_area_sqm: Optional[float] = None
    max_price: Optional[int] = None
    target_neighborhoods: Optional[List[str]] = None
    target_zoning_codes: Optional[List[str]] = None
    min_storey_uplift: Optional[int] = None
    min_fsr_uplift: Optional[float] = None
    max_distance_m: int = Field(default=800, ge=100, le=2000)


class OpportunityProfileUpdate(BaseModel):
    """Request model for updating an opportunity profile."""
    profile_name: Optional[str] = Field(None, max_length=255)
    min_lot_area_sqm: Optional[float] = None
    max_price: Optional[int] = None
    target_neighborhoods: Optional[List[str]] = None
    target_zoning_codes: Optional[List[str]] = None
    min_storey_uplift: Optional[int] = None
    min_fsr_uplift: Optional[float] = None
    max_distance_m: Optional[int] = Field(None, ge=100, le=2000)
    is_active: Optional[bool] = None


class OpportunityProfileResponse(BaseModel):
    """Response model for opportunity profile."""
    id: int
    user_id: int
    profile_name: str
    min_lot_area_sqm: Optional[float]
    max_price: Optional[int]
    target_neighborhoods: Optional[List[str]]
    target_zoning_codes: Optional[List[str]]
    min_storey_uplift: Optional[int]
    min_fsr_uplift: Optional[float]
    max_distance_m: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OpportunityMatchResponse(BaseModel):
    """Response model for opportunity match."""
    id: int
    profile_id: int
    parcel_pid: str
    civic_address: Optional[str]
    match_score: float
    match_reasons: dict
    is_dismissed: bool
    created_at: datetime
    dismissed_at: Optional[datetime]

    class Config:
        from_attributes = True


class MatchReason(BaseModel):
    """Individual match reason with score contribution."""
    category: str  # e.g. "storey_uplift", "fsr_uplift", "proximity", "lot_size", "price"
    score: float
    details: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# OpportunityAlertEngine
# ────────────────────────────────────────────────────────────────────────────


class OpportunityAlertEngine:
    """Core engine for opportunity detection and management."""

    @staticmethod
    async def create_profile(
        db_pool: asyncpg.Pool,
        user_id: int,
        profile: OpportunityProfileCreate,
    ) -> OpportunityProfileResponse:
        """
        Create a new opportunity profile for a user.

        Args:
            db_pool: AsyncPG connection pool
            user_id: User ID
            profile: Profile data

        Returns:
            Created profile response
        """
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO opportunity_profiles (
                    user_id, profile_name, min_lot_area_sqm, max_price,
                    target_neighborhoods, target_zoning_codes,
                    min_storey_uplift, min_fsr_uplift, max_distance_m
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, user_id, profile_name, min_lot_area_sqm, max_price,
                          target_neighborhoods, target_zoning_codes,
                          min_storey_uplift, min_fsr_uplift, max_distance_m,
                          is_active, created_at, updated_at
                """,
                user_id,
                profile.profile_name,
                profile.min_lot_area_sqm,
                profile.max_price,
                profile.target_neighborhoods,
                profile.target_zoning_codes,
                profile.min_storey_uplift,
                profile.min_fsr_uplift,
                profile.max_distance_m,
            )
            logger.info(f"Created opportunity profile {result['id']} for user {user_id}")
            return OpportunityProfileResponse(**result)

    @staticmethod
    async def get_profiles(
        db_pool: asyncpg.Pool,
        user_id: int,
        include_inactive: bool = False,
    ) -> List[OpportunityProfileResponse]:
        """
        Get all opportunity profiles for a user.

        Args:
            db_pool: AsyncPG connection pool
            user_id: User ID
            include_inactive: Whether to include inactive profiles

        Returns:
            List of profiles
        """
        async with db_pool.acquire() as conn:
            query = "SELECT * FROM opportunity_profiles WHERE user_id = $1"
            params = [user_id]

            if not include_inactive:
                query += " AND is_active = true"

            query += " ORDER BY updated_at DESC"

            results = await conn.fetch(query, *params)
            return [OpportunityProfileResponse(**row) for row in results]

    @staticmethod
    async def get_profile(
        db_pool: asyncpg.Pool,
        profile_id: int,
    ) -> Optional[OpportunityProfileResponse]:
        """
        Get a single profile by ID.

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID

        Returns:
            Profile or None
        """
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM opportunity_profiles WHERE id = $1",
                profile_id,
            )
            return OpportunityProfileResponse(**result) if result else None

    @staticmethod
    async def update_profile(
        db_pool: asyncpg.Pool,
        profile_id: int,
        updates: OpportunityProfileUpdate,
    ) -> Optional[OpportunityProfileResponse]:
        """
        Update an opportunity profile.

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID
            updates: Fields to update

        Returns:
            Updated profile or None
        """
        # Build dynamic UPDATE query
        set_clauses = []
        params = []
        param_count = 1

        for field, value in updates.model_dump(exclude_unset=True).items():
            set_clauses.append(f"{field} = ${param_count}")
            params.append(value)
            param_count += 1

        if not set_clauses:
            return await OpportunityAlertEngine.get_profile(db_pool, profile_id)

        set_clauses.append(f"updated_at = ${param_count}")
        params.append(datetime.now())
        param_count += 1

        params.append(profile_id)

        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                f"""
                UPDATE opportunity_profiles
                SET {', '.join(set_clauses)}
                WHERE id = ${param_count}
                RETURNING *
                """,
                *params,
            )
            if result:
                logger.info(f"Updated opportunity profile {profile_id}")
            return OpportunityProfileResponse(**result) if result else None

    @staticmethod
    async def delete_profile(
        db_pool: asyncpg.Pool,
        profile_id: int,
    ) -> bool:
        """
        Delete an opportunity profile (hard delete).

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID

        Returns:
            True if deleted
        """
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM opportunity_profiles WHERE id = $1",
                profile_id,
            )
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"Deleted opportunity profile {profile_id}")
            return deleted

    @staticmethod
    async def scan_opportunities(
        db_pool: asyncpg.Pool,
        profile_id: int,
    ) -> List[OpportunityMatchResponse]:
        """
        Scan for parcels matching a profile's criteria.

        Queries parcels within TOA buffers and calculates match scores based on:
        - Storey uplift (current vs entitled)
        - FSR uplift (current vs entitled)
        - Proximity to transit stations
        - Lot size fit
        - Price fit

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID

        Returns:
            List of matching parcels ranked by score
        """
        async with db_pool.acquire() as conn:
            # Fetch profile
            profile = await conn.fetchrow(
                "SELECT * FROM opportunity_profiles WHERE id = $1",
                profile_id,
            )
            if not profile:
                return []

            # Query for parcels within TOA buffers matching criteria
            query = """
                WITH profile_data AS (
                    SELECT
                        $1::int AS profile_id,
                        $2::numeric AS min_lot_area_sqm,
                        $3::bigint AS max_price,
                        $4::text[] AS target_zoning,
                        $5::int AS min_storey_uplift,
                        $6::numeric AS min_fsr_uplift,
                        $7::int AS max_distance_m
                ),
                parcel_entitlements AS (
                    SELECT
                        p.pid,
                        p.civic_address,
                        p.lot_area_sqm,
                        p.assessed_value,
                        p.asking_price,
                        p.current_zoning,
                        p.current_height,
                        p.current_fsr,
                        MAX(t.max_storeys) AS entitled_storeys,
                        MAX(t.max_fsr) AS entitled_fsr,
                        MIN(ST_Distance(
                            ST_Transform(ST_Centroid(p.geom), 3005),
                            ST_Transform(s.geom, 3005)
                        )) AS dist_to_nearest_station
                    FROM parcels p
                    CROSS JOIN profile_data pd
                    CROSS JOIN transit_stations s
                    CROSS JOIN toa_buffers t
                    WHERE ST_Intersects(p.geom, t.geom)
                        AND p.lot_area_sqm >= COALESCE(pd.min_lot_area_sqm, 0)
                        AND (p.assessed_value <= COALESCE(pd.max_price, 999999999999)
                             OR p.asking_price IS NULL
                             OR p.asking_price <= COALESCE(pd.max_price, 999999999999))
                        AND (pd.target_zoning IS NULL OR p.current_zoning = ANY(pd.target_zoning))
                    GROUP BY p.id, p.pid, p.civic_address, p.lot_area_sqm, p.assessed_value,
                             p.asking_price, p.current_zoning, p.current_height, p.current_fsr
                ),
                scored_parcels AS (
                    SELECT
                        pe.pid,
                        pe.civic_address,
                        pe.lot_area_sqm,
                        pe.assessed_value,
                        pe.asking_price,
                        pe.current_zoning,
                        pe.entitled_storeys,
                        pe.entitled_fsr,
                        pe.current_height,
                        pe.current_fsr,
                        pe.dist_to_nearest_station,
                        (COALESCE(pe.entitled_storeys, 0) - COALESCE(pe.current_height, 0))::int AS storey_uplift,
                        (COALESCE(pe.entitled_fsr, 0) - COALESCE(pe.current_fsr, 0))::numeric AS fsr_uplift,
                        pd.min_storey_uplift,
                        pd.min_fsr_uplift,
                        pd.max_distance_m,
                        pd.profile_id
                    FROM parcel_entitlements pe
                    CROSS JOIN profile_data pd
                )
                SELECT
                    sp.profile_id,
                    sp.pid,
                    sp.civic_address,
                    sp.storey_uplift,
                    sp.fsr_uplift,
                    sp.lot_area_sqm,
                    sp.assessed_value,
                    sp.asking_price,
                    sp.current_zoning,
                    sp.entitled_storeys,
                    sp.entitled_fsr,
                    sp.current_height,
                    sp.current_fsr,
                    sp.dist_to_nearest_station,
                    CASE
                        WHEN sp.storey_uplift < COALESCE(sp.min_storey_uplift, 0)
                             OR sp.fsr_uplift < COALESCE(sp.min_fsr_uplift, 0)
                             OR sp.dist_to_nearest_station > sp.max_distance_m
                        THEN NULL
                        ELSE (
                            LEAST(1.0, GREATEST(0.0,
                                COALESCE(sp.storey_uplift::numeric / NULLIF(sp.min_storey_uplift, 0), 0.5) * 0.35 +
                                COALESCE(sp.fsr_uplift / NULLIF(sp.min_fsr_uplift, 0), 0.5) * 0.35 +
                                (1.0 - (sp.dist_to_nearest_station / COALESCE(sp.max_distance_m, 800)::numeric)) * 0.20 +
                                CASE
                                    WHEN sp.lot_area_sqm >= 3000 THEN 0.10
                                    WHEN sp.lot_area_sqm >= 1500 THEN 0.05
                                    ELSE 0.0
                                END
                            )) * 100.0
                        )::numeric(5,2)
                    END AS match_score
                FROM scored_parcels sp
                WHERE sp.dist_to_nearest_station <= sp.max_distance_m
                ORDER BY match_score DESC NULLS LAST
            """

            results = await conn.fetch(
                query,
                profile_id,
                profile.get("min_lot_area_sqm"),
                profile.get("max_price"),
                profile.get("target_zoning_codes"),
                profile.get("min_storey_uplift"),
                profile.get("min_fsr_uplift"),
                profile.get("max_distance_m"),
            )

            # Store matches in database and build responses
            matches = []
            for row in results:
                if row["match_score"] is None:
                    continue

                # Build match reasons
                reasons = {
                    "storey_uplift": row["storey_uplift"],
                    "fsr_uplift": float(row["fsr_uplift"]) if row["fsr_uplift"] else 0,
                    "distance_m": float(row["dist_to_nearest_station"]),
                    "lot_area_sqm": float(row["lot_area_sqm"]),
                    "entitled_storeys": row["entitled_storeys"],
                    "entitled_fsr": float(row["entitled_fsr"]) if row["entitled_fsr"] else 0,
                    "current_zoning": row["current_zoning"],
                }

                # Upsert match record
                await conn.execute(
                    """
                    INSERT INTO opportunity_matches
                        (profile_id, parcel_pid, match_score, match_reasons, is_dismissed, created_at)
                    VALUES ($1, $2, $3, $4, false, NOW())
                    ON CONFLICT (profile_id, parcel_pid)
                    WHERE is_dismissed = false
                    DO UPDATE SET
                        match_score = EXCLUDED.match_score,
                        match_reasons = EXCLUDED.match_reasons,
                        created_at = NOW()
                    """,
                    profile_id,
                    row["pid"],
                    float(row["match_score"]),
                    json.dumps(reasons),
                )

                matches.append(
                    OpportunityMatchResponse(
                        id=0,  # Will be fetched separately
                        profile_id=profile_id,
                        parcel_pid=row["pid"],
                        civic_address=row["civic_address"],
                        match_score=float(row["match_score"]),
                        match_reasons=reasons,
                        is_dismissed=False,
                        created_at=datetime.now(),
                        dismissed_at=None,
                    )
                )

            logger.info(f"Found {len(matches)} opportunities for profile {profile_id}")
            return matches

    @staticmethod
    async def get_matches(
        db_pool: asyncpg.Pool,
        profile_id: int,
        include_dismissed: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[OpportunityMatchResponse]:
        """
        Get matches for a profile with optional filtering.

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID
            include_dismissed: Whether to include dismissed matches
            limit: Result limit
            offset: Result offset

        Returns:
            List of matches
        """
        async with db_pool.acquire() as conn:
            query = """
                SELECT m.id, m.profile_id, m.parcel_pid, p.civic_address,
                       m.match_score, m.match_reasons, m.is_dismissed,
                       m.created_at, m.dismissed_at
                FROM opportunity_matches m
                LEFT JOIN parcels p ON m.parcel_pid = p.pid
                WHERE m.profile_id = $1
            """
            params = [profile_id]

            if not include_dismissed:
                query += " AND m.is_dismissed = false"

            query += " ORDER BY m.match_score DESC, m.created_at DESC"
            query += f" LIMIT {limit} OFFSET {offset}"

            results = await conn.fetch(query, *params)
            return [OpportunityMatchResponse(**row) for row in results]

    @staticmethod
    async def dismiss_match(
        db_pool: asyncpg.Pool,
        match_id: int,
    ) -> bool:
        """
        Dismiss (hide) an opportunity match.

        Args:
            db_pool: AsyncPG connection pool
            match_id: Match ID

        Returns:
            True if dismissed
        """
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE opportunity_matches
                SET is_dismissed = true, dismissed_at = NOW()
                WHERE id = $1
                """,
                match_id,
            )
            dismissed = result == "UPDATE 1"
            if dismissed:
                logger.info(f"Dismissed opportunity match {match_id}")
            return dismissed

    @staticmethod
    async def get_top_matches(
        db_pool: asyncpg.Pool,
        user_id: int,
        limit: int = 10,
    ) -> List[OpportunityMatchResponse]:
        """
        Get top matches across all active profiles for a user.

        Args:
            db_pool: AsyncPG connection pool
            user_id: User ID
            limit: Number of top matches

        Returns:
            List of top matches
        """
        async with db_pool.acquire() as conn:
            results = await conn.fetch(
                """
                SELECT m.id, m.profile_id, m.parcel_pid, p.civic_address,
                       m.match_score, m.match_reasons, m.is_dismissed,
                       m.created_at, m.dismissed_at
                FROM opportunity_matches m
                INNER JOIN opportunity_profiles op ON m.profile_id = op.id
                LEFT JOIN parcels p ON m.parcel_pid = p.pid
                WHERE op.user_id = $1
                  AND op.is_active = true
                  AND m.is_dismissed = false
                ORDER BY m.match_score DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [OpportunityMatchResponse(**row) for row in results]

    @staticmethod
    async def run_scan_all(
        db_pool: asyncpg.Pool,
    ) -> dict:
        """
        Scan opportunities for all active profiles (admin/scheduled use).

        Args:
            db_pool: AsyncPG connection pool

        Returns:
            Summary of scan results
        """
        async with db_pool.acquire() as conn:
            profiles = await conn.fetch(
                "SELECT id FROM opportunity_profiles WHERE is_active = true"
            )

        results = {
            "total_profiles": len(profiles),
            "scanned": 0,
            "errors": [],
        }

        for row in profiles:
            try:
                await OpportunityAlertEngine.scan_opportunities(
                    db_pool,
                    row["id"],
                )
                results["scanned"] += 1
            except Exception as e:
                error_msg = f"Profile {row['id']}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)

        logger.info(
            f"Completed scan_all: {results['scanned']} profiles scanned, "
            f"{len(results['errors'])} errors"
        )
        return results

    @staticmethod
    async def get_profile_owner(
        db_pool: asyncpg.Pool,
        profile_id: int,
    ) -> Optional[int]:
        """
        Get the user_id that owns a profile (for authorization checks).

        Args:
            db_pool: AsyncPG connection pool
            profile_id: Profile ID

        Returns:
            User ID or None
        """
        async with db_pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT user_id FROM opportunity_profiles WHERE id = $1",
                profile_id,
            )
            return result
