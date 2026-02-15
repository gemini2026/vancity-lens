"""
Tests for RAG & Hybrid Search Hardening (RAG-001 through RAG-009).

Covers:
- RAG-001: Document viewer endpoint
- RAG-002: URL health checker
- RAG-003: Wayback Machine fallback
- RAG-005: Citation provenance chain
- RAG-006: Ingestion metadata extraction
- RAG-007: Search config endpoint
- RAG-008: Metadata-filtered hybrid search signature
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date, timezone

# ── RAG-002 + RAG-003: URL Health Checker Tests ──────────────────


class TestUrlHealth:
    """Tests for api.intelligence.url_health module."""

    def test_build_archive_url(self):
        from api.intelligence.url_health import build_archive_url

        url = "https://vancouver.ca/council/minutes.pdf"
        archive = build_archive_url(url)
        assert archive == "https://web.archive.org/web/https://vancouver.ca/council/minutes.pdf"

    def test_build_archive_url_with_query_params(self):
        from api.intelligence.url_health import build_archive_url

        url = "https://example.com/page?id=42&lang=en"
        archive = build_archive_url(url)
        assert archive.startswith("https://web.archive.org/web/")
        assert "id=42" in archive
        assert "lang=en" in archive

    @pytest.mark.asyncio
    async def test_check_single_url_alive(self):
        from api.intelligence.url_health import check_single_url, ALIVE

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_resp)

        status, redirect_url = await check_single_url(mock_session, "https://example.com")
        assert status == ALIVE
        assert redirect_url is None

    @pytest.mark.asyncio
    async def test_check_single_url_dead_404(self):
        from api.intelligence.url_health import check_single_url, DEAD

        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.headers = {}
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_resp)

        status, redirect_url = await check_single_url(mock_session, "https://example.com/dead")
        assert status == DEAD
        assert redirect_url is None

    @pytest.mark.asyncio
    async def test_check_single_url_redirect(self):
        from api.intelligence.url_health import check_single_url, REDIRECT

        mock_resp = AsyncMock()
        mock_resp.status = 301
        mock_resp.headers = {"Location": "https://new.example.com"}
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.head = MagicMock(return_value=mock_resp)

        status, redirect_url = await check_single_url(mock_session, "https://old.example.com")
        assert status == REDIRECT
        assert redirect_url == "https://new.example.com"

    @pytest.mark.asyncio
    async def test_check_single_url_timeout(self):
        import asyncio
        from api.intelligence.url_health import check_single_url, TIMEOUT

        mock_session = AsyncMock()
        mock_session.head = MagicMock(side_effect=asyncio.TimeoutError())

        status, redirect_url = await check_single_url(mock_session, "https://slow.example.com")
        assert status == TIMEOUT
        assert redirect_url is None

    @pytest.mark.asyncio
    async def test_check_single_url_connection_error(self):
        import aiohttp
        from api.intelligence.url_health import check_single_url, DEAD

        mock_session = AsyncMock()
        mock_session.head = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))

        status, redirect_url = await check_single_url(mock_session, "https://unreachable.example.com")
        assert status == DEAD
        assert redirect_url is None


# ── RAG-005: Citation Provenance Chain Tests ──────────────────────


class TestCitationProvenance:
    """Tests for provenance fields in SourceCitation model."""

    def test_source_citation_provenance_fields(self):
        from api.intelligence.models import SourceCitation

        citation = SourceCitation(
            document_title="Council Minutes",
            document_url="https://example.com/doc.pdf",
            source_type="council_minutes",
            published_date=date(2026, 1, 15),
            relevance_score=0.95,
            excerpt="The council voted 7-2 to approve...",
            document_id=42,
            chunk_id=123,
            url_status="dead",
            archive_url="https://web.archive.org/web/https://example.com/doc.pdf",
        )

        assert citation.document_id == 42
        assert citation.chunk_id == 123
        assert citation.url_status == "dead"
        assert citation.archive_url.startswith("https://web.archive.org/")

    def test_source_citation_provenance_defaults_none(self):
        from api.intelligence.models import SourceCitation

        citation = SourceCitation(
            document_title="Test",
            document_url="https://example.com",
            source_type="news_article",
            relevance_score=0.5,
            excerpt="test excerpt",
        )

        assert citation.document_id is None
        assert citation.chunk_id is None
        assert citation.url_status is None
        assert citation.archive_url is None


# ── RAG-001: Document Viewer Model Tests ──────────────────────────


class TestDocumentViewerModel:
    """Tests for DocumentViewResponse model."""

    def test_document_view_response_fields(self):
        from api.intelligence.models import DocumentViewResponse

        doc = DocumentViewResponse(
            id=1,
            title="Council Minutes Jan 2026",
            source_url="https://vancouver.ca/minutes.pdf",
            source_type="council_minutes",
            published_date=date(2026, 1, 15),
            raw_text="The council met on January 15...",
            text_length=31,
            page_count=5,
            url_status="dead",
            archive_url="https://web.archive.org/web/https://vancouver.ca/minutes.pdf",
        )

        assert doc.id == 1
        assert doc.title == "Council Minutes Jan 2026"
        assert doc.url_status == "dead"
        assert doc.archive_url is not None
        assert doc.raw_text.startswith("The council")

    def test_document_view_response_optional_fields(self):
        from api.intelligence.models import DocumentViewResponse

        doc = DocumentViewResponse(
            id=2,
            source_url="https://example.com/doc",
            source_type="external",
            raw_text="content",
        )

        assert doc.title is None
        assert doc.published_date is None
        assert doc.url_status is None
        assert doc.archive_url is None


# ── RAG-006: Ingestion Metadata Extraction Tests ─────────────────


class TestIngestionMetadata:
    """Tests for _extract_html_metadata in scraper_url.py."""

    def test_extract_og_title(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<html><head><meta property="og:title" content="City Council Minutes"></head></html>'
        meta = _extract_html_metadata(html)
        assert meta["og_title"] == "City Council Minutes"

    def test_extract_og_description(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<meta property="og:description" content="Minutes from the Jan 15 meeting">'
        meta = _extract_html_metadata(html)
        assert meta["og_description"] == "Minutes from the Jan 15 meeting"

    def test_extract_og_site_name(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<meta property="og:site_name" content="City of Vancouver">'
        meta = _extract_html_metadata(html)
        assert meta["og_site_name"] == "City of Vancouver"

    def test_extract_article_published_time(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<meta property="article:published_time" content="2026-01-15T10:00:00Z">'
        meta = _extract_html_metadata(html)
        assert meta["article_published_time"] == "2026-01-15T10:00:00Z"

    def test_extract_meta_description(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<meta name="description" content="Official council minutes">'
        meta = _extract_html_metadata(html)
        assert meta["meta_description"] == "Official council minutes"

    def test_extract_meta_author(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = '<meta name="author" content="City Clerk">'
        meta = _extract_html_metadata(html)
        assert meta["meta_author"] == "City Clerk"

    def test_extract_no_metadata(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = "<html><head><title>Hello</title></head><body>content</body></html>"
        meta = _extract_html_metadata(html)
        assert meta == {}

    def test_extract_multiple_tags(self):
        from api.intelligence.scraper_url import _extract_html_metadata

        html = """
        <html><head>
            <meta property="og:title" content="Rezoning Report">
            <meta property="og:site_name" content="Vancouver.ca">
            <meta name="author" content="Planning Dept">
        </head></html>
        """
        meta = _extract_html_metadata(html)
        assert meta["og_title"] == "Rezoning Report"
        assert meta["og_site_name"] == "Vancouver.ca"
        assert meta["meta_author"] == "Planning Dept"


# ── RAG-007: Search Config Model Tests ───────────────────────────


class TestSearchConfigModels:
    """Tests for SearchConfigRequest/Response models."""

    def test_search_config_request_defaults(self):
        from api.intelligence.models import SearchConfigRequest

        req = SearchConfigRequest()
        assert req.vector_weight is None
        assert req.text_weight is None
        assert req.rrf_k is None
        assert req.rerank_enabled is None

    def test_search_config_request_partial_update(self):
        from api.intelligence.models import SearchConfigRequest

        req = SearchConfigRequest(vector_weight=0.7, rerank_enabled=False)
        assert req.vector_weight == 0.7
        assert req.text_weight is None
        assert req.rerank_enabled is False

    def test_search_config_request_validation(self):
        from api.intelligence.models import SearchConfigRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SearchConfigRequest(vector_weight=1.5)  # exceeds max 1.0

        with pytest.raises(ValidationError):
            SearchConfigRequest(vector_weight=-0.1)  # below min 0.0

        with pytest.raises(ValidationError):
            SearchConfigRequest(rrf_k=0)  # below min 1

    def test_search_config_response(self):
        from api.intelligence.models import SearchConfigResponse

        resp = SearchConfigResponse(
            vector_weight=0.6,
            text_weight=0.4,
            rrf_k=60,
            rerank_enabled=True,
            updated_at=datetime(2026, 2, 9, 12, 0, 0),
        )
        assert resp.vector_weight == 0.6
        assert resp.text_weight == 0.4
        assert resp.rrf_k == 60
        assert resp.rerank_enabled is True


# ── RAG-008: Hybrid Search Signature Tests ───────────────────────


class TestHybridSearchSignature:
    """Tests that hybrid_search accepts metadata filter params (RAG-008)."""

    def test_hybrid_search_accepts_filter_params(self):
        """Verify the function signature includes metadata filter parameters."""
        import inspect
        from api.intelligence.local_rag.embeddings import hybrid_search

        sig = inspect.signature(hybrid_search)
        params = list(sig.parameters.keys())

        assert "neighborhood" in params, "hybrid_search should accept neighborhood param"
        assert "date_from" in params, "hybrid_search should accept date_from param"
        assert "date_to" in params, "hybrid_search should accept date_to param"
        assert "signal_type" in params, "hybrid_search should accept signal_type param"

    def test_hybrid_search_filter_defaults_are_none(self):
        import inspect
        from api.intelligence.local_rag.embeddings import hybrid_search

        sig = inspect.signature(hybrid_search)

        assert sig.parameters["neighborhood"].default is None
        assert sig.parameters["date_from"].default is None
        assert sig.parameters["date_to"].default is None
        assert sig.parameters["signal_type"].default is None


# ── RAG-009: Embedding Model Versioning Tests ─────────────────────


class TestEmbeddingModelVersioning:
    """Tests for embedding_model column support."""

    def test_migration_adds_embedding_model_column(self):
        """Verify the migration SQL includes the embedding_model column."""
        with open("db/026_rag_hardening.sql") as f:
            sql = f.read()

        assert "embedding_model" in sql
        assert "DEFAULT 'cohere-v3'" in sql


# ── Integration: Route Import Tests ──────────────────────────────


class TestRouteImports:
    """Verify all new models and endpoints import cleanly."""

    def test_models_import(self):
        from api.intelligence.models import (
            DocumentViewResponse,
            SearchConfigRequest,
            SearchConfigResponse,
            SourceCitation,
        )

        assert DocumentViewResponse is not None
        assert SearchConfigRequest is not None
        assert SearchConfigResponse is not None

    def test_url_health_import(self):
        from api.intelligence.url_health import (
            check_single_url,
            check_document_urls,
            get_document_url_status,
            build_archive_url,
            ALIVE,
            DEAD,
            REDIRECT,
            TIMEOUT,
            UNCHECKED,
        )

        assert ALIVE == "alive"
        assert DEAD == "dead"
        assert UNCHECKED == "unchecked"

    def test_routes_import(self):
        """Verify routes.py imports cleanly with new endpoints."""
        from api.intelligence.routes import router
        assert router is not None

        # Check new routes are registered
        route_paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/documents/{document_id}/view" in route_paths or any(
            "/documents/" in p for p in route_paths
        )


# ── Migration File Tests ─────────────────────────────────────────


# ── RAG-010: Multi-hop Retrieval Tests ────────────────────────────


class TestQueryPlanner:
    """Tests for api.intelligence.local_rag.query_planner module."""

    def test_is_multi_hop_compare(self):
        from api.intelligence.local_rag.query_planner import is_multi_hop

        assert is_multi_hop("Compare the rezoning at 123 Main to the one at 456 Oak")
        assert is_multi_hop("What is the difference between Broadway Plan and Cambie?")
        assert is_multi_hop("density changes in Kitsilano vs Mount Pleasant")
        assert is_multi_hop("How does downtown compare to Yaletown?")
        assert is_multi_hop("Contrast the permit activity in Marpole and Kerrisdale")

    def test_is_multi_hop_single(self):
        from api.intelligence.local_rag.query_planner import is_multi_hop

        assert not is_multi_hop("What is the latest rezoning decision at 123 Main?")
        assert not is_multi_hop("Tell me about the Broadway Plan")
        assert not is_multi_hop("How many permits in Kitsilano?")

    def test_decompose_compare_to(self):
        from api.intelligence.local_rag.query_planner import decompose_query

        result = decompose_query("Compare the rezoning at 123 Main to the one at 456 Oak")
        assert len(result) == 2
        assert "123 main" in result[0].lower() or "123 main" in result[1].lower()

    def test_decompose_difference_between(self):
        from api.intelligence.local_rag.query_planner import decompose_query

        result = decompose_query("difference between Broadway Plan and Cambie Corridor Plan")
        assert len(result) == 2

    def test_decompose_vs(self):
        from api.intelligence.local_rag.query_planner import decompose_query

        result = decompose_query("Kitsilano vs Mount Pleasant density changes")
        assert len(result) == 2

    def test_decompose_single_query(self):
        from api.intelligence.local_rag.query_planner import decompose_query

        result = decompose_query("What is the latest rezoning decision?")
        assert len(result) == 1
        assert result[0] == "What is the latest rezoning decision?"

    @pytest.mark.asyncio
    async def test_multi_hop_search_single_query(self):
        """When query is not multi-hop, multi_hop_search delegates to search_fn directly."""
        from api.intelligence.local_rag.query_planner import multi_hop_search

        mock_search = AsyncMock(return_value=[{"chunk_id": 1, "final_score": 0.9}])
        mock_pool = MagicMock()

        results = await multi_hop_search(
            mock_pool, "simple query", "api-key", search_fn=mock_search, final_limit=10
        )

        assert len(results) == 1
        assert results[0]["chunk_id"] == 1
        mock_search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multi_hop_search_deduplicates(self):
        """Multi-hop search should deduplicate chunks by chunk_id."""
        from api.intelligence.local_rag.query_planner import multi_hop_search

        # Same chunk_id returned by both sub-queries
        async def mock_search(pool, query, key, **kwargs):
            return [
                {"chunk_id": 1, "final_score": 0.9, "chunk_text": "shared"},
                {"chunk_id": 2 if "main" in query.lower() else 3, "final_score": 0.7, "chunk_text": "unique"},
            ]

        mock_pool = MagicMock()
        results = await multi_hop_search(
            mock_pool, "compare 123 main to 456 oak", "api-key",
            search_fn=mock_search, limit_per_hop=5, final_limit=10,
        )

        chunk_ids = [r["chunk_id"] for r in results]
        assert len(chunk_ids) == len(set(chunk_ids)), "Should have no duplicate chunk_ids"


# ── RAG-011: Document Processing Status Tests ─────────────────────


class TestDocumentStatusModel:
    """Tests for DocumentStatusResponse model."""

    def test_document_status_response_fields(self):
        from api.intelligence.models import DocumentStatusResponse

        status = DocumentStatusResponse(
            document_id=42,
            title="Test Document",
            status="completed",
            has_raw_text=True,
            chunk_count=15,
            signal_count=3,
        )
        assert status.document_id == 42
        assert status.status == "completed"
        assert status.chunk_count == 15
        assert status.signal_count == 3

    def test_document_status_response_defaults(self):
        from api.intelligence.models import DocumentStatusResponse

        status = DocumentStatusResponse(document_id=1, status="pending")
        assert status.title is None
        assert status.has_raw_text is False
        assert status.chunk_count == 0
        assert status.signal_count == 0
        assert status.scraped_at is None
        assert status.processed_at is None

    def test_document_status_import(self):
        from api.intelligence.models import DocumentStatusResponse
        assert DocumentStatusResponse is not None


# ── RAG-012: Scheduler Tests ──────────────────────────────────────


class TestScheduler:
    """Tests for api.intelligence.scheduler module."""

    def test_cron_schedule_daily(self):
        from api.intelligence.scheduler import CronSchedule

        cron = CronSchedule("0 6 * * *")  # daily 6am
        from datetime import datetime
        dt_match = datetime(2026, 2, 9, 6, 0)
        dt_no_match = datetime(2026, 2, 9, 7, 0)
        assert cron.should_run(dt_match) is True
        assert cron.should_run(dt_no_match) is False

    def test_cron_schedule_every_6_hours(self):
        from api.intelligence.scheduler import CronSchedule

        cron = CronSchedule("0 */6 * * *")
        from datetime import datetime
        assert cron.should_run(datetime(2026, 2, 9, 0, 0)) is True
        assert cron.should_run(datetime(2026, 2, 9, 6, 0)) is True
        assert cron.should_run(datetime(2026, 2, 9, 12, 0)) is True
        assert cron.should_run(datetime(2026, 2, 9, 3, 0)) is False

    def test_cron_schedule_invalid(self):
        from api.intelligence.scheduler import CronSchedule

        with pytest.raises(ValueError):
            CronSchedule("bad cron")

        with pytest.raises(ValueError):
            CronSchedule("0 25 * * *")  # hour out of range

    def test_scraper_schedule_creation(self):
        from api.intelligence.scheduler import ScraperSchedule

        schedule = ScraperSchedule(
            scraper_name="test",
            cron_expression="0 6 * * *",
            enabled=True,
        )
        assert schedule.scraper_name == "test"
        assert schedule.enabled is True
        assert schedule.max_retries == 3

    def test_scraper_result_duration(self):
        from api.intelligence.scheduler import ScraperResult, ScraperStatus
        from datetime import datetime

        result = ScraperResult(
            scraper_name="test",
            started_at=datetime(2026, 2, 9, 6, 0, 0),
            completed_at=datetime(2026, 2, 9, 6, 2, 30),
            documents_found=10,
            documents_new=5,
            documents_skipped=5,
            status=ScraperStatus.SUCCESS,
        )
        assert result.duration_seconds == 150.0

    def test_scraper_result_to_dict(self):
        from api.intelligence.scheduler import ScraperResult, ScraperStatus
        from datetime import datetime

        result = ScraperResult(
            scraper_name="council",
            started_at=datetime(2026, 2, 9, 6, 0),
            completed_at=datetime(2026, 2, 9, 6, 1),
            documents_found=5,
            documents_new=3,
            documents_skipped=2,
            status=ScraperStatus.SUCCESS,
        )
        d = result.to_dict()
        assert d["scraper_name"] == "council"
        assert d["status"] == "success"
        assert d["documents_new"] == 3

    def test_scheduler_get_status(self):
        from api.intelligence.scheduler import ScraperScheduler

        mock_pool = MagicMock()
        scheduler = ScraperScheduler(mock_pool)
        status = scheduler.get_status()

        assert "scrapers" in status
        assert "council" in status["scrapers"]
        assert "news" in status["scrapers"]
        assert status["scrapers"]["council"]["cron"] == "0 6 * * *"
        assert status["scrapers"]["news"]["cron"] == "0 */6 * * *"

    def test_scheduler_register_scraper(self):
        from api.intelligence.scheduler import ScraperScheduler

        mock_pool = MagicMock()
        scheduler = ScraperScheduler(mock_pool)

        async def dummy_scraper(pool, start, end):
            return {"documents_found": 0, "documents_new": 0, "documents_skipped": 0}

        scheduler.register_scraper("custom", dummy_scraper, "30 12 * * *")

        assert "custom" in scheduler.scrapers
        status = scheduler.get_status()
        assert status["scrapers"]["custom"]["cron"] == "30 12 * * *"
        assert status["scrapers"]["custom"]["has_function"] is True


class TestMigrationFile:
    """Verify the DB migration file is well-formed."""

    def test_migration_file_exists(self):
        import os
        assert os.path.exists("db/026_rag_hardening.sql")

    def test_migration_has_all_columns(self):
        with open("db/026_rag_hardening.sql") as f:
            sql = f.read()

        # RAG-002: URL health columns
        assert "url_status" in sql
        assert "url_checked_at" in sql

        # RAG-003: Archive URL
        assert "archive_url" in sql

        # RAG-004: Chunk metadata
        assert "document_chunks" in sql
        assert "metadata JSONB" in sql

        # RAG-007: Search config table
        assert "search_config" in sql
        assert "vector_weight" in sql
        assert "text_weight" in sql
        assert "rrf_k" in sql
        assert "rerank_enabled" in sql

        # RAG-009: Embedding model
        assert "embedding_model" in sql
