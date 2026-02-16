"""
VanCity Lens — Pipeline Clustering Alert Detection
FR-PIPE-006: Detect spatial/temporal clustering of development applications.

Triggers an alert when 3+ development applications appear within 500m radius
and 90-day window. This indicates a "hot zone" of development activity.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .supply_pipeline import PipelineStage

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────

CLUSTER_RADIUS_M = 500
CLUSTER_WINDOW_DAYS = 90
CLUSTER_MIN_APPS = 3


# ── Models ──────────────────────────────────────────────────────

class ClusterMember(BaseModel):
    """A pipeline entry that's part of a cluster."""
    pipeline_id: int
    parcel_pid: str
    address: str
    pipeline_stage: PipelineStage
    proposed_storeys: Optional[int] = None
    proposed_units: Optional[int] = None
    distance_m: float = Field(ge=0)


class DevelopmentCluster(BaseModel):
    """A detected cluster of development activity."""
    center_pid: str
    center_address: str
    center_lat: float = Field(ge=-90, le=90)
    center_lng: float = Field(ge=-180, le=180)
    member_count: int
    members: list[ClusterMember]
    radius_m: int = CLUSTER_RADIUS_M
    window_days: int = CLUSTER_WINDOW_DAYS
    total_proposed_units: int = 0
    neighborhoods: list[str] = Field(default_factory=list)


# ── SQL ─────────────────────────────────────────────────────────

SQL_FIND_CLUSTERS = """
    WITH pipeline_with_geom AS (
        SELECT
            sp.id AS pipeline_id,
            sp.parcel_pid,
            sp.address,
            sp.neighborhood,
            sp.pipeline_stage,
            sp.proposed_storeys,
            sp.proposed_units,
            sp.created_at,
            p.geom
        FROM supply_pipeline sp
        JOIN parcels p ON p.pid = sp.parcel_pid
        WHERE sp.created_at >= $1
          AND p.geom IS NOT NULL
    ),
    cluster_pairs AS (
        SELECT
            a.pipeline_id AS center_id,
            a.parcel_pid AS center_pid,
            a.address AS center_address,
            a.neighborhood AS center_neighborhood,
            ST_Y(ST_Transform(a.geom, 4326)) AS center_lat,
            ST_X(ST_Transform(a.geom, 4326)) AS center_lng,
            b.pipeline_id AS member_id,
            b.parcel_pid AS member_pid,
            b.address AS member_address,
            b.pipeline_stage AS member_stage,
            b.proposed_storeys AS member_storeys,
            b.proposed_units AS member_units,
            ROUND(ST_Distance(
                ST_Transform(a.geom, 3005),
                ST_Transform(b.geom, 3005)
            )::numeric, 1) AS distance_m
        FROM pipeline_with_geom a
        JOIN pipeline_with_geom b ON a.pipeline_id != b.pipeline_id
        WHERE ST_DWithin(
            ST_Transform(a.geom, 3005),
            ST_Transform(b.geom, 3005),
            $2
        )
    )
    SELECT
        center_pid, center_address, center_lat, center_lng,
        center_neighborhood,
        COUNT(DISTINCT member_id) + 1 AS cluster_size,
        json_agg(json_build_object(
            'pipeline_id', member_id,
            'parcel_pid', member_pid,
            'address', member_address,
            'pipeline_stage', member_stage,
            'proposed_storeys', member_storeys,
            'proposed_units', member_units,
            'distance_m', distance_m
        )) AS members
    FROM cluster_pairs
    GROUP BY center_pid, center_address, center_lat, center_lng, center_neighborhood
    HAVING COUNT(DISTINCT member_id) + 1 >= $3
    ORDER BY cluster_size DESC
"""


# ── Engine ──────────────────────────────────────────────────────

async def detect_clusters(
    db_pool,
    radius_m: int = CLUSTER_RADIUS_M,
    window_days: int = CLUSTER_WINDOW_DAYS,
    min_apps: int = CLUSTER_MIN_APPS,
) -> list[DevelopmentCluster]:
    """
    Detect spatial/temporal clusters of development applications.

    Returns clusters where min_apps+ applications exist within radius_m
    of each other, all created within the last window_days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(SQL_FIND_CLUSTERS, cutoff, radius_m, min_apps)

    clusters: list[DevelopmentCluster] = []
    seen_pids: set[str] = set()  # deduplicate overlapping clusters

    for row in rows:
        center_pid = row["center_pid"]
        if center_pid in seen_pids:
            continue
        seen_pids.add(center_pid)

        import json
        members_raw = row["members"]
        if isinstance(members_raw, str):
            members_raw = json.loads(members_raw)

        members = []
        total_units = 0
        neighborhoods = set()
        if row["center_neighborhood"]:
            neighborhoods.add(row["center_neighborhood"])

        for m in members_raw:
            seen_pids.add(m["parcel_pid"])
            members.append(ClusterMember(
                pipeline_id=m["pipeline_id"],
                parcel_pid=m["parcel_pid"],
                address=m["address"],
                pipeline_stage=m["pipeline_stage"],
                proposed_storeys=m.get("proposed_storeys"),
                proposed_units=m.get("proposed_units"),
                distance_m=float(m["distance_m"]),
            ))
            if m.get("proposed_units"):
                total_units += m["proposed_units"]

        cluster = DevelopmentCluster(
            center_pid=center_pid,
            center_address=row["center_address"],
            center_lat=float(row["center_lat"]),
            center_lng=float(row["center_lng"]),
            member_count=row["cluster_size"],
            members=members,
            radius_m=radius_m,
            window_days=window_days,
            total_proposed_units=total_units,
            neighborhoods=sorted(neighborhoods),
        )
        clusters.append(cluster)

    logger.info(f"Detected {len(clusters)} development clusters")
    return clusters
