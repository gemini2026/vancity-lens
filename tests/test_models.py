"""Tests for Pydantic models in the intelligence layer."""

from datetime import date
import pytest
from api.intelligence.models import (
    SourceType,
    SignalType,
    Decision,
    Sentiment,
    Severity,
    DocumentCreate,
    DocumentResponse,
    ExtractedSignal,
    SignalResponse,
    ChatRequest,
    ChatResponse,
    SourceCitation,
    SignalFeedRequest,
    SignalFeedResponse,
)


class TestEnums:
    """Test enum definitions."""

    def test_source_type_values(self):
        """Test SourceType enum has expected values."""
        assert SourceType.COUNCIL_MINUTES.value == "council_minutes"
        assert SourceType.REZONING_REPORT.value == "rezoning_report"
        assert SourceType.DPB_MINUTES.value == "dpb_minutes"
        assert SourceType.COURT_RULING.value == "court_ruling"
        assert SourceType.COMMUNITY_PLAN.value == "community_plan"
        assert SourceType.STAFF_REPORT.value == "staff_report"
        assert SourceType.PUBLIC_HEARING.value == "public_hearing"

    def test_signal_type_values(self):
        """Test SignalType enum has expected values."""
        assert SignalType.REZONING_DECISION.value == "rezoning_decision"
        assert SignalType.PERMIT_APPROVAL.value == "permit_approval"
        assert SignalType.POLICY_CHANGE.value == "policy_change"
        assert SignalType.INFRASTRUCTURE.value == "infrastructure_announcement"
        assert SignalType.LEGAL_PRECEDENT.value == "legal_precedent"
        assert SignalType.COMMUNITY_OPPOSITION.value == "community_opposition"
        assert SignalType.DENSITY_CHANGE.value == "density_change"
        assert SignalType.LAND_SALE.value == "land_sale"
        assert SignalType.OTHER.value == "other"

    def test_decision_values(self):
        """Test Decision enum values."""
        assert Decision.APPROVED.value == "approved"
        assert Decision.DENIED.value == "denied"
        assert Decision.DEFERRED.value == "deferred"
        assert Decision.REFERRED.value == "referred"
        assert Decision.PENDING.value == "pending"
        assert Decision.UNKNOWN.value == "unknown"

    def test_sentiment_values(self):
        """Test Sentiment enum values."""
        assert Sentiment.POSITIVE.value == "positive_for_development"
        assert Sentiment.NEGATIVE.value == "negative_for_development"
        assert Sentiment.NEUTRAL.value == "neutral"

    def test_severity_values(self):
        """Test Severity enum values."""
        assert Severity.INFO.value == "info"
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"


class TestDocumentModels:
    """Test document-related models."""

    def test_document_create_minimal(self):
        """Test DocumentCreate with minimal fields."""
        doc = DocumentCreate(
            source_type=SourceType.COUNCIL_MINUTES,
            source_url="https://example.com/doc1"
        )
        assert doc.source_type == SourceType.COUNCIL_MINUTES
        assert doc.source_url == "https://example.com/doc1"
        assert doc.title is None
        assert doc.raw_text is None
        assert doc.file_format == "html"

    def test_document_create_full(self):
        """Test DocumentCreate with all fields."""
        doc = DocumentCreate(
            source_type=SourceType.COUNCIL_MINUTES,
            source_url="https://example.com/doc1",
            title="Council Meeting January 15, 2024",
            published_date=date(2024, 1, 15),
            meeting_date=date(2024, 1, 15),
            raw_text="Meeting content...",
            text_length=1000,
            page_count=5,
            file_format="pdf",
            metadata={"meeting_type": "regular"}
        )
        assert doc.title == "Council Meeting January 15, 2024"
        assert doc.published_date == date(2024, 1, 15)
        assert doc.text_length == 1000
        assert doc.metadata["meeting_type"] == "regular"

    def test_document_response(self):
        """Test DocumentResponse model."""
        doc = DocumentResponse(
            id=1,
            source_type="council_minutes",
            source_url="https://example.com/doc1",
            title="Council Meeting",
            published_date=date(2024, 1, 15),
            meeting_date=date(2024, 1, 15),
            text_length=1000,
            page_count=5,
            file_format="html",
            metadata={},
            processed_at=None,
            scraped_at=date(2024, 1, 16)
        )
        assert doc.id == 1
        assert doc.source_type == "council_minutes"
        assert doc.text_length == 1000


