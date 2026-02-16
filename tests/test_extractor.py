"""Tests for the LLM extraction pipeline."""

from datetime import date
import pytest
from unittest.mock import AsyncMock, patch, MagicMock  # MagicMock still used in geocoding tests
from api.intelligence.extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    extract_signals_from_chunk,
    geocode_address,
    process_document,
    process_all_unprocessed,
)
from api.intelligence.models import ExtractedSignal, SignalType


class TestExtractionSystemPrompt:
    """Test the extraction system prompt."""

    def test_prompt_exists(self):
        """Test that EXTRACTION_SYSTEM_PROMPT is defined."""
        assert EXTRACTION_SYSTEM_PROMPT is not None
        assert isinstance(EXTRACTION_SYSTEM_PROMPT, str)

    def test_prompt_not_empty(self):
        """Test that prompt is not empty."""
        assert len(EXTRACTION_SYSTEM_PROMPT) > 100

    def test_prompt_contains_key_instructions(self):
        """Test prompt contains key instructions."""
        prompt_lower = EXTRACTION_SYSTEM_PROMPT.lower()
        assert "signal_type" in prompt_lower or "type" in prompt_lower
        assert "summary" in prompt_lower
        assert "address" in prompt_lower
        assert "confidence" in prompt_lower


class TestExtractSignalsFromChunk:
    """Test signal extraction from document chunks."""

    @pytest.mark.asyncio
    async def test_extract_empty_chunk(self):
        """Test extraction from empty chunk."""
        signals = await extract_signals_from_chunk("", {}, "test-key")
        assert signals == []

    @pytest.mark.asyncio
    async def test_extract_with_valid_response(self):
        """Test extraction with mocked LLM returning valid JSON."""
        chunk_text = "City Council approved rezoning of 1234 Main Street from RS-1 to CD-1"
        doc_context = {
            "source_type": "council_minutes",
            "title": "Council Meeting",
            "meeting_date": "2024-01-15",
            "source_url": "https://example.com"
        }

        json_text = """[{
            "signal_type": "rezoning_decision",
            "summary": "City Council approved rezoning",
            "headline": "1234 Main rezoned",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": "2024-01-15"
        }]"""

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=(json_text, "gemini-2.5-flash", 1.5)):
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            assert len(signals) == 1
            assert isinstance(signals[0], ExtractedSignal)
            assert signals[0].signal_type == SignalType.REZONING_DECISION
            assert signals[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_extract_empty_array_response(self):
        """Test extraction when LLM returns empty array."""
        chunk_text = "This is just regular meeting notes with no actionable signals."
        doc_context = {"source_type": "council_minutes"}

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=("[]", "gemini-2.5-flash", 0.8)):
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            assert signals == []

    @pytest.mark.asyncio
    async def test_extract_invalid_json_response(self):
        """Test extraction with invalid JSON response."""
        chunk_text = "Some text"
        doc_context = {}

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=("This is not valid JSON", "gemini-2.5-flash", 0.5)):
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            # Should return empty list on JSON parse error
            assert signals == []

    @pytest.mark.asyncio
    async def test_extract_with_retry_on_api_error(self):
        """Test extraction retries on API error."""
        chunk_text = "Test chunk"
        doc_context = {}

        # First call fails, second succeeds
        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, side_effect=[
            Exception("API Error"),
            ("[]", "gemini-2.5-flash", 0.8),
        ]):
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            # Should succeed after retry
            assert signals == []


