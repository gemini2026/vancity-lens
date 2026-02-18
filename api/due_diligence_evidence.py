"""
Due Diligence Evidence (VCL-??)

Collects *verifiable* evidence for due diligence checklist items and returns it
with source links so it can be shown in the UI and included in PDFs.

Scope (initial):
1) Utilities (water/sewer): proximity evidence using City of Vancouver open data
2) Encumbrances proxy: property easements intersecting the parcel (open data)
3) OCP/policy excerpts: relevant plan/legislation snippets with citations from ingested docs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Literal

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvidenceSource(BaseModel):
    label: str
    url: str


class UtilityNearestAsset(BaseModel):
    asset_id: Optional[str] = None
    line_type: Optional[str] = None
    diameter_mm: Optional[float] = None
    material: Optional[str] = None
    distance_m: float


class UtilityEvidence(BaseModel):
    status: Literal["ok", "not_loaded", "not_configured", "error"]
    nearest_distance_m: Optional[float] = None
    nearest_assets: list[UtilityNearestAsset] = Field(default_factory=list)
    source: Optional[EvidenceSource] = None
    note: Optional[str] = None


class UtilitiesEvidence(BaseModel):
    status: Literal["ok", "partial", "not_loaded", "not_configured", "error"]
    water: UtilityEvidence
    sewer: UtilityEvidence


class EasementEvidenceItem(BaseModel):
    easement_type: str
    plan_number: Optional[str] = None


class EncumbrancesEvidence(BaseModel):
    status: Literal["ok", "not_loaded", "not_configured", "error"]
    easement_count: Optional[int] = None
    easements: list[EasementEvidenceItem] = Field(default_factory=list)
    source: Optional[EvidenceSource] = None
    note: Optional[str] = None


class PolicyExcerpt(BaseModel):
    title: Optional[str] = None
    source_url: str
    source_type: Optional[str] = None
    section_header: Optional[str] = None
    excerpt: str


class PolicyEvidence(BaseModel):
    status: Literal["ok", "not_loaded", "no_matches", "not_configured", "error"]
    query: str
    excerpts: list[PolicyExcerpt] = Field(default_factory=list)
    note: Optional[str] = None


class DueDiligenceEvidenceResponse(BaseModel):
    pid: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    utilities: UtilitiesEvidence
    encumbrances_proxy: EncumbrancesEvidence
    ocp_policy_excerpts: PolicyEvidence


DEFAULT_WATER_SOURCE = EvidenceSource(
    label="City of Vancouver Open Data - Water Distribution Mains",
    url="https://opendata.vancouver.ca/explore/dataset/water-distribution-mains/",
)
DEFAULT_SEWER_SOURCE = EvidenceSource(
    label="City of Vancouver Open Data - Sewer Mains",
    url="https://opendata.vancouver.ca/explore/dataset/sewer-mains/",
)
DEFAULT_EASEMENTS_SOURCE = EvidenceSource(
    label="City of Vancouver Open Data - Property Easements",
    url="https://opendata.vancouver.ca/explore/dataset/property-easements/",
)


async def _utility_evidence_for_type(
    conn: asyncpg.Connection,
    *,
    pid: str,
    utility_type: str,
    default_source: EvidenceSource,
) -> UtilityEvidence:
    try:
        has_any = await conn.fetchval(
            "SELECT 1 FROM utility_lines WHERE utility_type = $1 LIMIT 1",
            utility_type,
        )
    except asyncpg.exceptions.UndefinedTableError:
        return UtilityEvidence(
            status="not_configured",
            source=default_source,
            note="utility_lines table missing (run /api/v1/admin/run-migrations or re-init DB)",
        )
    except Exception as e:
        logger.exception("utility evidence check failed")
        return UtilityEvidence(status="error", source=default_source, note=str(e)[:200])

    if not has_any:
        return UtilityEvidence(
            status="not_loaded",
            source=default_source,
            note="No utility lines loaded yet (run /api/v1/admin/load-utilities-water|sewer).",
        )

    try:
        rows = await conn.fetch(
            """
            SELECT
                u.asset_id,
                u.line_type,
                u.diameter_mm,
                u.material,
                u.source_url,
                ROUND(ST_Distance(
                    p.geom::geography,
                    u.geom::geography
                )::numeric, 1) AS distance_m
            FROM parcels p
            JOIN utility_lines u ON u.utility_type = $2
            WHERE p.pid = $1
            ORDER BY p.geom <-> u.geom
            LIMIT 3
            """,
            pid,
            utility_type,
        )
    except Exception as e:
        logger.exception("utility evidence query failed")
        return UtilityEvidence(status="error", source=default_source, note=str(e)[:200])

    nearest_assets: list[UtilityNearestAsset] = []
    source_url: Optional[str] = None
    for r in rows:
        if not source_url and r.get("source_url"):
            source_url = r["source_url"]
        nearest_assets.append(
            UtilityNearestAsset(
                asset_id=r.get("asset_id"),
                line_type=r.get("line_type"),
                diameter_mm=float(r["diameter_mm"])
                if r.get("diameter_mm") is not None
                else None,
                material=r.get("material"),
                distance_m=float(r["distance_m"]),
            )
        )

    nearest_distance_m = nearest_assets[0].distance_m if nearest_assets else None
    source = EvidenceSource(
        label=default_source.label, url=source_url or default_source.url
    )
    return UtilityEvidence(
        status="ok",
        nearest_distance_m=nearest_distance_m,
        nearest_assets=nearest_assets,
        source=source,
    )


async def _encumbrances_proxy_evidence(
    conn: asyncpg.Connection, *, pid: str
) -> EncumbrancesEvidence:
    try:
        has_any = await conn.fetchval("SELECT 1 FROM property_easements LIMIT 1")
    except asyncpg.exceptions.UndefinedTableError:
        return EncumbrancesEvidence(
            status="not_configured",
            source=DEFAULT_EASEMENTS_SOURCE,
            note="property_easements table missing (run /api/v1/admin/run-migrations or re-init DB)",
        )
    except Exception as e:
        logger.exception("encumbrances proxy check failed")
        return EncumbrancesEvidence(
            status="error", source=DEFAULT_EASEMENTS_SOURCE, note=str(e)[:200]
        )

    if not has_any:
        return EncumbrancesEvidence(
            status="not_loaded",
            source=DEFAULT_EASEMENTS_SOURCE,
            note="No easements loaded yet (run /api/v1/admin/load-easements).",
        )

    try:
        easement_count = await conn.fetchval(
            """
            SELECT count(*)
            FROM parcels p
            JOIN property_easements e ON ST_Intersects(p.geom, e.geom)
            WHERE p.pid = $1
            """,
            pid,
        )
        rows = await conn.fetch(
            """
            SELECT e.easement_type, e.plan_number
            FROM parcels p
            JOIN property_easements e ON ST_Intersects(p.geom, e.geom)
            WHERE p.pid = $1
            LIMIT 10
            """,
            pid,
        )
    except Exception as e:
        logger.exception("encumbrances proxy query failed")
        return EncumbrancesEvidence(
            status="error", source=DEFAULT_EASEMENTS_SOURCE, note=str(e)[:200]
        )

    easements = [
        EasementEvidenceItem(
            easement_type=(r.get("easement_type") or "").strip() or "Easement",
            plan_number=(r.get("plan_number") or None),
        )
        for r in rows
    ]
    return EncumbrancesEvidence(
        status="ok",
        easement_count=int(easement_count or 0),
        easements=easements,
        source=DEFAULT_EASEMENTS_SOURCE,
        note="Open-data proxy only. Confirm via LTSA title search for authoritative encumbrances.",
    )


async def _policy_excerpts_evidence(
    conn: asyncpg.Connection,
    *,
    pid: str,
    civic_address: Optional[str],
    current_zoning: Optional[str],
    geo_local_area: Optional[str],
) -> PolicyEvidence:
    # We want a resilient query that returns *some* policy/legislation snippets even when
    # parcel-specific terms (e.g. zoning codes) aren't mentioned verbatim in documents.
    #
    # `plainto_tsquery()` uses AND semantics across all terms, which is too strict here.
    # Use `websearch_to_tsquery()` with explicit OR terms instead.
    def _ws_term(term: str) -> str:
        t = " ".join((term or "").split()).strip()
        if not t:
            return ""
        t = t.replace('"', "")
        # Quote anything that could be mis-parsed (spaces, hyphens, etc.).
        if any(ch in t for ch in (" ", "-", ":", "/")):
            return f'"{t}"'
        return t

    terms: list[str] = []
    if geo_local_area:
        terms.append(_ws_term(geo_local_area))
    if current_zoning:
        terms.append(_ws_term(current_zoning))

    # Generic planning + Bill 47/TOD terms (keep small and high-signal).
    terms.extend(
        [
            '"bill 47"',
            '"transit oriented"',
            "zoning",
            "height",
            "fsr",
            "density",
            "plan",
        ]
    )

    query = " OR ".join([t for t in terms if t]) or _ws_term(civic_address or pid)

    # Prefer official sources, but fall back to any ingested docs.
    preferred_source_types = [
        "syc_plan_document",
        "syc_plan_page",
        "provincial_legislation",
        "provincial_policy",
    ]

    try:
        any_chunks = await conn.fetchval("SELECT 1 FROM document_chunks LIMIT 1")
    except asyncpg.exceptions.UndefinedTableError:
        return PolicyEvidence(
            status="not_configured",
            query=query,
            note="document_chunks table missing (intelligence layer not installed).",
        )
    except Exception as e:
        logger.exception("policy evidence availability check failed")
        return PolicyEvidence(status="error", query=query, note=str(e)[:200])

    if not any_chunks:
        return PolicyEvidence(
            status="not_loaded",
            query=query,
            note="No document chunks available yet. Ingest sources and chunk documents first.",
        )

    async def _search(source_types: list[str], limit: int) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT
                d.title,
                d.source_url,
                d.source_type,
                dc.section_header,
                LEFT(dc.chunk_text, 450) AS excerpt
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id,
                 websearch_to_tsquery('english', $1) q
            WHERE dc.chunk_tsvector @@ q
              AND d.source_type = ANY($2::text[])
            ORDER BY ts_rank_cd(dc.chunk_tsvector, q) DESC
            LIMIT $3
            """,
            query,
            source_types,
            limit,
        )

    try:
        rows = await _search(preferred_source_types, limit=5)
        if len(rows) < 3:
            # Fall back to any source types.
            rows = await conn.fetch(
                """
                SELECT
                    d.title,
                    d.source_url,
                    d.source_type,
                    dc.section_header,
                    LEFT(dc.chunk_text, 450) AS excerpt
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id,
                     websearch_to_tsquery('english', $1) q
                WHERE dc.chunk_tsvector @@ q
                ORDER BY ts_rank_cd(dc.chunk_tsvector, q) DESC
                LIMIT 5
                """,
                query,
            )
    except Exception as e:
        logger.exception("policy excerpt query failed")
        return PolicyEvidence(status="error", query=query, note=str(e)[:200])

    excerpts: list[PolicyExcerpt] = []
    for r in rows:
        source_url = r.get("source_url")
        if not source_url:
            continue
        excerpts.append(
            PolicyExcerpt(
                title=r.get("title"),
                source_url=source_url,
                source_type=r.get("source_type"),
                section_header=r.get("section_header"),
                excerpt=(r.get("excerpt") or "").strip(),
            )
        )

    if not excerpts:
        return PolicyEvidence(status="no_matches", query=query, excerpts=[])

    return PolicyEvidence(status="ok", query=query, excerpts=excerpts)


