"""
VCL-83 [PERF-012] Frontend pagination enforcement for VanCity Lens.

Provides:
- PaginationParams: FastAPI Depends for page/page_size/sort validation
- PaginatedResponse: Generic response model with pagination metadata
- paginate() helper: Converts query results to paginated responses
- MaxPageSizeMiddleware: Enforces max page size limits
- CursorPagination: Stable cursor-based pagination with encoding/decoding
"""

import base64
import json
import logging
import os
from typing import Generic, Optional, TypeVar, List, Any

from fastapi import Query
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Type variable for generic response models
T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────
# PaginationParams - FastAPI Depends for query parameter validation
# ──────────────────────────────────────────────────────────────────────────


class PaginationParams:
    """
    Pagination parameters for FastAPI endpoints.

    Use as a Depends() in route handlers:
        async def my_endpoint(params: PaginationParams = Depends()):
            # params.page, params.page_size, params.offset, params.limit available
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(
            20, ge=1, le=100, description="Items per page (max 100)"
        ),
        sort_by: Optional[str] = Query(None, description="Field to sort by"),
        sort_order: str = Query(
            "desc", pattern="^(asc|desc)$", description="Sort order (asc or desc)"
        ),
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_order = sort_order

    @property
    def offset(self) -> int:
        """Calculate offset from page and page_size."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size (used in SQL queries)."""
        return self.page_size


# ──────────────────────────────────────────────────────────────────────────
# PaginatedResponse - Generic model for paginated responses
# ──────────────────────────────────────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response model.

    Example usage:
        response = PaginatedResponse[SignalResponse](
            items=signals,
            total=100,
            page=1,
            page_size=20
        )
    """

    items: List[T] = Field(..., description="Items in this page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(
        ..., description="Whether there are more pages after this one"
    )
    has_prev: bool = Field(..., description="Whether there are pages before this one")
    next_page: Optional[int] = Field(
        None, ge=1, description="Next page number, or null if no next page"
    )
    prev_page: Optional[int] = Field(
        None, ge=1, description="Previous page number, or null if no previous page"
    )

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int):
        """
        Factory method to create a PaginatedResponse with computed metadata.

        Args:
            items: List of items for this page
            total: Total count across all pages
            page: Current page number (1-indexed)
            page_size: Items per page

        Returns:
            PaginatedResponse with all metadata computed
        """
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1
        next_page = page + 1 if has_next else None
        prev_page = page - 1 if has_prev else None

        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
            next_page=next_page,
            prev_page=prev_page,
        )


# ──────────────────────────────────────────────────────────────────────────
# paginate() Helper Function
# ──────────────────────────────────────────────────────────────────────────


def paginate(
    items: List[T],
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponse:
    """
    Convert query results and metadata into a PaginatedResponse.

    This is a convenience helper that avoids having to manually compute
    total_pages, has_next, etc.

    Args:
        items: List of items to return in this page
        total: Total count of items across all pages
        page: Current page number (1-indexed)
        page_size: Items per page

    Returns:
        PaginatedResponse with all pagination metadata

    Example:
        rows = await conn.fetch("SELECT * FROM signals LIMIT $1 OFFSET $2", limit, offset)
        count_row = await conn.fetchrow("SELECT count(*) FROM signals")
        return paginate(rows, count_row['count'], page=1, page_size=20)
    """
    return PaginatedResponse.create(items, total, page, page_size)


# ──────────────────────────────────────────────────────────────────────────
# MaxPageSizeMiddleware - Enforces maximum page size
# ──────────────────────────────────────────────────────────────────────────


class MaxPageSizeMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce maximum page size across all endpoints.

    Reads MAX_PAGE_SIZE environment variable (default 100).
    Rejects requests where page_size query parameter exceeds this limit.

    This prevents abuse and ensures consistent resource usage.
    """

    def __init__(self, app, max_page_size: Optional[int] = None):
        super().__init__(app)
        if max_page_size is not None:
            self.max_page_size = max_page_size
        else:
            self.max_page_size = int(os.getenv("MAX_PAGE_SIZE", "100"))

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only check pagination-related endpoints
        if request.method == "GET":
            page_size_param = request.query_params.get("page_size")
            if page_size_param:
                try:
                    page_size = int(page_size_param)
                    if page_size > self.max_page_size:
                        return Response(
                            content=json.dumps(
                                {
                                    "detail": f"page_size {page_size} exceeds maximum {self.max_page_size}"
                                }
                            ),
                            status_code=400,
                            media_type="application/json",
                        )
                except (ValueError, TypeError):
                    # Invalid page_size format, let FastAPI handle validation
                    pass

        return await call_next(request)


