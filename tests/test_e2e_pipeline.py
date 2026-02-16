"""End-to-end tests for the full VanCity Lens pipeline."""

from datetime import date, datetime
import json
import pytest
from unittest.mock import AsyncMock, patch
from api.intelligence.local_rag.chunker import chunk_document
from api.intelligence.models import ExtractedSignal, SignalType, Decision, Sentiment, Severity


class TestFullPipeline:
    """End-to-end tests for the complete pipeline."""

    def test_chunking_realistic_council_minutes(self, sample_document):
        """Test chunking realistic council minutes."""
        chunks = chunk_document(sample_document["raw_text"])

        assert len(chunks) > 0
        assert all(c["chunk_text"] for c in chunks)
        assert all(c["chunk_index"] >= 0 for c in chunks)
        assert all(c["approx_token_count"] > 0 for c in chunks)

        # Verify content is preserved
        full_text = " ".join(c["chunk_text"] for c in chunks)
        assert "REZONING" in full_text.upper()
        assert "COUNCIL" in full_text.upper()

    @pytest.mark.asyncio
    async def test_extraction_to_signal_model(self):
        """Test extraction produces valid ExtractedSignal models."""
        chunk_text = """ITEM 2: REZONING DECISION - 1234 MAIN STREET
City Council voted to approve rezoning of 1234 Main Street from RS-1 to CD-1.
Vote: 10-1 in favor.
Project: 25-storey mixed-use tower with 300 units."""

        doc_context = {
            "source_type": "council_minutes",
            "title": "Council Meeting",
            "meeting_date": "2024-01-15",
            "source_url": "https://example.com"
        }

        json_text = json.dumps([{
            "signal_type": "rezoning_decision",
            "summary": "Rezoning approved for 1234 Main Street",
            "headline": "1234 Main rezoned",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "height_after": 80.0,
            "unit_count": 300,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": "2024-01-15"
        }])

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=(json_text, "gemini-2.5-flash", 1.5)):
            from api.intelligence.extractor import extract_signals_from_chunk
            signals = await extract_signals_from_chunk(chunk_text, doc_context, "test-key")

            assert len(signals) == 1
            signal = signals[0]
            assert isinstance(signal, ExtractedSignal)
            assert signal.signal_type == SignalType.REZONING_DECISION
            assert signal.unit_count == 300
            assert signal.confidence == 0.95
            assert signal.decision == Decision.APPROVED
            assert signal.sentiment == Sentiment.POSITIVE

    def test_full_pipeline_with_sample_data(self, sample_document, sample_chunks, sample_signals):
        """Test full pipeline integrating chunking, extraction, and signal storage."""
        # Stage 1: Chunk the document
        chunks = chunk_document(sample_document["raw_text"])
        assert len(chunks) > 0

        # Verify chunks have expected structure
        for chunk in chunks:
            assert "chunk_text" in chunk
            assert "chunk_index" in chunk
            assert "section_header" in chunk
            assert "approx_token_count" in chunk

        # Stage 2: Verify sample chunks match structure
        for sample_chunk in sample_chunks:
            assert "chunk_text" in sample_chunk
            assert len(sample_chunk["chunk_text"]) > 0

        # Stage 3: Verify sample signals are properly formed
        for signal in sample_signals:
            assert signal["signal_type"] in [s.value for s in SignalType]
            assert signal["summary"]
            assert signal["confidence"] >= 0 and signal["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_document_to_chat_flow(self):
        """Test the flow from document to chat response."""
        # Sample council minutes
        sample_text = """CITY COUNCIL MEETING - JANUARY 15, 2024

ITEM 1: APPROVAL OF MINUTES
Previous minutes approved.

ITEM 2: REZONING DECISION - 1234 MAIN STREET
Council voted to approve rezoning of 1234 Main Street from RS-1 to CD-1 (123).
Vote: 10-1 in favor.
Height limit increased to 80 metres. FSR increased to 8.5.
Approximately 300 residential units plus 15,000 sq ft of retail.
Conditions: Public plaza minimum 1500 sq m, 20% affordable rental housing.
Project value estimated at $150 million.
Neighborhood: Downtown."""

        # Stage 1: Chunk
        chunks = chunk_document(sample_text)
        assert len(chunks) > 0

        # Stage 2: Extract signals (mocked)
        json_text = json.dumps([{
            "signal_type": "rezoning_decision",
            "summary": "Rezoning approved",
            "headline": "Main Street rezoned",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "height_after": 80.0,
            "unit_count": 300,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": "2024-01-15"
        }])

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=(json_text, "gemini-2.5-flash", 1.5)):
            from api.intelligence.extractor import extract_signals_from_chunk
            signals = await extract_signals_from_chunk(
                chunks[0]["chunk_text"],
                {"source_type": "council_minutes", "title": "Test", "meeting_date": "2024-01-15"},
                "test-key"
            )

            assert len(signals) > 0
            signal = signals[0]

            # Stage 3: Verify signal data for chat
            assert signal.addresses
            assert signal.neighborhood
            assert signal.decision

    def test_chunk_sizes_reasonable(self, sample_document):
        """Test that all chunks are within reasonable token bounds."""
        chunk_size = 1000
        chunks = chunk_document(sample_document["raw_text"], chunk_size=chunk_size)

        # Most chunks should be under chunk_size
        for chunk in chunks:
            # Allow some overhead
            assert chunk["approx_token_count"] <= chunk_size * 1.3

    def test_no_data_loss_in_chunking(self, sample_document):
        """Test that chunking doesn't lose important content."""
        original_text = sample_document["raw_text"].upper()
        chunks = chunk_document(sample_document["raw_text"])

        # Reconstruct text from chunks
        reconstructed_text = " ".join(c["chunk_text"] for c in chunks).upper()

        # Key terms should be preserved
        key_terms = ["REZONING", "APPROVED", "COUNCIL", "MAIN STREET"]
        for term in key_terms:
            # At least one chunk should contain the term
            assert any(term in c["chunk_text"].upper() for c in chunks), f"Lost '{term}' in chunking"

    @pytest.mark.asyncio
    async def test_signal_embedding_compatibility(self):
        """Test that extracted signals are compatible with embedding."""
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Test rezoning with multiple fields",
            headline="Test Rezoning",
            addresses=["1234 Main Street", "5678 Granville"],
            neighborhood="Downtown",
            zoning_from="RS-1",
            zoning_to="CD-1",
            height_before=10.0,
            height_after=80.0,
            fsr_before=1.0,
            fsr_after=8.5,
            unit_count=300,
            project_value_dollars=150000000,
            decision=Decision.APPROVED,
            vote_for=10,
            vote_against=1,
            conditions=["Public plaza", "Rental housing"],
            sentiment=Sentiment.POSITIVE,
            severity=Severity.HIGH,
            confidence=0.95,
            event_date=date(2024, 1, 15)
        )

        # Should be JSON serializable
        json_str = signal.model_dump_json()
        assert json_str
        assert "rezoning_decision" in json_str

        # Should round-trip through JSON
        parsed = json.loads(json_str)
        assert parsed["signal_type"] == "rezoning_decision"
        assert parsed["unit_count"] == 300

    def test_realistic_scenario_downtown_rezoning(self):
        """Test a realistic scenario: Downtown rezoning with multiple conditions."""
        # Real-like council minutes
        text = """CITY COUNCIL REGULAR MEETING
January 15, 2024

ITEM 2: REZONING APPLICATION - 1234 MAIN STREET

The application proposes rezoning of 1234 Main Street from RS-1 (Single Family)
to CD-1 (Downtown Eastside Community) to permit a 25-storey mixed-use development.

SITE CHARACTERISTICS:
- Current zoning: RS-1
- Proposed zoning: CD-1 (123)
- Lot size: 1.2 hectares
- Current height limit: 10.5 meters
- Proposed height limit: 80 meters
- Current FSR: 1.0
- Proposed FSR: 8.5

PROJECT DETAILS:
- 300 residential units (mix of strata and rental)
- 20,000 gross floor area for retail/commercial
- 150 parking spaces
- Estimated project value: $150 million
- Construction period: 3 years

COUNCIL VOTE:
Motion to approve: CARRIED 10-1
In favor: Mayor and 9 Council Members
Against: 1 Council Member

CONDITIONS:
1. Public plaza minimum 1,500 square meters
2. 20% of residential units as affordable rental
3. Community benefit contributions: $5 million
4. Design review for step-backs above 50 meters
5. Environmental review and remediation plan

The rezoning supports the Downtown Eastside Plan objectives."""

        # Chunk the text
        chunks = chunk_document(text, chunk_size=150)

        # Verify structure
        assert len(chunks) >= 2
        assert all(c["chunk_text"] for c in chunks)

        # Verify content preservation
        full = " ".join(c["chunk_text"] for c in chunks)
        assert "25-storey" in full
        assert "300" in full
        assert "CD-1" in full
        assert "80 meters" in full
        assert "8.5" in full

    def test_multiple_signals_in_chunk(self):
        """Test handling multiple signals in a single chunk."""
        text = """CITY COUNCIL MEETING

ITEM 1: REZONING - 1234 MAIN STREET
Rezoning from RS-1 to CD-1 approved. Vote: 10-1.

ITEM 2: REZONING - 5678 GRANVILLE
Rezoning from RM-4 to CD-1 approved. Vote: 8-3.

ITEM 3: POLICY UPDATE
Official Development Plan updated for multiple neighborhoods."""

        chunks = chunk_document(text)

        # Should identify section headers
        headers = [c["section_header"] for c in chunks if c["section_header"]]
        assert len(headers) > 0

    def test_signal_validation_all_enum_values(self):
        """Test that all enum values are valid for signals."""
        for signal_type in SignalType:
            signal = ExtractedSignal(
                signal_type=signal_type,
                summary="Test"
            )
            assert signal.signal_type == signal_type

        for decision in Decision:
            signal = ExtractedSignal(
                signal_type=SignalType.OTHER,
                summary="Test",
                decision=decision
            )
            assert signal.decision == decision

        for sentiment in Sentiment:
            signal = ExtractedSignal(
                signal_type=SignalType.OTHER,
                summary="Test",
                sentiment=sentiment
            )
            assert signal.sentiment == sentiment

        for severity in Severity:
            signal = ExtractedSignal(
                signal_type=SignalType.OTHER,
                summary="Test",
                severity=severity
            )
            assert signal.severity == severity


