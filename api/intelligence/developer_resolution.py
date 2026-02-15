"""
Developer Entity Resolution (DV-PIPE-006).

Normalizes developer names to canonical entities for consistent pipeline
filtering and analytics. Handles:
- Case normalization
- Common abbreviation expansion (Corp → Corporation, Dev → Development)
- Whitespace/punctuation cleanup
- Fuzzy matching against known entities
"""

import logging
import re
from typing import Optional

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeveloperEntity(BaseModel):
    """A resolved developer entity."""
    id: int
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    bc_corp_number: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# Common abbreviation expansions for developer names
_ABBREVIATIONS = {
    r"\bCorp\b": "Corporation",
    r"\bInc\b": "Incorporated",
    r"\bLtd\b": "Limited",
    r"\bDev\b": "Development",
    r"\bProp\b": "Properties",
    r"\bGrp\b": "Group",
    r"\bMgmt\b": "Management",
    r"\bConstr\b": "Construction",
    r"\bBldrs?\b": "Builders",
    r"\bAssoc\b": "Associates",
    r"\bIntl?\b": "International",
}


def normalize_developer_name(name: str) -> str:
    """
    Normalize a developer name for matching.

    Steps:
    1. Strip whitespace, collapse multiple spaces
    2. Title case
    3. Expand common abbreviations
    4. Remove trailing punctuation (periods, commas)
    """
    if not name:
        return ""

    # Strip and collapse whitespace
    cleaned = " ".join(name.strip().split())

    # Remove trailing periods/commas
    cleaned = cleaned.rstrip(".,;")

    # Title case
    cleaned = cleaned.title()

    # Expand abbreviations
    for pattern, replacement in _ABBREVIATIONS.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Final cleanup
    cleaned = " ".join(cleaned.split())

    return cleaned


def _similarity_score(a: str, b: str) -> float:
    """Simple Levenshtein-based similarity ratio (0-1). No external deps."""
    a_lower = a.lower()
    b_lower = b.lower()

    if a_lower == b_lower:
        return 1.0

    # Check containment (one is substring of other)
    if a_lower in b_lower or b_lower in a_lower:
        return 0.85

    # Simple character overlap ratio
    set_a = set(a_lower)
    set_b = set(b_lower)
    intersection = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.0
    jaccard = len(intersection) / len(union)

    # Length-weighted similarity
    len_ratio = min(len(a), len(b)) / max(len(a), len(b)) if max(len(a), len(b)) > 0 else 0

    return (jaccard + len_ratio) / 2


# Threshold for fuzzy matching
_MATCH_THRESHOLD = 0.75


async def resolve_developer(
    conn: asyncpg.Connection,
    raw_name: str,
) -> Optional[DeveloperEntity]:
    """
    Resolve a raw developer name to a canonical entity.

    1. Normalize the name
    2. Exact match on canonical_name
    3. Exact match on aliases
    4. Fuzzy match on all known entities
    5. If no match found, create new entity

    Returns the matched or newly created DeveloperEntity.
    """
    if not raw_name or not raw_name.strip():
        return None

    normalized = normalize_developer_name(raw_name)

    # 1. Exact match on canonical_name
    row = await conn.fetchrow(
        "SELECT id, canonical_name, aliases, bc_corp_number, metadata "
        "FROM developer_entities WHERE LOWER(canonical_name) = LOWER($1)",
        normalized,
    )
    if row:
        return _row_to_entity(row)

    # 2. Check aliases (array contains, case-insensitive)
    row = await conn.fetchrow(
        "SELECT id, canonical_name, aliases, bc_corp_number, metadata "
        "FROM developer_entities WHERE LOWER($1) = ANY(SELECT LOWER(unnest(aliases)))",
        normalized,
    )
    if row:
        return _row_to_entity(row)

    # 3. Fuzzy match against all entities
    all_rows = await conn.fetch(
        "SELECT id, canonical_name, aliases, bc_corp_number, metadata "
        "FROM developer_entities"
    )
    best_match = None
    best_score = 0.0
    for r in all_rows:
        score = _similarity_score(normalized, r["canonical_name"])
        # Also check aliases
        for alias in (r["aliases"] or []):
            alias_score = _similarity_score(normalized, alias)
            score = max(score, alias_score)
        if score > best_score:
            best_score = score
            best_match = r

    if best_match and best_score >= _MATCH_THRESHOLD:
        # Add as alias if not already there
        entity = _row_to_entity(best_match)
        if normalized.lower() not in [a.lower() for a in entity.aliases]:
            await conn.execute(
                "UPDATE developer_entities SET aliases = array_append(aliases, $1) WHERE id = $2",
                normalized, entity.id,
            )
            entity.aliases.append(normalized)
            logger.info(f"Added alias '{normalized}' to entity '{entity.canonical_name}'")
        return entity

    # 4. No match — create new entity
    row = await conn.fetchrow(
        "INSERT INTO developer_entities (canonical_name, aliases) "
        "VALUES ($1, $2) "
        "RETURNING id, canonical_name, aliases, bc_corp_number, metadata",
        normalized, [raw_name] if raw_name != normalized else [],
    )
    logger.info(f"Created new developer entity: '{normalized}'")
    return _row_to_entity(row)


async def search_developers(
    conn: asyncpg.Connection,
    query: str,
    limit: int = 20,
) -> list[DeveloperEntity]:
    """Search developer entities by name (partial match)."""
    rows = await conn.fetch(
        "SELECT id, canonical_name, aliases, bc_corp_number, metadata "
        "FROM developer_entities "
        "WHERE canonical_name ILIKE $1 "
        "   OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE a ILIKE $1) "
        "ORDER BY canonical_name LIMIT $2",
        f"%{query}%", limit,
    )
    return [_row_to_entity(r) for r in rows]


def _row_to_entity(row) -> DeveloperEntity:
    return DeveloperEntity(
        id=row["id"],
        canonical_name=row["canonical_name"],
        aliases=row["aliases"] or [],
        bc_corp_number=row["bc_corp_number"],
        metadata=row["metadata"] or {},
    )