class TestExtractedSignal:
    """Test ExtractedSignal model."""

    def test_extracted_signal_minimal(self):
        """Test ExtractedSignal with minimal required fields."""
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Rezoning approved for 1234 Main Street"
        )
        assert signal.signal_type == SignalType.REZONING_DECISION
        assert signal.summary == "Rezoning approved for 1234 Main Street"
        assert signal.addresses == []
        assert signal.sentiment == Sentiment.NEUTRAL
        assert signal.severity == Severity.INFO
        assert signal.confidence == 0.5

    def test_extracted_signal_full(self):
        """Test ExtractedSignal with all fields."""
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Council approved rezoning of 1234 Main Street from RS-1 to CD-1",
            headline="1234 Main rezoned to CD-1",
            addresses=["1234 Main Street"],
            neighborhood="Downtown",
            zoning_from="RS-1",
            zoning_to="CD-1",
            height_before=10.5,
            height_after=80.0,
            fsr_before=1.0,
            fsr_after=8.5,
            unit_count=300,
            project_value_dollars=150000000,
            decision=Decision.APPROVED,
            vote_for=10,
            vote_against=1,
            conditions=["Public plaza", "Rental housing 20%"],
            sentiment=Sentiment.POSITIVE,
            severity=Severity.HIGH,
            confidence=0.95,
            event_date=date(2024, 1, 15)
        )
        assert signal.unit_count == 300
        assert signal.decision == Decision.APPROVED
        assert signal.vote_for == 10
        assert signal.confidence == 0.95

    def test_extracted_signal_confidence_bounds(self):
        """Test confidence is bounded [0, 1]."""
        # Valid confidence
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Test",
            confidence=0.75
        )
        assert signal.confidence == 0.75

        # Invalid confidence should raise validation error
        with pytest.raises(ValueError):
            ExtractedSignal(
                signal_type=SignalType.REZONING_DECISION,
                summary="Test",
                confidence=1.5
            )

    def test_extracted_signal_with_multiple_addresses(self):
        """Test signal with multiple addresses."""
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Multi-site rezoning",
            addresses=["1234 Main Street", "5678 Granville Street", "100 Broadway"]
        )
        assert len(signal.addresses) == 3
        assert "5678 Granville Street" in signal.addresses


class TestSignalResponse:
    """Test SignalResponse model."""

    def test_signal_response(self):
        """Test SignalResponse with source information."""
        signal = SignalResponse(
            id=1,
            document_id=1,
            signal_type="rezoning_decision",
            summary="Rezoning approved",
            headline="Rezoning approved",
            addresses=["1234 Main Street"],
            neighborhood="Downtown",
            decision="approved",
            vote_for=10,
            vote_against=1,
            sentiment="positive_for_development",
            severity="high",
            confidence=0.95,
            event_date=date(2024, 1, 15),
            source_title="Council Meeting",
            source_url="https://example.com/council",
            source_type="council_minutes",
            source_date=date(2024, 1, 15)
        )
        assert signal.id == 1
        assert signal.source_title == "Council Meeting"
        assert signal.vote_for == 10


class TestChatModels:
    """Test chat-related models."""

    def test_chat_request_minimal(self):
        """Test ChatRequest with minimal fields."""
        request = ChatRequest(query="What rezoning decisions were made?")
        assert request.query == "What rezoning decisions were made?"
        assert request.session_id is None
        assert request.neighborhood_filter is None

    def test_chat_request_full(self):
        """Test ChatRequest with all filters."""
        request = ChatRequest(
            query="Rezoning decisions",
            session_id="session-123",
            neighborhood_filter="Downtown",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31)
        )
        assert request.session_id == "session-123"
        assert request.neighborhood_filter == "Downtown"
        assert request.date_from == date(2024, 1, 1)

    def test_source_citation(self):
        """Test SourceCitation model."""
        citation = SourceCitation(
            document_title="Council Meeting",
            document_url="https://example.com/council",
            source_type="council_minutes",
            published_date=date(2024, 1, 15),
            relevance_score=0.92,
            excerpt="Council voted to approve..."
        )
        assert citation.document_title == "Council Meeting"
        assert citation.relevance_score == 0.92

    def test_chat_response(self):
        """Test ChatResponse model."""
        response = ChatResponse(
            answer="The rezoning decision was approved.",
            citations=[
                SourceCitation(
                    document_title="Council Meeting",
                    document_url="https://example.com",
                    source_type="council_minutes",
                    relevance_score=0.92,
                    excerpt="Council voted..."
                )
            ],
            related_signals=[],
            session_id="session-123"
        )
        assert response.session_id == "session-123"
        assert len(response.citations) == 1
        assert response.citations[0].relevance_score == 0.92


