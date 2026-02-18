from __future__ import annotations

from typing import List, Literal, Optional, TypedDict


class ChunkingConfig(TypedDict, total=False):
    """Chunking configuration for document ingestion.

    All fields are optional - unset fields inherit from corpus defaults or env defaults.
    """

    # Top-level chunking strategy
    strategy: Literal["fixed", "paragraph", "semantic", "semchunk", "unstructured"]
    # Unstructured sub-strategy (only used when strategy="unstructured")
    chunking_strategy: Literal["basic", "by_title", "by_page", "by_similarity"]
    # Max characters per chunk
    chunk_size: int
    # Overlap between chunks (characters)
    overlap: int
    # Combine small sections under N chars (by_title specific)
    combine_text_under_n_chars: int
    # Allow sections to span pages
    multipage_sections: bool
    # Soft limit before hard max (new_after_n_chars)
    new_after_n_chars: int
    # Concurrent Unstructured API requests
    max_concurrent_requests: int
    # API timeout in milliseconds
    timeout: int


class DocumentCreateResponse(TypedDict):
    doc_id: str
    job_id: str


class DocumentBatchItem(TypedDict, total=False):
    source_uri: str | None
    raw_text: str
    metadata: dict | None


class DocumentUrlItem(TypedDict, total=False):
    url: str
    title: str | None
    tags: list[str] | None
    metadata: dict | None


class DocumentUrlIngestResponse(TypedDict):
    job_id: str
    submitted: int


class DocumentManifestIngestResponse(TypedDict):
    job_id: str


class DocumentListItem(TypedDict, total=False):
    id: str
    corpus_id: str
    source_uri: str
    custom_metadata: dict
    system_metadata: dict
    created_at: str | None
    status: str | None
    size_bytes: int | None
    content_type: str | None
    preview: str | None


class DocumentListResponse(TypedDict):
    documents: list[DocumentListItem]


class DocumentDetailResponse(DocumentListItem):
    pass


class DocumentDeleteResponse(TypedDict, total=False):
    message: str
    reindex_job_id: str | None


class DocumentBatchUploadResponse(TypedDict):
    """Response for multipart batch file upload."""

    job_id: str
    doc_ids: list[str]
    count: int
