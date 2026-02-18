"""Organization / team account logic."""

import re
from .db import db


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def create_org(name: str, owner_id: int) -> dict:
    pool = await db.get_pool()
    slug = _slugify(name)
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO organizations (name, slug)
                   VALUES ($1, $2)
                   RETURNING id, name, slug, plan, max_seats, created_at""",
                name,
                slug,
            )
            await conn.execute(
                """INSERT INTO org_members (org_id, user_id, role)
                   VALUES ($1, $2, 'owner')""",
                row["id"],
                owner_id,
            )
    return dict(row)


async def get_org(org_id: int) -> dict | None:
    pool = await db.get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, slug, plan, max_seats, created_at FROM organizations WHERE id = $1",
        org_id,
    )
    return dict(row) if row else None


async def list_user_orgs(user_id: int) -> list[dict]:
    pool = await db.get_pool()
    rows = await pool.fetch(
        """SELECT o.id, o.name, o.slug, o.plan, om.role
           FROM organizations o
           JOIN org_members om ON om.org_id = o.id
           WHERE om.user_id = $1
           ORDER BY o.name""",
        user_id,
    )
    return [dict(r) for r in rows]


async def list_members(org_id: int) -> list[dict]:
    pool = await db.get_pool()
    rows = await pool.fetch(
        """SELECT om.id, om.user_id, om.role, om.joined_at,
                  u.email, u.full_name
           FROM org_members om
           JOIN users u ON u.id = om.user_id
           WHERE om.org_id = $1
           ORDER BY om.role, u.full_name""",
        org_id,
    )
    return [dict(r) for r in rows]


async def add_member(
    org_id: int, user_email: str, role: str = "member", invited_by: int | None = None
) -> dict | None:
    pool = await db.get_pool()
    user = await pool.fetchrow(
        "SELECT id, email, full_name FROM users WHERE email = $1", user_email
    )
    if not user:
        return None
    org = await get_org(org_id)
    if not org:
        return None
    # Check seat limit
    current = await pool.fetchval(
        "SELECT COUNT(*) FROM org_members WHERE org_id = $1", org_id
    )
    if current >= org["max_seats"]:
        return None
    row = await pool.fetchrow(
        """INSERT INTO org_members (org_id, user_id, role, invited_by)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (org_id, user_id) DO UPDATE SET role = $3
           RETURNING id, user_id, role, joined_at""",
        org_id,
        user["id"],
        role,
        invited_by,
    )
    result = dict(row)
    result["email"] = user["email"]
    result["full_name"] = user["full_name"]
    return result


async def remove_member(org_id: int, user_id: int) -> bool:
    pool = await db.get_pool()
    result = await pool.execute(
        "DELETE FROM org_members WHERE org_id = $1 AND user_id = $2 AND role != 'owner'",
        org_id,
        user_id,
    )
    return result == "DELETE 1"
