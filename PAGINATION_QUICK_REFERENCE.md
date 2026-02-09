# VCL-83 Pagination - Quick Reference Guide

## Quick Start

### Add pagination to a new endpoint (Recommended)

```python
from fastapi import FastAPI, Query
from api.pagination import paginate

@app.get("/api/v1/items")
async def list_items(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    # Calculate offset
    offset = (page - 1) * page_size

    # Fetch data and count
    items = await db.fetch("SELECT * FROM items LIMIT $1 OFFSET $2", page_size, offset)
    total = await db.fetchval("SELECT count(*) FROM items")

    # Return paginated response
    return paginate(items, total, page, page_size)
```

### Add pagination to existing endpoint (with backward compatibility)

```python
@app.get("/api/v1/items")
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int = Query(None),  # Legacy support
    offset: int = Query(None),  # Legacy support
):
    # Support legacy parameters
    if limit is not None or offset is not None:
        limit = limit or 20
        offset = offset or 0
        page = (offset // limit) + 1 if limit > 0 else 1
        page_size = limit

    # ... rest of implementation
    return paginate(items, total, page, page_size)
```

## API Examples

### Basic pagination
```
GET /api/v1/items?page=1&page_size=20
```

Response:
```json
{
  "items": [...],
  "total": 500,
  "page": 1,
  "page_size": 20,
  "total_pages": 25,
  "has_next": true,
  "has_prev": false,
  "next_page": 2,
  "prev_page": null
}
```

### Navigate to page 5
```
GET /api/v1/items?page=5&page_size=20
```

### Larger page size
```
GET /api/v1/items?page=1&page_size=50
```

### Legacy limit/offset (still supported)
```
GET /api/v1/items?limit=25&offset=50
```

## Configuration

### Set maximum page size globally
```bash
export MAX_PAGE_SIZE=100  # In environment or .env file
```

Or in code:
```python
from api.pagination import MaxPageSizeMiddleware
app.add_middleware(MaxPageSizeMiddleware, max_page_size=50)
```

## Common Patterns

### Pattern 1: Using PaginationParams with Depends

```python
from fastapi import Depends
from api.pagination import PaginationParams

@app.get("/items")
async def list_items(params: PaginationParams = Depends()):
    offset = params.offset      # (page-1) * page_size
    limit = params.limit        # page_size
    sort_by = params.sort_by    # Optional field to sort by
    sort_order = params.sort_order  # "asc" or "desc"

    # Fetch and return
    return paginate(items, total, params.page, params.page_size)
```

### Pattern 2: Direct parameters (more explicit)

```python
@app.get("/items")
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    # ... fetch data ...
    return paginate(items, total, page, page_size)
```

### Pattern 3: Cursor-based pagination (for large datasets)

```python
from api.pagination import CursorPagination, CursorPaginationParams

@app.get("/items")
async def list_items(params: CursorPaginationParams = Depends()):
    # Fetch one extra to detect has_next
    items = await db.fetch(
        "SELECT * FROM items WHERE ... LIMIT $1",
        params.page_size + 1
    )
    return CursorPagination.create_response(items, params.page_size, params.sort_order)
```

## Response Structure

All paginated endpoints return:

```python
{
    "items": [],              # List of items for this page
    "total": int,             # Total count across all pages
    "page": int,              # Current page number (1-indexed)
    "page_size": int,         # Items per page
    "total_pages": int,       # Total number of pages
    "has_next": bool,         # Whether there's a next page
    "has_prev": bool,         # Whether there's a previous page
    "next_page": int|null,    # Next page number or null
    "prev_page": int|null     # Previous page number or null
}
```

## Error Responses

### Invalid page (must be ≥1)
```
400 Bad Request
{
    "detail": "ensure this value is greater than or equal to 1"
}
```

### Invalid page_size (must be 1-100)
```
400 Bad Request
{
    "detail": "ensure this value is less than or equal to 100"
}
```

### page_size exceeds MAX_PAGE_SIZE
```
400 Bad Request
{
    "detail": "page_size 150 exceeds maximum 100"
}
```

### Invalid sort_order (must be asc or desc)
```
400 Bad Request
{
    "detail": "string should match pattern '^(asc|desc)$'"
}
```

## Performance Tips

1. **Always compute total count separately**: Use `SELECT count(*)` once per request
2. **Use OFFSET for small datasets**: Efficient for < 100k rows
3. **Use cursor pagination for large datasets**: More stable when data changes
4. **Set reasonable MAX_PAGE_SIZE**: Prevents resource exhaustion (default 100)
5. **Index sort fields**: Add database indexes on columns used for sorting

## Testing

```python
import pytest
from fastapi.testclient import TestClient

def test_pagination(app):
    client = TestClient(app)

    # Test first page
    response = client.get("/api/v1/items?page=1&page_size=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 20
    assert data["has_next"] is True
    assert data["next_page"] == 2

    # Test last page
    response = client.get("/api/v1/items?page=10&page_size=20")
    assert data["has_next"] is False
    assert data["prev_page"] == 9
```

## Migration Checklist

- [ ] Import pagination module: `from api.pagination import paginate`
- [ ] Add query parameters: `page`, `page_size` (and optionally `sort_by`, `sort_order`)
- [ ] Calculate offset: `offset = (page - 1) * page_size`
- [ ] Fetch total count: `total = await db.fetchval("SELECT count(*) FROM ...")`
- [ ] Fetch paginated results: `LIMIT $1 OFFSET $2`
- [ ] Return response: `return paginate(items, total, page, page_size)`
- [ ] Update tests to verify pagination metadata
- [ ] Test backward compatibility if endpoint had limit/offset
- [ ] Update API documentation with new response structure

## Support for Different Item Types

`PaginatedResponse` is generic and works with any data type:

```python
# List of dicts
return paginate([{"id": 1, "name": "Item 1"}], 100, 1, 20)

# List of Pydantic models
return paginate([ItemModel(id=1, name="Item 1")], 100, 1, 20)

# List of database rows (asyncpg.Record)
return paginate(db_rows, 100, 1, 20)

# Mixed types (as long as they're serializable)
return paginate(items, 100, 1, 20)
```

## Troubleshooting

### "PaginationParams not found"
```python
# Correct import
from api.pagination import PaginationParams
```

### "paginate() requires exactly 4 arguments"
```python
# Correct usage - all 4 args required
paginate(items, total_count, page_number, page_size)

# Wrong - missing arguments
paginate(items, total_count)
```

### Page size always 100 regardless of query param
```python
# Check if MAX_PAGE_SIZE env var is set
# It limits the maximum, doesn't set the default

# Default is 20 per parameter definition
# Users can request 1-100, middleware enforces max
```

### Cursor pagination "has_next" always False
```python
# You need to fetch page_size + 1 items to detect next page
items = await db.fetch(query, page_size + 1)
# CursorPagination.create_response() checks if len(items) > page_size
```
