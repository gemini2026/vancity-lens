"""
VCL-106 [PERF-018] Cursor-based pagination for opportunity endpoints.

Provides efficient cursor-based pagination using keyset pagination technique:
- Cursor encodes: id + sort_value (base64 JSON)
- Uses WHERE clause with comparison operators (> or <) for efficiency
- Handles composite cursors for stable sorting with tie-breaking
- Avoids OFFSET (which is slow on large tables)
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class CursorPaginationParams(BaseModel):
    """
    Parameters for cursor-based pagination.

    Attributes:
        cursor: Optional base64-encoded cursor string from previous response
        limit: Number of items to return (default 20, max 100)
        sort_by: Column name to sort by (default "created_at")
        sort_order: Sort direction, "asc" or "desc" (default "desc")
    """

    cursor: Optional[str] = Field(
        None,
        description="Opaque cursor from previous response"
    )
    limit: int = Field(
        20,
        ge=1,
        le=100,
        description="Items per page (max 100)"
    )
    sort_by: str = Field(
        "created_at",
        description="Column to sort by"
    )
    sort_order: str = Field(
        "desc",
        pattern="^(asc|desc)$",
        description="Sort order (asc or desc)"
    )

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v):
        """Ensure limit is within acceptable range."""
        if v < 1 or v > 100:
            raise ValueError("limit must be between 1 and 100")
        return v

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v):
        """Ensure sort_order is asc or desc."""
        if v not in ("asc", "desc"):
            raise ValueError("sort_order must be asc or desc")
        return v


class CursorPageResult(BaseModel):
    """
    Response model for cursor-based pagination.

    Attributes:
        items: List of items in this page
        next_cursor: Opaque cursor for next page (None if last page)
        previous_cursor: Opaque cursor for previous page (None if first page)
        has_more: Whether there are more items after this page
        total_count: Optional total count (only if requested)
    """

    items: List[Any] = Field(
        ...,
        description="Items in this page"
    )
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for next page, or null if no next page"
    )
    previous_cursor: Optional[str] = Field(
        None,
        description="Cursor for previous page, or null if no previous page"
    )
    has_more: bool = Field(
        ...,
        description="Whether there are more items after this page"
    )
    total_count: Optional[int] = Field(
        None,
        description="Total count of items (optional, only if requested)"
    )


def encode_cursor(item_id: Any, sort_value: Any) -> str:
    """
    Encode a cursor from item ID and sort value.

    Uses base64 JSON encoding for opaque cursor format.

    Args:
        item_id: The ID of the last item in this page
        sort_value: The sort field value of the last item

    Returns:
        Base64-encoded cursor string

    Raises:
        ValueError: If encoding fails
    """
    try:
        cursor_data = {
            "id": str(item_id),
            "sort_value": str(sort_value),
        }
        json_str = json.dumps(cursor_data, separators=(',', ':'))
        encoded = base64.b64encode(json_str.encode()).decode()
        return encoded
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to encode cursor: {e}")


def decode_cursor(cursor: str) -> tuple:
    """
    Decode a cursor into item ID and sort value.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Tuple of (item_id, sort_value)

    Raises:
        ValueError: If cursor is malformed or cannot be decoded
    """
    try:
        json_str = base64.b64decode(cursor.encode()).decode()
        cursor_data = json.loads(json_str)
        item_id = cursor_data.get("id")
        sort_value = cursor_data.get("sort_value")

        if item_id is None or sort_value is None:
            raise ValueError("Cursor missing id or sort_value")

        return item_id, sort_value
    except (base64.binascii.Error, json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Invalid cursor: {e}")


async def cursor_paginate(
    pool: Any,
    table: str,
    cursor_params: CursorPaginationParams,
    filters: Optional[Dict[str, Any]] = None,
    select_columns: Optional[List[str]] = None,
    compute_total: bool = False,
) -> CursorPageResult:
    """
    Execute cursor-based pagination query.

    Uses keyset pagination (WHERE clause with comparison operators)
    for efficient pagination without OFFSET.

    Args:
        pool: asyncpg connection pool
        table: Table name to query
        cursor_params: CursorPaginationParams instance
        filters: Optional dict of column:value filters (AND conditions)
        select_columns: Optional list of columns to select (all if None)
        compute_total: Whether to compute total count (slow on large tables)

    Returns:
        CursorPageResult with items, cursors, and has_more flag

    Raises:
        ValueError: If cursor is malformed
    """
    limit = cursor_params.limit
    sort_by = cursor_params.sort_by
    sort_order = cursor_params.sort_order

    columns = select_columns or ["*"]
    columns_str = ", ".join(columns)

    where_conditions = []
    params = []
    param_idx = 1

    if filters:
        for col, val in filters.items():
            where_conditions.append(f"{col} = ${param_idx}")
            params.append(val)
            param_idx += 1

    last_id = None
    last_sort_value = None

    if cursor_params.cursor:
        try:
            last_id, last_sort_value = decode_cursor(cursor_params.cursor)
        except ValueError as e:
            raise ValueError(f"Invalid cursor provided: {e}")

        comparison_op = ">" if sort_order == "asc" else "<"
        where_conditions.append(
            f"({sort_by}, id) {comparison_op} (${param_idx}, ${param_idx + 1})"
        )
        params.append(last_sort_value)
        params.append(last_id)
        param_idx += 2

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    query = f"SELECT {columns_str} FROM {table} WHERE {where_clause}"
    query += f" ORDER BY {sort_by} {sort_order}, id {sort_order}"
    query += f" LIMIT ${param_idx}"

    params.append(limit + 1)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        has_more = len(rows) > limit
        result_items = rows[:limit]

        next_cursor = None
        if has_more and result_items:
            last_item = result_items[-1]
            last_id = last_item.get("id") if isinstance(last_item, dict) else last_item[0]
            last_sort_val = (
                last_item.get(sort_by)
                if isinstance(last_item, dict)
                else getattr(last_item, sort_by, None)
            )
            if last_id is not None and last_sort_val is not None:
                next_cursor = encode_cursor(last_id, last_sort_val)

        previous_cursor = None
        if cursor_params.cursor:
            previous_cursor = cursor_params.cursor

        total_count = None
        if compute_total:
            count_query = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where_clause}"
            count_result = await conn.fetchrow(count_query, *params[:-1])
            total_count = count_result["cnt"] if count_result else 0

        return CursorPageResult(
            items=[dict(row) for row in result_items],
            next_cursor=next_cursor,
            previous_cursor=previous_cursor,
            has_more=has_more,
            total_count=total_count,
        )