async def build_due_diligence_evidence(
    conn: asyncpg.Connection, pid: str
) -> DueDiligenceEvidenceResponse:
    """
    Build due diligence evidence for a parcel.

    Raises:
        ValueError: if PID does not exist.
    """
    parcel = await conn.fetchrow(
        """
        SELECT pid, civic_address, current_zoning, geo_local_area
        FROM parcels
        WHERE pid = $1
        LIMIT 1
        """,
        pid,
    )
    if not parcel:
        raise ValueError(f"Parcel {pid} not found")

    utilities_water = await _utility_evidence_for_type(
        conn,
        pid=pid,
        utility_type="water",
        default_source=DEFAULT_WATER_SOURCE,
    )
    utilities_sewer = await _utility_evidence_for_type(
        conn,
        pid=pid,
        utility_type="sewer",
        default_source=DEFAULT_SEWER_SOURCE,
    )

    # Aggregate utilities status
    util_statuses = {utilities_water.status, utilities_sewer.status}
    if util_statuses == {"ok"}:
        utilities_status: Literal[
            "ok", "partial", "not_loaded", "not_configured", "error"
        ] = "ok"
    elif "error" in util_statuses:
        utilities_status = "error"
    elif "ok" in util_statuses:
        utilities_status = "partial"
    elif util_statuses == {"not_loaded"}:
        utilities_status = "not_loaded"
    elif util_statuses == {"not_configured"}:
        utilities_status = "not_configured"
    else:
        utilities_status = "partial"

    encumbrances = await _encumbrances_proxy_evidence(conn, pid=pid)
    policy = await _policy_excerpts_evidence(
        conn,
        pid=pid,
        civic_address=parcel.get("civic_address"),
        current_zoning=parcel.get("current_zoning"),
        geo_local_area=parcel.get("geo_local_area"),
    )

    return DueDiligenceEvidenceResponse(
        pid=pid,
        utilities=UtilitiesEvidence(
            status=utilities_status,
            water=utilities_water,
            sewer=utilities_sewer,
        ),
        encumbrances_proxy=encumbrances,
        ocp_policy_excerpts=policy,
    )
