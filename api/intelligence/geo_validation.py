"""
VanCity Lens — Geographic Scope Validation (DV-REG-004)

Validates and resolves geographic references in extracted signals
to valid Vancouver neighborhoods and zoning districts.
"""

import logging
from typing import Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)

# Canonical Vancouver neighborhoods (22 official)
VANCOUVER_NEIGHBORHOODS = {
    "Arbutus Ridge",
    "Downtown",
    "Dunbar-Southlands",
    "Fairview",
    "Grandview-Woodland",
    "Hastings-Sunrise",
    "Kensington-Cedar Cottage",
    "Kerrisdale",
    "Killarney",
    "Kitsilano",
    "Marpole",
    "Mount Pleasant",
    "Oakridge",
    "Renfrew-Collingwood",
    "Riley Park",
    "Shaughnessy",
    "South Cambie",
    "Strathcona",
    "Sunset",
    "Victoria-Fraserview",
    "West End",
    "West Point Grey",
}

# Common aliases → canonical name
NEIGHBORHOOD_ALIASES = {
    "arbutus": "Arbutus Ridge",
    "cbd": "Downtown",
    "downtown vancouver": "Downtown",
    "dunbar": "Dunbar-Southlands",
    "southlands": "Dunbar-Southlands",
    "fairview slopes": "Fairview",
    "grandview": "Grandview-Woodland",
    "commercial drive": "Grandview-Woodland",
    "the drive": "Grandview-Woodland",
    "hastings": "Hastings-Sunrise",
    "sunrise": "Hastings-Sunrise",
    "kensington": "Kensington-Cedar Cottage",
    "cedar cottage": "Kensington-Cedar Cottage",
    "kits": "Kitsilano",
    "mt pleasant": "Mount Pleasant",
    "mt. pleasant": "Mount Pleasant",
    "renfrew": "Renfrew-Collingwood",
    "collingwood": "Renfrew-Collingwood",
    "riley park-little mountain": "Riley Park",
    "little mountain": "Riley Park",
    "cambie": "South Cambie",
    "victoria": "Victoria-Fraserview",
    "fraserview": "Victoria-Fraserview",
    "point grey": "West Point Grey",
    # Metro Vancouver municipalities (not neighborhoods but useful)
    "burnaby": None,  # Flag as non-Vancouver
    "surrey": None,
    "richmond": None,
    "north vancouver": None,
    "coquitlam": None,
    "new westminster": None,
}

# Valid Vancouver zoning prefixes
VALID_ZONING_PREFIXES = [
    "RS-",
    "RT-",
    "RM-",
    "FM-",
    "C-",
    "CD-",
    "DD-",
    "FC-",
    "HA-",
    "I-",
    "IC-",
    "M-",
    "MC-",
    "FCCDD-",
    "BCPED",
    "CWD",
    "DEOD",
]


def resolve_neighborhood(name: Optional[str]) -> Tuple[Optional[str], bool]:
    """
    Resolve a neighborhood reference to a canonical name.

    Returns:
        (canonical_name, is_valid) — canonical name if resolved, validity flag
    """
    if not name:
        return None, False

    name_stripped = name.strip()

    # Direct match (case-insensitive)
    for canonical in VANCOUVER_NEIGHBORHOODS:
        if name_stripped.lower() == canonical.lower():
            return canonical, True

    # Alias match
    name_lower = name_stripped.lower()
    if name_lower in NEIGHBORHOOD_ALIASES:
        canonical = NEIGHBORHOOD_ALIASES[name_lower]
        if canonical is None:
            # Non-Vancouver municipality
            return name_stripped, False
        return canonical, True

    # Partial match — check if any canonical name contains the input
    for canonical in VANCOUVER_NEIGHBORHOODS:
        if name_lower in canonical.lower() or canonical.lower() in name_lower:
            return canonical, True

    return name_stripped, False


def validate_zoning(zoning: Optional[str]) -> bool:
    """Check if a zoning code matches known Vancouver zoning prefixes."""
    if not zoning:
        return False
    zoning_upper = zoning.strip().upper()
    return any(zoning_upper.startswith(prefix) for prefix in VALID_ZONING_PREFIXES)


async def resolve_neighborhood_from_db(
    conn: asyncpg.Connection, name: str
) -> Optional[str]:
    """
    Resolve a neighborhood name using the vancouver_neighborhoods lookup table.
    Falls back to the in-memory aliases if DB table doesn't exist.
    """
    try:
        row = await conn.fetchrow(
            """
            SELECT name FROM vancouver_neighborhoods
            WHERE name ILIKE $1
               OR $1 = ANY(alternate_names)
            LIMIT 1
        """,
            name.strip(),
        )
        if row:
            return row["name"]
    except Exception:
        pass  # Table may not exist yet

    # Fall back to in-memory resolution
    canonical, is_valid = resolve_neighborhood(name)
    return canonical if is_valid else None


def validate_event_date_range(
    event_date_str: Optional[str],
) -> Tuple[bool, Optional[str]]:
    """
    DV-REG-003: Validate effective/event date.

    Returns:
        (is_valid, reason) — True if valid, reason if invalid
    """
    if not event_date_str:
        return True, None  # Null is acceptable

    from datetime import date, timedelta

    try:
        if isinstance(event_date_str, date):
            event_date = event_date_str
        else:
            event_date = date.fromisoformat(str(event_date_str)[:10])
    except (ValueError, TypeError):
        return False, f"Invalid date format: {event_date_str}"

    # Date shouldn't be more than 5 years in the past
    min_date = date.today() - timedelta(days=365 * 5)
    if event_date < min_date:
        return False, f"Date {event_date} is more than 5 years old"

    # Date shouldn't be more than 1 year in the future
    max_date = date.today() + timedelta(days=365)
    if event_date > max_date:
        return False, f"Date {event_date} is more than 1 year in the future"

    return True, None