class TestGeocodeAddress:
    """Test address geocoding."""

    @pytest.mark.asyncio
    async def test_geocode_empty_address(self):
        """Test geocoding empty address."""
        mock_pool = AsyncMock()
        result = await geocode_address(mock_pool, "")
        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_parcel_match(self):
        """Test geocoding with parcel table match."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock parcel data
        mock_row = {
            "pid": "123456789",
            "civic_address": "1234 Main Street",
            "geom": MagicMock(x=-123.1, y=49.3)
        }
        conn.fetch.return_value = [mock_row]

        result = await geocode_address(mock_pool, "1234 Main Street")

        # Should return coordinates
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_geocode_api_fallback(self):
        """Test geocoding falls back to BC API."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # No parcel match
        conn.fetch.return_value = []

        with patch("api.intelligence.extractor.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock BC geocoder API response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "features": [{
                    "geometry": {
                        "coordinates": [-123.1, 49.3]
                    }
                }]
            }
            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await geocode_address(mock_pool, "1234 Main Street")

            # Should get coordinates from API
            assert result is not None

    @pytest.mark.asyncio
    async def test_geocode_api_no_results(self):
        """Test geocoding when API returns no results."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        with patch("api.intelligence.extractor.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)

            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"features": []}
            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await geocode_address(mock_pool, "Non-existent Street")

            assert result is None


class TestProcessDocument:
    """Test document processing end-to-end."""

    @pytest.mark.asyncio
    async def test_process_nonexistent_document(self):
        """Test processing nonexistent document."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchrow.return_value = None

        result = await process_document(mock_pool, 999, "test-key")

        assert result == 0

    @pytest.mark.asyncio
    async def test_process_document_no_chunks(self):
        """Test processing document with no chunks."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Return document but no chunks
        conn.fetchrow.return_value = {
            "id": 1,
            "source_type": "council_minutes",
            "source_url": "https://example.com",
            "title": "Test",
            "meeting_date": date(2024, 1, 15)
        }
        conn.fetch.return_value = []

        result = await process_document(mock_pool, 1, "test-key")

        assert result == 0


class TestProcessAllUnprocessed:
    """Test batch processing of unprocessed documents."""

    @pytest.mark.asyncio
    async def test_process_no_unprocessed(self):
        """Test when no unprocessed documents exist."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        result = await process_all_unprocessed(mock_pool, "test-key")

        assert result["documents_processed"] == 0

    @pytest.mark.asyncio
    async def test_process_batch_counts(self):
        """Test batch processing returns correct counts."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        result = await process_all_unprocessed(
            mock_pool,
            "test-key",
            batch_size=5
        )

        assert "documents_processed" in result
        assert "signals_extracted" in result
        assert "errors" in result


class TestExtractionIntegration:
    """Integration tests for extraction pipeline."""

    @pytest.mark.asyncio
    async def test_extract_realistic_chunk(self):
        """Test extraction with realistic council minutes chunk."""
        chunk_text = """ITEM 2: REZONING DECISION - 1234 MAIN STREET
Council voted to approve rezoning of 1234 Main Street from RS-1 to CD-1 (123).
Vote: 10-1 in favor.
The site permits a 25-storey mixed-use tower with approximately 300 residential units
and 15,000 square feet of retail space.
Conditions: Public plaza minimum 1500 square metres, 20% rental housing.
Project value estimated at $150 million."""

        doc_context = {
            "source_type": "council_minutes",
            "title": "City Council Regular Meeting - January 15, 2024",
            "meeting_date": "2024-01-15",
            "source_url": "https://council.vancouver.ca/20240115/regulagenda20240115.htm"
        }

        json_text = """[{
            "signal_type": "rezoning_decision",
            "summary": "City Council approved rezoning of 1234 Main Street from RS-1 to CD-1, permitting a 25-storey mixed-use tower with 300 units",
            "headline": "1234 Main rezoned to 25-storey mixed-use",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "zoning_from": "RS-1",
            "zoning_to": "CD-1 (123)",
            "height_before": 10.5,
            "height_after": 80.0,
            "fsr_before": 1.0,
            "fsr_after": 8.5,
            "unit_count": 300,
            "project_value_dollars": 150000000,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "conditions": ["Public plaza minimum 1500 sq m", "Rental housing 20%"],
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": "2024-01-15"
        }]"""

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=(json_text, "gemini-2.5-flash", 2.1)):
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            assert len(signals) == 1
            signal = signals[0]
            assert signal.signal_type == SignalType.REZONING_DECISION
            assert signal.unit_count == 300
            assert signal.confidence == 0.95
            assert "1234 Main Street" in signal.addresses
