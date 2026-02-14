from __future__ import annotations

from typing import List, Optional, TypedDict


class ChunkListItem(TypedDict, total=False):
    id: str
    text: str
    metadata: dict
    offset_start: int | None
    offset_end: int | None
    page_start: int | None
    page_end: int | None


class ChunkListResponse(TypedDict):
    chunks: list[ChunkListItem]
