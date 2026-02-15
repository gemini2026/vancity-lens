"""K2 migration unit tests.

These tests validate the K2 wrapper and retrieval backend selection/fallback
logic without requiring network access.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


def _set_required_k2_env(monkeypatch, *, key: str = "test-key", corpus_id: str = "test-corpus"):
    monkeypatch.setenv("K2_API_KEY", key)
    monkeypatch.setenv("K2_CORPUS_ID", corpus_id)


class TestK2Config:
    def test_load_k2_config_defaults_and_parses_numbers(self, monkeypatch):
        from api.intelligence.k2_client import load_k2_config

        _set_required_k2_env(monkeypatch)
        monkeypatch.delenv("K2_API_HOST", raising=False)
        monkeypatch.setenv("K2_TOP_K", "7")
        monkeypatch.setenv("K2_TIMEOUT_SECONDS", "12.5")

        cfg = load_k2_config()
        assert cfg.api_host == "https://api-dev.knowledge2.ai"
        assert cfg.api_key == "test-key"
        assert cfg.corpus_id == "test-corpus"
        assert cfg.top_k == 7
        assert cfg.timeout_seconds == 12.5

    def test_load_k2_config_requires_key_and_corpus(self, monkeypatch):
        from api.intelligence.k2_client import load_k2_config

        monkeypatch.delenv("K2_API_KEY", raising=False)
        monkeypatch.delenv("K2_CORPUS_ID", raising=False)

        with pytest.raises(RuntimeError, match="K2_API_KEY is not set"):
            load_k2_config()

        monkeypatch.setenv("K2_API_KEY", "test-key")
        with pytest.raises(RuntimeError, match="K2_CORPUS_ID is not set"):
            load_k2_config()


class TestK2SearchNormalization:
    def test_k2_search_chunks_normalizes_results(self, monkeypatch):
        from api.intelligence.k2_client import k2_search_chunks

        _set_required_k2_env(monkeypatch)

        class StubClient:
            def search(self, *, corpus_id, query, top_k, return_config):
                assert corpus_id == "test-corpus"
                assert query == "hello"
                assert top_k == 3
                assert return_config["include_text"] is True
                assert return_config["include_scores"] is True
                assert return_config["include_provenance"] is True
                return {
                    "results": [
                        {
                            "chunk_id": "k2-chunk-1",
                            "text": "  Some chunk text  ",
                            "score": 0.42,
                            "metadata": {
                                "title": "Doc Title",
                                "source_url": "https://example.com/doc",
                                "source_type": "pdf",
                                "published_date": "2024-01-02T12:00:00Z",
                                "archive_url": "https://archive.example.com/doc",
                                "url_status": "ok",
                                "section_header": "Section A",
                                "chunk_index": 5,
                            },
                        }
                    ]
                }

        with patch("api.intelligence.k2_client.get_k2_client", return_value=StubClient()):
            chunks = k2_search_chunks("hello", top_k=3)

        assert len(chunks) == 1
        c0 = chunks[0]
        assert c0["chunk_id"] is None
        assert c0["document_id"] is None
        assert c0["k2_chunk_id"] == "k2-chunk-1"
        assert c0["chunk_text"] == "Some chunk text"
        assert c0["final_score"] == pytest.approx(0.42)
        assert c0["rrf_score"] == pytest.approx(0.42)
        assert c0["document_title"] == "Doc Title"
        assert c0["source_url"] == "https://example.com/doc"
        assert c0["source_type"] == "pdf"
        assert c0["published_date"] == date(2024, 1, 2)
        assert c0["archive_url"] == "https://archive.example.com/doc"
        assert c0["url_status"] == "ok"
        assert c0["section_header"] == "Section A"
        assert c0["chunk_index"] == 5

    def test_k2_search_chunks_resolves_corpus_name_on_not_found(self, monkeypatch):
        from api.intelligence.k2_client import k2_search_chunks
        from sdk.errors import Knowledge2Error

        _set_required_k2_env(monkeypatch, corpus_id="vancity")

        # Ensure test isolation in case other tests populated the cache.
        from api.intelligence import k2_client as k2_mod
        k2_mod._CORPUS_ID_CACHE.clear()

        class StubClient:
            def __init__(self):
                self.search_calls = []
                self.list_calls = 0

            def search(self, *, corpus_id, query, top_k, return_config):
                self.search_calls.append(corpus_id)
                if corpus_id == "vancity":
                    raise Knowledge2Error("Corpus not found", status_code=404, request_id="req-1")
                assert corpus_id == "resolved-id"
                return {
                    "results": [
                        {
                            "chunk_id": "k2-chunk-1",
                            "text": "Resolved corpus result",
                            "score": 0.9,
                            "metadata": {"title": "Resolved Doc"},
                        }
                    ]
                }

            def list_corpora(self, limit: int = 100, offset: int = 0):
                self.list_calls += 1
                assert limit == 100
                assert offset == 0
                return {"corpora": [{"id": "resolved-id", "name": "vancity", "project_id": "p1"}]}

        stub = StubClient()
        with patch("api.intelligence.k2_client.get_k2_client", return_value=stub):
            chunks = k2_search_chunks("hello", top_k=1)

        assert stub.search_calls == ["vancity", "resolved-id"]
        assert stub.list_calls == 1
        assert len(chunks) == 1
        assert chunks[0]["document_title"] == "Resolved Doc"


class TestK2DefaultBackend:
    """K2 should be the default backend when RAG_BACKEND is not set."""

    def test_default_backend_is_k2(self, monkeypatch):
        monkeypatch.delenv("RAG_BACKEND", raising=False)
        from api.intelligence.retrieval_backend import get_rag_backend
        assert get_rag_backend() == "k2"

    def test_explicit_local_still_works(self, monkeypatch):
        monkeypatch.setenv("RAG_BACKEND", "local")
        from api.intelligence.retrieval_backend import get_rag_backend
        assert get_rag_backend() == "local"


class TestRetrievalBackend:
    @pytest.mark.asyncio
    async def test_retrieve_document_chunks_uses_k2_when_enabled(self, monkeypatch):
        from api.intelligence.retrieval_backend import retrieve_document_chunks

        monkeypatch.setenv("RAG_BACKEND", "k2")
        _set_required_k2_env(monkeypatch)

        expected = [{"chunk_text": "x"}]
        with patch("api.intelligence.retrieval_backend.asyncio.to_thread", new=AsyncMock(return_value=expected)) as mock_tt:
            result = await retrieve_document_chunks(
                db_pool=AsyncMock(),
                query="q",
                search_mode="demo",
            )
        assert result == expected
        assert mock_tt.await_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_document_chunks_falls_back_to_bm25_on_k2_error(self, monkeypatch):
        from api.intelligence.retrieval_backend import retrieve_document_chunks

        monkeypatch.setenv("RAG_BACKEND", "k2")
        monkeypatch.setenv("K2_FALLBACK_TO_LOCAL", "true")
        _set_required_k2_env(monkeypatch)

        fallback_chunks = [{"chunk_text": "fallback"}]

        with patch(
            "api.intelligence.retrieval_backend.asyncio.to_thread",
            new=AsyncMock(side_effect=Exception("boom")),
        ):
            with patch(
                "api.intelligence.local_rag.embeddings.sparse_search",
                new=AsyncMock(return_value=fallback_chunks),
            ) as mock_sparse:
                result = await retrieve_document_chunks(
                    db_pool=AsyncMock(),
                    query="q",
                    search_mode="demo",
                )

        assert result == fallback_chunks
        assert mock_sparse.await_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_document_chunks_raises_when_fallback_disabled(self, monkeypatch):
        from api.intelligence.retrieval_backend import retrieve_document_chunks

        monkeypatch.setenv("RAG_BACKEND", "k2")
        monkeypatch.setenv("K2_FALLBACK_TO_LOCAL", "false")
        _set_required_k2_env(monkeypatch)

        with patch(
            "api.intelligence.retrieval_backend.asyncio.to_thread",
            new=AsyncMock(side_effect=Exception("boom")),
        ):
            with pytest.raises(Exception, match="boom"):
                await retrieve_document_chunks(
                    db_pool=AsyncMock(),
                    query="q",
                    search_mode="demo",
                )