class TestSignalFeedModels:
    """Test signal feed models."""

    def test_signal_feed_request_defaults(self):
        """Test SignalFeedRequest with defaults."""
        request = SignalFeedRequest()
        assert request.limit == 20
        assert request.offset == 0
        assert request.neighborhood is None

    def test_signal_feed_request_with_filters(self):
        """Test SignalFeedRequest with filters."""
        request = SignalFeedRequest(
            neighborhood="Downtown",
            signal_type=SignalType.REZONING_DECISION,
            severity_min=Severity.HIGH,
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            limit=50,
            offset=100
        )
        assert request.neighborhood == "Downtown"
        assert request.signal_type == SignalType.REZONING_DECISION
        assert request.severity_min == Severity.HIGH
        assert request.limit == 50
        assert request.offset == 100

    def test_signal_feed_request_limit_validation(self):
        """Test SignalFeedRequest limit is capped at 100."""
        with pytest.raises(ValueError):
            SignalFeedRequest(limit=150)

    def test_signal_feed_response(self):
        """Test SignalFeedResponse model."""
        signals = [
            SignalResponse(
                id=1,
                document_id=1,
                signal_type="rezoning_decision",
                summary="Rezoning",
                headline="Rezoning",
                addresses=[],
                neighborhood="Downtown",
                sentiment="neutral",
                severity="medium",
                confidence=0.8,
                event_date=date(2024, 1, 15)
            )
        ]
        feed = SignalFeedResponse(
            signals=signals,
            total_count=100,
            has_more=True
        )
        assert len(feed.signals) == 1
        assert feed.total_count == 100
        assert feed.has_more is True

    def test_signal_feed_response_no_more(self):
        """Test SignalFeedResponse when no more results."""
        feed = SignalFeedResponse(
            signals=[],
            total_count=20,
            has_more=False
        )
        assert feed.has_more is False
        assert len(feed.signals) == 0


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_chat_request_from_dict(self):
        """Test creating ChatRequest from dict."""
        data = {
            "query": "Rezoning decisions",
            "session_id": "session-123",
            "neighborhood_filter": "Downtown"
        }
        request = ChatRequest(**data)
        assert request.query == "Rezoning decisions"

    def test_extracted_signal_json_serialization(self):
        """Test ExtractedSignal can be JSON serialized."""
        signal = ExtractedSignal(
            signal_type=SignalType.REZONING_DECISION,
            summary="Test signal",
            confidence=0.85
        )
        # This should not raise
        json_data = signal.model_dump_json()
        assert "rezoning_decision" in json_data
        assert "Test signal" in json_data

    def test_chat_response_serialization(self):
        """Test ChatResponse JSON serialization."""
        response = ChatResponse(
            answer="Test answer",
            session_id="session-123"
        )
        json_data = response.model_dump_json()
        assert "Test answer" in json_data
        assert "session-123" in json_data


class TestModelDefaults:
    """Test model default values."""

    def test_extracted_signal_defaults(self):
        """Test ExtractedSignal default values."""
        signal = ExtractedSignal(
            signal_type=SignalType.OTHER,
            summary="Default test"
        )
        assert signal.addresses == []
        assert signal.conditions == []
        assert signal.sentiment == Sentiment.NEUTRAL
        assert signal.severity == Severity.INFO
        assert signal.confidence == 0.5

    def test_chat_response_defaults(self):
        """Test ChatResponse default values."""
        response = ChatResponse(
            answer="Test",
            session_id="test"
        )
        assert response.citations == []
        assert response.related_signals == []