# ──────────────────────────────────────────────────────────────────────────
# Cursor-Based Pagination
# ──────────────────────────────────────────────────────────────────────────


class CursorPaginationParams(BaseModel):
    """
    Parameters for cursor-based pagination.

    Cursor-based pagination is more stable than offset/limit pagination
    when the dataset is being modified (inserts/deletes), as it doesn't
    require tracking absolute positions.
    """

    cursor: Optional[str] = Field(
        None, description="Opaque cursor from previous response for next page"
    )
    page_size: int = Field(20, ge=1, le=100, description="Number of items to return")
    sort_order: str = Field(
        "desc", pattern="^(asc|desc)$", description="Sort order (asc or desc)"
    )

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v):
        """Ensure page_size is reasonable."""
        if v < 1 or v > 1000:
            raise ValueError("page_size must be between 1 and 1000")
        return v


class CursorPaginationResponse(BaseModel, Generic[T]):
    """
    Response model for cursor-based pagination.

    Includes a cursor for the next page if available.
    """

    items: List[T] = Field(..., description="Items in this page")
    cursor: Optional[str] = Field(
        None, description="Opaque cursor to fetch next page, or null if no next page"
    )
    has_next: bool = Field(
        ..., description="Whether there are more items after this page"
    )
    count: int = Field(..., ge=0, description="Number of items in this page")


class CursorPagination:
    """
    Utilities for cursor-based pagination.

    Encodes/decodes opaque cursors that contain the last item ID and sort value.
    """

    @staticmethod
    def encode_cursor(last_id: Any, last_sort_value: Any) -> str:
        """
        Encode a cursor from the last item's ID and sort value.

        Args:
            last_id: The ID of the last item in this page
            last_sort_value: The sort field value of the last item

        Returns:
            Base64-encoded opaque cursor string
        """
        cursor_data = {
            "id": str(last_id),
            "sort_value": str(last_sort_value),
        }
        json_str = json.dumps(cursor_data, separators=(",", ":"))
        encoded = base64.b64encode(json_str.encode()).decode()
        return encoded

    @staticmethod
    def decode_cursor(cursor: str) -> tuple[Any, Any]:
        """
        Decode a cursor into its ID and sort value.

        Args:
            cursor: Base64-encoded cursor string from encode_cursor()

        Returns:
            Tuple of (last_id, last_sort_value)

        Raises:
            ValueError: If cursor is malformed
        """
        try:
            json_str = base64.b64decode(cursor.encode()).decode()
            cursor_data = json.loads(json_str)
            return cursor_data["id"], cursor_data["sort_value"]
        except (base64.binascii.Error, json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid cursor: {e}")

    @staticmethod
    def create_response(
        items: List[T],
        page_size: int,
        sort_order: str,
    ) -> CursorPaginationResponse:
        """
        Create a cursor pagination response.

        If we received page_size+1 items, the last item indicates there's a next page.
        Strip it from results and generate a cursor.

        Args:
            items: Items fetched (should be page_size or page_size+1)
            page_size: Requested page size
            sort_order: Sort order used

        Returns:
            CursorPaginationResponse with cursor set if has_next
        """
        has_next = len(items) > page_size
        result_items = items[:page_size]

        cursor = None
        if has_next and result_items:
            last_item = result_items[-1]
            # Assume last_item has 'id' and a sort field (e.g., 'created_at')
            # Subclasses should override this logic if needed
            last_id = getattr(last_item, "id", None)
            # Try to find a reasonable sort value
            last_sort_value = getattr(last_item, "created_at", None) or getattr(
                last_item, "updated_at", None
            )
            if last_id is not None and last_sort_value is not None:
                cursor = CursorPagination.encode_cursor(last_id, last_sort_value)

        return CursorPaginationResponse(
            items=result_items,
            cursor=cursor,
            has_next=has_next,
            count=len(result_items),
        )
