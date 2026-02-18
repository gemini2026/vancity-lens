from __future__ import annotations

import json
import os
from typing import Any, Iterator, cast

from sdk.resources._mixin_base import RequesterMixin
from sdk.types import (
    ChunkingConfig,
    ChunkListResponse,
    DocumentBatchUploadResponse,
    DocumentCreateResponse,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentManifestIngestResponse,
    DocumentUrlIngestResponse,
)


class DocumentsMixin(RequesterMixin):
    def upload_document(
        self,
        corpus_id: str,
        *,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
        raw_text: str | None = None,
        source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        auto_index: bool | None = None,
        chunk_strategy: str | None = None,
        chunking: ChunkingConfig | None = None,
        idempotency_key: str | None = None,
    ) -> DocumentCreateResponse:
        """Upload a document to a corpus.

        Args:
            corpus_id: Target corpus ID.
            file_path: Path to file to upload.
            file_bytes: Raw file bytes to upload.
            filename: Filename when using file_bytes.
            raw_text: Raw text content to upload.
            source_uri: Optional source URI for the document.
            metadata: Optional document metadata.
            auto_index: Whether to auto-index after ingestion.
            chunk_strategy: Deprecated - use chunking instead.
            chunking: Chunking configuration (strategy, chunk_size, overlap, etc.)
            idempotency_key: Optional key for idempotent requests.
        """
        if file_path and (file_bytes or raw_text):
            raise ValueError("file_path cannot be combined with file_bytes or raw_text")
        if file_bytes and raw_text:
            raise ValueError("file_bytes cannot be combined with raw_text")
        headers = self._idempotency_headers(idempotency_key)
        if file_path:
            form: dict[str, str] = {}
            if source_uri is not None:
                form["source_uri"] = source_uri
            if metadata is not None:
                form["metadata"] = json.dumps(metadata)
            if auto_index is not None:
                form["auto_index"] = str(bool(auto_index)).lower()
            if chunking is not None:
                form["chunking"] = json.dumps(chunking)
            elif chunk_strategy is not None:
                form["chunk_strategy"] = chunk_strategy
            with open(file_path, "rb") as handle:
                files = {"file": (os.path.basename(file_path), handle)}
                data = self._request(
                    "POST",
                    f"/v1/corpora/{corpus_id}/documents",
                    data=form,
                    files=files,
                    headers=headers,
                )
            return cast("DocumentCreateResponse", data)
        if file_bytes is not None:
            if not filename:
                raise ValueError("filename is required when using file_bytes")
            form_data: dict[str, str] = {}
            if source_uri is not None:
                form_data["source_uri"] = source_uri
            if metadata is not None:
                form_data["metadata"] = json.dumps(metadata)
            if auto_index is not None:
                form_data["auto_index"] = str(bool(auto_index)).lower()
            if chunking is not None:
                form_data["chunking"] = json.dumps(chunking)
            elif chunk_strategy is not None:
                form_data["chunk_strategy"] = chunk_strategy
            file_payload: dict[str, Any] = {"file": (filename, file_bytes)}
            data = self._request(
                "POST",
                f"/v1/corpora/{corpus_id}/documents",
                data=form_data,
                files=file_payload,
                headers=headers,
            )
            return cast("DocumentCreateResponse", data)
        if raw_text is None:
            raise ValueError("raw_text is required when no file is provided")
        payload: dict[str, Any] = {}
        if raw_text is not None:
            payload["raw_text"] = raw_text
        if source_uri is not None:
            payload["source_uri"] = source_uri
        if metadata is not None:
            payload["metadata"] = metadata
        if auto_index is not None:
            payload["auto_index"] = auto_index
        if chunking is not None:
            payload["chunking"] = chunking
        elif chunk_strategy is not None:
            payload["chunk_strategy"] = chunk_strategy
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents",
            json=payload,
            headers=headers,
        )
        return cast("DocumentCreateResponse", data)

    def upload_documents_batch(
        self,
        corpus_id: str,
        documents: list[dict[str, Any]],
        idempotency_key: str | None = None,
        *,
        auto_index: bool | None = None,
        chunk_strategy: str | None = None,
        chunking: ChunkingConfig | None = None,
        wait: bool = True,
        poll_s: int = 5,
    ) -> DocumentCreateResponse:
        """Upload multiple documents as raw text in a batch.

        Args:
            corpus_id: Target corpus ID.
            documents: List of document dicts with raw_text, source_uri, metadata.
            idempotency_key: Optional key for idempotent requests.
            auto_index: Whether to auto-index after ingestion.
            chunk_strategy: Deprecated - use chunking instead.
            chunking: Chunking configuration (strategy, chunk_size, overlap, etc.)
            wait: If True, wait for the batch job to complete.
            poll_s: Polling interval when waiting.
        """
        payload: dict[str, Any] = {"documents": documents}
        if auto_index is not None:
            payload["auto_index"] = auto_index
        if chunking is not None:
            payload["chunking"] = chunking
        elif chunk_strategy is not None:
            payload["chunk_strategy"] = chunk_strategy
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:batch",
            json=payload,
            headers=headers,
        )
        if wait:
            job_id = data.get("job_id")
            if job_id:
                self._wait_for_job(job_id, poll_s=poll_s)
        return cast("DocumentCreateResponse", data)

    def upload_files_batch(
        self,
        corpus_id: str,
        files: list[tuple[str, bytes]],
        idempotency_key: str | None = None,
        *,
        auto_index: bool | None = None,
        chunk_strategy: str | None = None,
        chunking: ChunkingConfig | None = None,
        wait: bool = True,
        poll_s: int = 5,
    ) -> DocumentBatchUploadResponse:
        """Upload multiple files in a single multipart request.

        Creates a single ingest_documents_batch job for all files,
        enabling batch processing with near-data optimization.

        Args:
            corpus_id: Target corpus ID.
            files: List of (filename, content_bytes) tuples.
            idempotency_key: Optional key for idempotent requests.
            auto_index: Whether to auto-index after ingestion.
            chunk_strategy: Deprecated - use chunking instead.
            chunking: Chunking configuration (strategy, chunk_size, overlap, etc.)
            wait: If True, wait for the batch job to complete.
            poll_s: Polling interval when waiting.

        Returns:
            Response with job_id, doc_ids, and count.
        """
        headers = self._idempotency_headers(idempotency_key)

        # Build multipart form data
        files_payload: dict[str, Any] = {}
        for i, (filename, content) in enumerate(files):
            files_payload[f"files"] = files_payload.get("files", [])
            # httpx expects list of tuples for multiple files with same key
        files_list = [("files", (filename, content)) for filename, content in files]

        form_data: dict[str, Any] = {}
        if auto_index is not None:
            form_data["auto_index"] = str(auto_index).lower()
        if chunking is not None:
            form_data["chunking"] = json.dumps(chunking)
        elif chunk_strategy is not None:
            form_data["chunk_strategy"] = chunk_strategy

        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:upload_batch",
            data=form_data if form_data else None,
            files=files_list,
            headers=headers,
        )
        if wait:
            job_id = data.get("job_id")
            if job_id:
                self._wait_for_job(job_id, poll_s=poll_s)
        return cast("DocumentBatchUploadResponse", data)

    def ingest_urls(
        self,
        corpus_id: str,
        urls: list[dict[str, Any]],
        idempotency_key: str | None = None,
        *,
        auto_index: bool | None = None,
        chunk_strategy: str | None = None,
        chunking: ChunkingConfig | None = None,
        wait: bool = True,
        poll_s: int = 5,
    ) -> DocumentUrlIngestResponse:
        """Ingest documents from URLs.

        Args:
            corpus_id: Target corpus ID.
            urls: List of URL dicts with url, title, tags, metadata.
            idempotency_key: Optional key for idempotent requests.
            auto_index: Whether to auto-index after ingestion.
            chunk_strategy: Deprecated - use chunking instead.
            chunking: Chunking configuration (strategy, chunk_size, overlap, etc.)
            wait: If True, wait for the batch job to complete.
            poll_s: Polling interval when waiting.
        """
        payload: dict[str, Any] = {"urls": urls}
        if auto_index is not None:
            payload["auto_index"] = auto_index
        if chunking is not None:
            payload["chunking"] = chunking
        elif chunk_strategy is not None:
            payload["chunk_strategy"] = chunk_strategy
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:ingest_urls",
            json=payload,
            headers=headers,
        )
        if wait:
            job_id = data.get("job_id")
            if job_id:
                self._wait_for_job(job_id, poll_s=poll_s)
        return cast("DocumentUrlIngestResponse", data)

    def ingest_manifest(
        self,
        corpus_id: str,
        manifest_uri: str,
        max_documents: int | None = None,
        idempotency_key: str | None = None,
        *,
        auto_index: bool | None = None,
        chunk_strategy: str | None = None,
        chunking: ChunkingConfig | None = None,
    ) -> DocumentManifestIngestResponse:
        """Ingest documents from a manifest file.

        Args:
            corpus_id: Target corpus ID.
            manifest_uri: URI to manifest file (S3, HTTP, local).
            max_documents: Optional limit on documents to ingest.
            idempotency_key: Optional key for idempotent requests.
            auto_index: Whether to auto-index after ingestion.
            chunk_strategy: Deprecated - use chunking instead.
            chunking: Chunking configuration (strategy, chunk_size, overlap, etc.)
        """
        payload: dict[str, Any] = {"manifest_uri": manifest_uri}
        if max_documents is not None:
            payload["max_documents"] = max_documents
        if auto_index is not None:
            payload["auto_index"] = auto_index
        if chunking is not None:
            payload["chunking"] = chunking
        elif chunk_strategy is not None:
            payload["chunk_strategy"] = chunk_strategy
        headers = self._idempotency_headers(idempotency_key)
        data = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:ingest_manifest",
            json=payload,
            headers=headers,
        )
        return cast("DocumentManifestIngestResponse", data)

    def list_documents(
        self,
        corpus_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
        status: str | None = None,
        source: str | None = None,
        tag: str | None = None,
    ) -> DocumentListResponse:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q is not None:
            params["q"] = q
        if status is not None:
            params["status"] = status
        if source is not None:
            params["source"] = source
        if tag is not None:
            params["tag"] = tag
        data = self._request("GET", f"/v1/corpora/{corpus_id}/documents", params=params)
        return cast("DocumentListResponse", data)

    def iter_documents(
        self,
        corpus_id: str,
        *,
        limit: int = 100,
        q: str | None = None,
        status: str | None = None,
        source: str | None = None,
        tag: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Lazily paginate documents, yielding individual document items."""
        params: dict[str, Any] = {}
        if q is not None:
            params["q"] = q
        if status is not None:
            params["status"] = status
        if source is not None:
            params["source"] = source
        if tag is not None:
            params["tag"] = tag
        yield from self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/documents",
            items_key="documents",
            params=params if params else None,
            limit=limit,
        )

    def get_document(self, doc_id: str) -> DocumentDetailResponse:
        data = self._request("GET", f"/v1/documents/{doc_id}")
        return cast("DocumentDetailResponse", data)

    def update_document_metadata(
        self,
        doc_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Update customer metadata on a document using merge semantics.

        Keys with non-empty values are added or updated.
        Keys with empty string or None values are removed.
        Keys not in the request are left unchanged.

        Args:
            doc_id: Document ID to update
            metadata: Dict of metadata updates to apply

        Returns:
            Updated metadata dict with custom_metadata and system_metadata
        """
        response = self._request(
            "PATCH",
            f"/v1/documents/{doc_id}/metadata",
            json=metadata,
        )
        return response

    def delete_document(
        self, corpus_id: str, doc_id: str, reindex: bool = False
    ) -> DocumentDeleteResponse:
        data = self._request(
            "DELETE",
            f"/v1/corpora/{corpus_id}/documents/{doc_id}",
            params={"reindex": reindex},
        )
        return cast("DocumentDeleteResponse", data)

    def list_chunks(self, corpus_id: str, limit: int = 100, offset: int = 0) -> ChunkListResponse:
        data = self._request(
            "GET",
            f"/v1/corpora/{corpus_id}/chunks",
            params={"limit": limit, "offset": offset},
        )
        return cast("ChunkListResponse", data)

    def iter_chunks(self, corpus_id: str, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Lazily paginate chunks, yielding individual chunk items."""
        yield from self._paginate(
            "GET",
            f"/v1/corpora/{corpus_id}/chunks",
            items_key="chunks",
            limit=limit,
        )