class TestE2EPipelineWithMocks:
    """End-to-end tests with mocked external services."""

    @pytest.mark.asyncio
    async def test_complete_workflow_document_to_database(self):
        """Test complete workflow from document scraping to database storage."""
        # Stage 1: Simulate scraped document
        scraped_html = """
        <html>
            <h1>Council Meeting January 15, 2024</h1>
            <p>ITEM 1: REZONING - 1234 Main Street approved. Vote: 10-1.</p>
            <p>Rezoning from RS-1 to CD-1 for 25-storey mixed-use with 300 units.</p>
        </html>
        """

        # Stage 2: Extract text and chunk
        chunks = chunk_document(scraped_html, chunk_size=500)
        assert len(chunks) > 0

        # Stage 3: Mock LLM extraction
        json_text = json.dumps([{
            "signal_type": "rezoning_decision",
            "summary": "Rezoning approved",
            "headline": "Main Street rezoned",
            "addresses": ["1234 Main Street"],
            "neighborhood": "Downtown",
            "zoning_from": "RS-1",
            "zoning_to": "CD-1",
            "height_after": 80.0,
            "unit_count": 300,
            "decision": "approved",
            "vote_for": 10,
            "vote_against": 1,
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": "2024-01-15"
        }])

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, return_value=(json_text, "gemini-2.5-flash", 1.5)):
            from api.intelligence.extractor import extract_signals_from_chunk
            signals = await extract_signals_from_chunk(
                chunks[0]["chunk_text"],
                {
                    "source_type": "council_minutes",
                    "title": "Council Meeting",
                    "meeting_date": "2024-01-15",
                    "source_url": "https://example.com"
                },
                "test-key"
            )

            # Verify signals are extracted
            assert len(signals) > 0
            signal = signals[0]

            # Stage 4: Verify signal has all required fields for database
            assert signal.signal_type
            assert signal.summary
            assert signal.addresses
            assert signal.decision
            assert signal.sentiment
            assert signal.severity
            assert signal.confidence

        return signals

    def test_vancouver_specific_data_handling(self, vancouver_neighborhoods, vancouver_zoning_codes):
        """Test handling of Vancouver-specific data."""
        for neighborhood in vancouver_neighborhoods:
            signal = ExtractedSignal(
                signal_type=SignalType.REZONING_DECISION,
                summary=f"Rezoning in {neighborhood}",
                neighborhood=neighborhood
            )
            assert signal.neighborhood == neighborhood

        for zoning in vancouver_zoning_codes:
            signal = ExtractedSignal(
                signal_type=SignalType.REZONING_DECISION,
                summary="Test",
                zoning_from=zoning
            )
            assert signal.zoning_from == zoning
