"""Saved views (filter persistence) logic."""

from .db import db


async def create_view(user_id: int, name: str, filters: dict) -> dict:
    pool = await db.get_pool()
    row = await pool.fetchrow(
        """INSERT INTO saved_views (user_id, name, filters)
           VALUES ($1, $2, $3::jsonb)
           RETURNING id, name, filters, created_at""",
        user_id,
        name,
        __import__("json").dumps(filters),
    )
    return dict(row)


async def list_views(user_id: int) -> list[dict]:
    pool = await db.get_pool()
    rows = await pool.fetch(
        "SELECT id, name, filters, created_at FROM saved_views WHERE user_id = $1 ORDER BY created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def delete_view(user_id: int, view_id: int) -> bool:
    pool = await db.get_pool()
    result = await pool.execute(
        "DELETE FROM saved_views WHERE id = $1 AND user_id = $2",
        view_id,
        user_id,
    )
    return result == "DELETE 1"
