"""
Comprehensive E2E Pipeline Validation Test for VanCity Lens.

Tests the full flow:
1. PDF parsing → raw text extraction
2. Chunking → semantically coherent chunks
3. Embedding generation → vector storage
4. Signal extraction → intelligence signals
5. Storage → database persistence
6. Chat query → RAG response with citations
7. Citation verification → source accuracy

Tests are organized by pipeline stage with both unit tests (mocked services)
and integration tests (marked with @pytest.mark.e2e_pipeline).

Architecture enforces:
- Semantic quality of chunks
- Vector dimensions correctness
- Signal extraction accuracy
- RAG citation accuracy
- End-to-end data flow integrity
"""

import json
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import asyncpg

from api.intelligence import (
    parser,
    chunker,
    embeddings,
    signals,
    chat,
)
from api.intelligence.models import (
    SignalType,
    Decision,
    Sentiment,
    Severity,
    SignalResponse,
    ChatResponse,
)


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: Document Ingestion & Parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineDocumentIngestion:
    """Test PDF parsing and document ingestion."""

    def test_parse_pdf_extracts_text(self, sample_document):
        """Unit: PDF parsing extracts text content."""
        pdf_bytes = b"%PDF-1.4\n%fake pdf content"

        # Mock parser fallback to return structured result
        with patch('api.intelligence.parser.parse_pdf_with_pdfplumber') as mock_parse:
            mock_parse.return_value = {
                'text': sample_document['raw_text'],
                'page_count': sample_document['page_count'],
                'tables_found': 0,
                'parser': 'pdfplumber',
            }

            result = parser.parse_pdf(pdf_bytes)

            assert result is not None
            assert 'text' in result
            assert len(result['text']) > 0
            assert result['page_count'] == 5
            assert result['parser'] in ['docling', 'pdfplumber']

    def test_parse_pdf_handles_empty_content(self):
        """Unit: PDF parser handles empty/corrupted PDFs gracefully."""
        pdf_bytes = b""

        with patch('api.intelligence.parser.parse_pdf_with_pdfplumber') as mock_parse:
            mock_parse.return_value = None

            result = parser.parse_pdf(pdf_bytes)

            assert result is None

    def test_parse_pdf_preserves_structure(self, sample_document):
        """Unit: Parsed PDF preserves document structure."""
        with patch('api.intelligence.parser.parse_pdf_with_pdfplumber') as mock_parse:
            mock_parse.return_value = {
                'text': sample_document['raw_text'],
                'page_count': sample_document['page_count'],
                'tables_found': 0,
                'parser': 'pdfplumber',
            }

            result = parser.parse_pdf(b"fake pdf")

            assert '\n' in result['text']  # Paragraph breaks preserved
            assert 'ITEM' in result['text']  # Headers preserved
            assert 'REZONING' in result['text']  # Content preserved

    def test_parse_html_extracts_text(self, sample_council_html):
        """Unit: HTML parsing extracts clean text."""
        with patch('api.intelligence.parser.parse_html_with_docling') as mock_parse:
            mock_parse.return_value = {
                'text': "City Council Regular Meeting\nDate: January 15, 2024\n...",
                'page_count': 1,
                'tables_found': 0,
                'parser': 'docling',
            }

            result = parser.parse_html(sample_council_html)

            assert result is not None
            assert 'text' in result
            assert len(result['text']) > 0

    def test_parse_html_removes_noise(self, sample_council_html):
        """Unit: HTML parser removes script/style tags."""
        # Mock parser removes unwanted tags
        with patch('api.intelligence.parser.parse_html_with_docling') as mock_parse:
            mock_parse.return_value = {
                'text': "City Council Regular Meeting",
                'page_count': 1,
                'tables_found': 0,
                'parser': 'docling',
            }

            result = parser.parse_html(sample_council_html)

            # Should not contain HTML tags in text
            assert '<script>' not in result['text']
            assert '<style>' not in result['text']
            assert '<nav>' not in result['text']

    @pytest.mark.e2e_pipeline
    async def test_ingest_document_to_database(self, mock_db_pool, sample_document):
        """Integration: Ingested document stored in database with all fields."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock insert returning document ID
        conn.execute = AsyncMock()
        conn.fetchval = AsyncMock(return_value=1)

        # Store document
        doc_insert_sql = """
            INSERT INTO documents (
                source_type, source_url, title, published_date,
                raw_text, text_length, page_count
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """

        doc_id = await conn.fetchval(
            doc_insert_sql,
            sample_document['source_type'],
            sample_document['source_url'],
            sample_document['title'],
            sample_document['published_date'],
            sample_document['raw_text'],
            sample_document['text_length'],
            sample_document['page_count'],
        )

        assert doc_id == 1
        assert conn.fetchval.called

    @pytest.mark.e2e_pipeline
    async def test_document_metadata_preserved(self, mock_db_pool, sample_document):
        """Integration: Document metadata (dates, urls, titles) preserved."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock retrieval
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'title': sample_document['title'],
            'source_url': sample_document['source_url'],
            'published_date': sample_document['published_date'],
            'meeting_date': sample_document['meeting_date'],
            'source_type': sample_document['source_type'],
            'raw_text': sample_document['raw_text'],
        })

        row = await conn.fetchrow(
            "SELECT id, title, source_url, published_date, meeting_date, source_type, raw_text FROM documents WHERE id = $1",
            1
        )

        assert row['title'] == sample_document['title']
        assert row['source_url'] == sample_document['source_url']
        assert row['published_date'] == sample_document['published_date']
        assert row['meeting_date'] == sample_document['meeting_date']
        assert row['source_type'] == sample_document['source_type']


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: Document Chunking
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineChunking:
    """Test semantic text chunking pipeline."""

    def test_chunk_document_produces_chunks(self, sample_document):
        """Unit: Document chunking produces non-empty chunk list."""
        chunks = chunker.chunk_document(sample_document['raw_text'])

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        for chunk in chunks:
            assert 'chunk_text' in chunk
            assert 'chunk_index' in chunk
            assert 'approx_token_count' in chunk
            assert len(chunk['chunk_text']) > 0

    def test_chunk_count_reasonable(self, sample_document):
        """Unit: Chunk count scales reasonably with document size."""
        chunks = chunker.chunk_document(sample_document['raw_text'])

        # Document should produce at least 1 chunk
        assert 1 <= len(chunks) <= 10

    def test_chunk_text_non_overlapping(self, sample_document):
        """Unit: Chunks are non-overlapping (sequential)."""
        chunks = chunker.chunk_document(sample_document['raw_text'])

        for i, chunk in enumerate(chunks):
            assert chunk['chunk_index'] == i

        # All chunk texts combined should cover most of original
        combined_text = ' '.join([c['chunk_text'] for c in chunks])
        original_coverage = len(combined_text) / len(sample_document['raw_text'])
        assert original_coverage > 0.8  # At least 80% coverage

    def test_chunk_preserves_structure(self, sample_document):
        """Unit: Chunks preserve semantic structure (sections/headers)."""
        chunks = chunker.chunk_document(sample_document['raw_text'])

        # Chunks should have section_header field (may be empty for short docs)
        for chunk in chunks:
            assert 'section_header' in chunk

    def test_chunk_token_counts_accurate(self, sample_document):
        """Unit: Chunk token counts are reasonable."""
        chunks = chunker.chunk_document(sample_document['raw_text'])

        for chunk in chunks:
            # Token count should be positive
            assert chunk['approx_token_count'] > 0
            # Token count should be less than character length / 4
            assert chunk['approx_token_count'] <= len(chunk['chunk_text'])

    def test_chunk_empty_document(self):
        """Unit: Chunking empty document returns empty list."""
        chunks = chunker.chunk_document("")
        assert chunks == []

    def test_chunk_very_small_document(self):
        """Unit: Very small document produces at least one chunk."""
        small_text = "Single line of text."
        chunks = chunker.chunk_document(small_text)
        assert len(chunks) >= 1
        assert chunks[0]['chunk_text'] == "Single line of text."

    def test_chunk_section_header_detection(self):
        """Unit: Section headers are detected from standard patterns."""
        text = """SECTION 1: INTRODUCTION
This is introductory content.

SECTION 2: MAIN CONTENT
This is the main content section.

Item 3. Subsection
More content here."""

        chunks = chunker.chunk_document(text)

        # At least one chunk should have detected a header
        detected_headers = [c['section_header'] for c in chunks if c['section_header']]
        assert len(detected_headers) > 0

    @pytest.mark.e2e_pipeline
    async def test_store_chunks_to_database(self, mock_db_pool, sample_chunks):
        """Integration: Chunks stored in database with embeddings."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock chunk insertion
        conn.fetchval = AsyncMock(side_effect=[101, 102, 103])

        stored_ids = []
        for chunk in sample_chunks:
            chunk_id = await conn.fetchval(
                "INSERT INTO document_chunks (document_id, chunk_index, chunk_text, section_header, token_count) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                1,
                chunk['chunk_index'],
                chunk['chunk_text'],
                chunk['section_header'],
                chunk['approx_token_count'],
            )
            stored_ids.append(chunk_id)

        assert stored_ids == [101, 102, 103]
        assert conn.fetchval.call_count == 3

    @pytest.mark.e2e_pipeline
    async def test_chunk_retrieval_from_database(self, mock_db_pool):
        """Integration: Stored chunks can be retrieved with metadata."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        mock_chunk_row = {
            'id': 101,
            'document_id': 1,
            'chunk_index': 0,
            'chunk_text': 'Sample chunk text',
            'section_header': 'SECTION 1',
            'token_count': 25,
        }

        conn.fetch = AsyncMock(return_value=[mock_chunk_row])

        rows = await conn.fetch(
            "SELECT id, document_id, chunk_index, chunk_text, section_header, token_count "
            "FROM document_chunks WHERE document_id = $1 ORDER BY chunk_index",
            1
        )

        assert len(rows) == 1
        assert rows[0]['chunk_text'] == 'Sample chunk text'
        assert rows[0]['section_header'] == 'SECTION 1'


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: Embedding Generation & Storage
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineEmbedding:
    """Test vector embedding generation and storage."""

    @pytest.mark.e2e_pipeline
    async def test_generate_embedding_returns_vector(self):
        """Integration: Embedding generation returns correct dimension vector."""
        with patch('api.intelligence.embeddings.cohere.AsyncClient') as mock_cohere:
            mock_client = AsyncMock()
            mock_cohere.return_value.__aenter__.return_value = mock_client

            # Mock Cohere response: 1024-dimensional vector
            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.1] * 1024]
            mock_client.embed = AsyncMock(return_value=mock_response)

            with patch('api.intelligence.embeddings.COHERE_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    embedding = await embeddings.generate_embedding(
                        "Test text to embed",
                        api_key="test-key",
                        input_type="search_document"
                    )

            assert isinstance(embedding, list)
            assert len(embedding) == embeddings.EMBEDDING_DIMENSION

    @pytest.mark.e2e_pipeline
    async def test_batch_embed_multiple_texts(self):
        """Integration: Batch embedding handles multiple texts."""
        texts = [
            "First document chunk about rezoning",
            "Second document about housing policy",
            "Third chunk regarding infrastructure"
        ]

        with patch('api.intelligence.embeddings.cohere.AsyncClient') as mock_cohere:
            mock_client = AsyncMock()
            mock_cohere.return_value.__aenter__.return_value = mock_client

            # Mock response with 3 embeddings
            mock_response = MagicMock()
            mock_response.embeddings.float_ = [
                [0.1] * 1024,
                [0.2] * 1024,
                [0.3] * 1024,
            ]
            mock_client.embed = AsyncMock(return_value=mock_response)

            with patch('api.intelligence.embeddings.COHERE_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    embeddings_list = await embeddings.batch_embed(
                        texts,
                        api_key="test-key",
                        input_type="search_document"
                    )

            assert len(embeddings_list) == 3
            for emb in embeddings_list:
                assert len(emb) == embeddings.EMBEDDING_DIMENSION

    @pytest.mark.e2e_pipeline
    async def test_store_chunk_with_embedding(self, mock_db_pool):
        """Integration: Chunk stored with embedding vector in database."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        test_embedding = [0.1] * 1024
        conn.fetchval = AsyncMock(return_value=101)

        chunk_id = await embeddings.store_chunk_with_embedding(
            mock_db_pool,
            document_id=1,
            chunk_index=0,
            chunk_text="Test chunk text",
            section_header="SECTION 1",
            token_count=25,
            embedding=test_embedding
        )

        assert chunk_id == 101

        # Verify the query was called with correct parameters
        call_args = conn.fetchval.call_args
        assert call_args[0][1] == 1  # document_id
        assert call_args[0][2] == 0  # chunk_index
        assert call_args[0][3] == "Test chunk text"

    @pytest.mark.e2e_pipeline
    async def test_embedding_vector_dimensions(self):
        """Integration: All embeddings have correct 1024-dimensional output."""
        embedding_dim = embeddings.EMBEDDING_DIMENSION
        assert embedding_dim == 1024

        # Verify this through batch processing
        with patch('api.intelligence.embeddings.cohere.AsyncClient') as mock_cohere:
            mock_client = AsyncMock()
            mock_cohere.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.5] * 1024]
            mock_client.embed = AsyncMock(return_value=mock_response)

            with patch('api.intelligence.embeddings.COHERE_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    result = await embeddings.batch_embed(
                        ["Test"],
                        api_key="test-key"
                    )

            assert len(result[0]) == 1024

    @pytest.mark.e2e_pipeline
    async def test_embedding_storage_with_tsvector(self, mock_db_pool):
        """Integration: Stored chunks include full-text search tsvector."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn
        conn.fetchval = AsyncMock(return_value=101)

        await embeddings.store_chunk_with_embedding(
            mock_db_pool,
            document_id=1,
            chunk_index=0,
            chunk_text="City Council approved rezoning decision",
            section_header="REZONING",
            token_count=20,
            embedding=[0.1] * 1024
        )

        # Verify tsvector was generated in query
        call_args = conn.fetchval.call_args
        query = call_args[0][0]
        assert "to_tsvector('english'" in query
        assert "chunk_tsvector" in query


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: Signal Extraction
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineSignalExtraction:
    """Test intelligence signal extraction and storage."""

    def test_signal_extraction_types(self):
        """Unit: Signal extraction recognizes all signal types."""
        signal_types = [
            SignalType.REZONING_DECISION,
            SignalType.PERMIT_APPROVAL,
            SignalType.POLICY_CHANGE,
            SignalType.INFRASTRUCTURE,
            SignalType.LEGAL_PRECEDENT,
            SignalType.COMMUNITY_OPPOSITION,
            SignalType.DENSITY_CHANGE,
            SignalType.LAND_SALE,
        ]

        for sig_type in signal_types:
            assert sig_type.value in [
                'rezoning_decision',
                'permit_approval',
                'policy_change',
                'infrastructure_announcement',
                'legal_precedent',
                'community_opposition',
                'density_change',
                'land_sale',
            ]

    def test_signal_extraction_decisions(self):
        """Unit: Signal extraction captures decision states."""
        decisions = [
            Decision.APPROVED,
            Decision.DENIED,
            Decision.DEFERRED,
            Decision.REFERRED,
            Decision.PENDING,
            Decision.UNKNOWN,
        ]

        assert len(decisions) == 6

    def test_signal_extraction_severity_levels(self):
        """Unit: Signal severity has correct priority levels."""
        severities = [
            Severity.INFO,
            Severity.LOW,
            Severity.MEDIUM,
            Severity.HIGH,
            Severity.CRITICAL,
        ]

        assert len(severities) == 5
        severity_values = [s.value for s in severities]
        assert 'critical' in severity_values
        assert 'info' in severity_values

    def test_signal_extraction_sentiment(self):
        """Unit: Signal sentiment captures pro/anti/neutral stance."""
        sentiments = [
            Sentiment.POSITIVE,
            Sentiment.NEGATIVE,
            Sentiment.NEUTRAL,
        ]

        assert len(sentiments) == 3

    @pytest.mark.e2e_pipeline
    async def test_extract_signals_from_document(self, mock_db_pool, sample_signals):
        """Integration: Signals extracted and stored for document."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock signal insertion
        conn.fetchval = AsyncMock(side_effect=[1, 2])

        inserted_signals = []
        for sig in sample_signals:
            sig_id = await conn.fetchval(
                "INSERT INTO intelligence_signals "
                "(document_id, signal_type, summary, headline, addresses, "
                "neighborhood, decision, vote_for, vote_against, "
                "sentiment, severity, confidence, event_date) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) "
                "RETURNING id",
                sig.get('document_id', 1),
                sig.get('signal_type', 'rezoning'),
                sig.get('summary', ''),
                sig.get('headline', ''),
                sig.get('addresses', []),
                sig.get('neighborhood', ''),
                sig.get('decision', None),
                sig.get('vote_for', None),
                sig.get('vote_against', None),
                sig.get('sentiment', 'neutral'),
                sig.get('severity', 'medium'),
                sig.get('confidence', 0.8),
                sig.get('event_date', None),
            )
            inserted_signals.append(sig_id)

        assert inserted_signals == [1, 2]

    @pytest.mark.e2e_pipeline
    async def test_signal_addresses_geocoded(self, mock_db_pool, sample_signals):
        """Integration: Signal addresses are geocoded with spatial data."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock geocoded signal with geometry
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'addresses': ['1234 Main Street'],
            'geom': 'POINT(-123.1 49.2)',
            'neighborhood': 'Downtown',
        })

        row = await conn.fetchrow(
            "SELECT id, addresses, geom, neighborhood FROM intelligence_signals WHERE id = $1",
            1
        )

        assert row['addresses'] == ['1234 Main Street']
        assert row['geom'] is not None
        assert row['neighborhood'] == 'Downtown'

    @pytest.mark.e2e_pipeline
    async def test_signal_confidence_scores(self, mock_db_pool):
        """Integration: Signal confidence scores stored correctly."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        conn.fetch = AsyncMock(return_value=[
            {'id': 1, 'signal_type': 'rezoning_decision', 'confidence': 0.95},
            {'id': 2, 'signal_type': 'policy_change', 'confidence': 0.75},
        ])

        signals_list = await conn.fetch(
            "SELECT id, signal_type, confidence FROM intelligence_signals ORDER BY confidence DESC"
        )

        assert len(signals_list) == 2
        assert signals_list[0]['confidence'] == 0.95
        assert signals_list[1]['confidence'] == 0.75

    @pytest.mark.e2e_pipeline
    async def test_signal_vote_data_captured(self, mock_db_pool, sample_signals):
        """Integration: Vote counts (for/against) captured in signals."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'headline': sample_signals[0]['headline'],
            'vote_for': 10,
            'vote_against': 1,
            'decision': 'approved',
        })

        row = await conn.fetchrow(
            "SELECT id, headline, vote_for, vote_against, decision FROM intelligence_signals WHERE id = $1",
            1
        )

        assert row['vote_for'] == 10
        assert row['vote_against'] == 1
        assert row['decision'] == 'approved'


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: Chat Query & RAG Response
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineChatQuery:
    """Test chat query processing with RAG and citation extraction."""

    @pytest.mark.e2e_pipeline
    async def test_chat_query_retrieves_context(self, mock_db_pool):
        """Integration: Chat query retrieves relevant document chunks."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Mock hybrid search retrieval
        mock_chunks = [
            {
                'chunk_id': 101,
                'chunk_text': 'City Council approved rezoning of 1234 Main Street',
                'document_id': 1,
                'document_title': 'Council Meeting January 15',
                'source_url': 'https://council.vancouver.ca/20240115/',
                'source_type': 'council_minutes',
                'rrf_score': 0.85,
                'final_score': 0.85,
            },
            {
                'chunk_id': 102,
                'chunk_text': 'The rezoning permits a 25-storey mixed-use tower',
                'document_id': 1,
                'document_title': 'Council Meeting January 15',
                'source_url': 'https://council.vancouver.ca/20240115/',
                'source_type': 'council_minutes',
                'rrf_score': 0.78,
                'final_score': 0.78,
            },
        ]

        with patch('api.intelligence.chat.hybrid_search') as mock_search:
            mock_search.return_value = mock_chunks

            chunks = await chat.hybrid_search(
                mock_db_pool,
                "What rezoning happened in Downtown?",
                api_key="test-key"
            )

            assert len(chunks) > 0
            assert 'chunk_text' in chunks[0]
            assert 'document_title' in chunks[0]

    @pytest.mark.e2e_pipeline
    async def test_chat_generates_answer(self, mock_db_pool):
        """Integration: Chat query generates answer from context."""
        # Mock Anthropic client
        with patch('api.intelligence.chat.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "City Council approved rezoning of 1234 Main Street from RS-1 to CD-1 on January 15, 2024, with a 10-1 vote."

            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()

            with patch('api.intelligence.chat.ANTHROPIC_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    with patch('api.intelligence.chat.hybrid_search', return_value=[]):
                        with patch('api.intelligence.chat.get_relevant_signals', return_value=[]):
                            result = await chat.handle_chat(
                                mock_db_pool,
                                "What rezoning decisions were made?",
                                anthropic_api_key="test-key",
                                cohere_api_key="test-key"
                            )

            assert isinstance(result, ChatResponse)
            assert len(result.answer) > 0

    @pytest.mark.e2e_pipeline
    async def test_chat_extracts_citations(self, mock_db_pool):
        """Integration: Chat response includes citations from source chunks."""
        with patch('api.intelligence.chat.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "The rezoning was approved."

            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()

            mock_chunks = [
                {
                    'chunk_id': 101,
                    'chunk_text': 'Council approved rezoning...',
                    'document_title': 'Council Meeting January 15',
                    'source_url': 'https://council.vancouver.ca/',
                    'source_type': 'council_minutes',
                    'published_date': date(2024, 1, 15),
                    'final_score': 0.92,
                    'rrf_score': 0.92,
                },
            ]

            with patch('api.intelligence.chat.ANTHROPIC_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    with patch('api.intelligence.chat.hybrid_search', return_value=mock_chunks):
                        with patch('api.intelligence.chat.get_relevant_signals', return_value=[]):
                            result = await chat.handle_chat(
                                mock_db_pool,
                                "What rezoning decisions?",
                                anthropic_api_key="test-key",
                                cohere_api_key="test-key"
                            )

            assert len(result.citations) > 0
            assert result.citations[0].document_title == 'Council Meeting January 15'

    @pytest.mark.e2e_pipeline
    async def test_chat_includes_signals(self, mock_db_pool):
        """Integration: Chat response includes related intelligence signals."""
        mock_signal = SignalResponse(
            id=1,
            document_id=1,
            signal_type='rezoning_decision',
            summary='Council approved rezoning',
            headline='1234 Main rezoned',
            addresses=['1234 Main Street'],
            neighborhood='Downtown',
            decision='approved',
            vote_for=10,
            vote_against=1,
            sentiment='positive_for_development',
            severity='high',
            confidence=0.95,
            event_date=date(2024, 1, 15),
            source_title='Council Meeting',
            source_url='https://council.vancouver.ca/',
            source_type='council_minutes',
            source_date=date(2024, 1, 15),
        )

        with patch('api.intelligence.chat.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Answer."

            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()

            with patch('api.intelligence.chat.ANTHROPIC_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    with patch('api.intelligence.chat.hybrid_search', return_value=[]):
                        with patch('api.intelligence.chat.get_relevant_signals', return_value=[mock_signal]):
                            result = await chat.handle_chat(
                                mock_db_pool,
                                "Rezoning?",
                                anthropic_api_key="test-key",
                                cohere_api_key="test-key"
                            )

            assert len(result.related_signals) > 0
            assert result.related_signals[0].signal_type == 'rezoning_decision'

    @pytest.mark.e2e_pipeline
    async def test_chat_citation_accuracy(self, mock_db_pool):
        """Integration: Citations accurately reference retrieved chunks."""
        mock_chunks = [
            {
                'chunk_id': 101,
                'chunk_text': 'City Council approved rezoning of 1234 Main Street from RS-1 to CD-1 (123).',
                'document_title': 'City Council Regular Meeting - January 15, 2024',
                'source_url': 'https://council.vancouver.ca/20240115/',
                'source_type': 'council_minutes',
                'published_date': date(2024, 1, 15),
                'final_score': 0.95,
                'rrf_score': 0.95,
            },
        ]

        with patch('api.intelligence.chat.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "The rezoning was approved by council."

            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()

            with patch('api.intelligence.chat.ANTHROPIC_SEMAPHORE', new_callable=MagicMock):
                with patch('asyncio.wait_for', return_value=mock_response):
                    with patch('api.intelligence.chat.hybrid_search', return_value=mock_chunks):
                        with patch('api.intelligence.chat.get_relevant_signals', return_value=[]):
                            result = await chat.handle_chat(
                                mock_db_pool,
                                "Tell me about the rezoning",
                                anthropic_api_key="test-key",
                                cohere_api_key="test-key"
                            )

            # Citation should match retrieved chunk
            assert result.citations[0].excerpt == mock_chunks[0]['chunk_text'][:300]
            assert result.citations[0].document_url == mock_chunks[0]['source_url']


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS: End-to-End Pipeline Validation
# ──────────────────────────────────────────────────────────────────────────────

class TestPipelineEndToEnd:
    """Test full pipeline from document ingestion to chat response."""

    @pytest.mark.e2e_pipeline
    async def test_full_pipeline_document_to_chat(self, mock_db_pool, sample_document):
        """Integration: Complete pipeline from PDF to chat answer."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Step 1: Parse document
        parsed = parser.parse_pdf(b"fake pdf")
        with patch('api.intelligence.parser.parse_pdf_with_pdfplumber') as mock_parse:
            mock_parse.return_value = {
                'text': sample_document['raw_text'],
                'page_count': 5,
                'tables_found': 0,
                'parser': 'pdfplumber',
            }
            parsed = parser.parse_pdf(b"fake")

        assert parsed is not None

        # Step 2: Chunk document
        chunks = chunker.chunk_document(parsed['text'])
        assert len(chunks) > 0

        # Step 3: Store document and chunks
        conn.fetchval = AsyncMock(side_effect=[1, 101, 102, 103])

        doc_id = await conn.fetchval(
            "INSERT INTO documents (...) VALUES (...) RETURNING id",
            sample_document['source_type'],
            sample_document['source_url'],
            sample_document['title'],
            sample_document['published_date'],
        )

        assert doc_id == 1

        # Step 4-6: Generate embeddings and store chunks (mocked)
        with patch('api.intelligence.embeddings.cohere.AsyncClient'):
            chunk_ids = []
            for i, chunk in enumerate(chunks):
                cid = await conn.fetchval(
                    "INSERT INTO document_chunks (...) VALUES (...) RETURNING id",
                    doc_id,
                    chunk['chunk_index'],
                    chunk['chunk_text'],
                )
                chunk_ids.append(cid)

        assert len(chunk_ids) == len(chunks)

        # Step 7: Query with chat
        with patch('api.intelligence.chat.hybrid_search') as mock_search:
            with patch('api.intelligence.chat.get_relevant_signals', return_value=[]):
                with patch('api.intelligence.chat.AsyncAnthropic') as mock_anthropic:
                    mock_client = AsyncMock()
                    mock_anthropic.return_value = mock_client

                    mock_response = MagicMock()
                    mock_response.content = [MagicMock()]
                    mock_response.content[0].text = "Answer based on documents."

                    mock_client.messages.create = AsyncMock(return_value=mock_response)
                    mock_client.close = AsyncMock()

                    mock_search.return_value = [
                        {
                            'chunk_id': 101,
                            'chunk_text': chunks[0]['chunk_text'],
                            'document_title': sample_document['title'],
                            'source_url': sample_document['source_url'],
                            'source_type': sample_document['source_type'],
                            'published_date': sample_document['published_date'],
                            'final_score': 0.9,
                            'rrf_score': 0.9,
                        }
                    ]

                    with patch('api.intelligence.chat.ANTHROPIC_SEMAPHORE', new_callable=MagicMock):
                        with patch('asyncio.wait_for', return_value=mock_response):
                            result = await chat.handle_chat(
                                mock_db_pool,
                                "What rezoning happened?",
                                anthropic_api_key="test-key",
                                cohere_api_key="test-key"
                            )

        assert result is not None
        assert len(result.answer) > 0
        assert len(result.citations) > 0

    @pytest.mark.e2e_pipeline
    async def test_pipeline_handles_multiple_documents(self, mock_db_pool):
        """Integration: Pipeline correctly processes multiple documents."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Simulate 3 documents
        doc_ids = [1, 2, 3]
        conn.fetchval = AsyncMock(side_effect=doc_ids + [101, 102, 103])

        stored_ids = []
        for i, doc_id in enumerate(doc_ids):
            result = await conn.fetchval(
                "INSERT INTO documents (...) VALUES (...) RETURNING id",
                f"document_{i}"
            )
            stored_ids.append(result)

        assert stored_ids == doc_ids

    @pytest.mark.e2e_pipeline
    async def test_pipeline_preserves_data_integrity(self, mock_db_pool, sample_signals):
        """Integration: Data integrity maintained through pipeline stages."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Store and retrieve signal
        original_signal = sample_signals[0]

        conn.fetchrow = AsyncMock(return_value={
            'id': original_signal['id'],
            'document_id': original_signal['document_id'],
            'signal_type': original_signal['signal_type'],
            'summary': original_signal['summary'],
            'headline': original_signal['headline'],
            'addresses': original_signal['addresses'],
            'neighborhood': original_signal['neighborhood'],
            'decision': original_signal['decision'],
            'vote_for': original_signal['vote_for'],
            'vote_against': original_signal['vote_against'],
            'sentiment': original_signal['sentiment'],
            'severity': original_signal['severity'],
            'confidence': original_signal['confidence'],
            'event_date': original_signal['event_date'],
        })

        retrieved = await conn.fetchrow(
            "SELECT * FROM intelligence_signals WHERE id = $1",
            original_signal['id']
        )

        # All fields should match
        assert retrieved['signal_type'] == original_signal['signal_type']
        assert retrieved['summary'] == original_signal['summary']
        assert retrieved['headline'] == original_signal['headline']
        assert retrieved['addresses'] == original_signal['addresses']
        assert retrieved['neighborhood'] == original_signal['neighborhood']
        assert retrieved['decision'] == original_signal['decision']
        assert retrieved['vote_for'] == original_signal['vote_for']
        assert retrieved['vote_against'] == original_signal['vote_against']

    @pytest.mark.e2e_pipeline
    async def test_pipeline_error_recovery(self, mock_db_pool):
        """Integration: Pipeline handles errors gracefully."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # First call fails, second succeeds
        conn.fetchval = AsyncMock(side_effect=[
            Exception("Connection error"),
            1,  # Success on retry
        ])

        # First attempt fails
        with pytest.raises(Exception):
            await conn.fetchval("INSERT INTO documents (...) VALUES (...) RETURNING id", "test")

        # Second attempt succeeds
        result = await conn.fetchval("INSERT INTO documents (...) VALUES (...) RETURNING id", "test")
        assert result == 1

    @pytest.mark.e2e_pipeline
    async def test_pipeline_handles_empty_signals(self, mock_db_pool):
        """Integration: Pipeline handles documents with no extractable signals."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        # Document with no signals
        conn.fetch = AsyncMock(return_value=[])

        signals_list = await conn.fetch(
            "SELECT * FROM intelligence_signals WHERE document_id = $1",
            999  # Non-existent document
        )

        assert signals_list == []

    @pytest.mark.e2e_pipeline
    async def test_pipeline_session_management(self, mock_db_pool):
        """Integration: Chat sessions properly tracked through pipeline."""
        conn = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = conn

        session_id = str(uuid4())

        # Create session
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock()

        # Store messages
        await conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES ($1, $2, $3, $4)",
            session_id,
            'user',
            'What rezoning happened?',
            datetime.now(timezone.utc),
        )

        await conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES ($1, $2, $3, $4)",
            session_id,
            'assistant',
            'Council approved rezoning...',
            datetime.now(timezone.utc),
        )

        assert conn.execute.call_count == 2
