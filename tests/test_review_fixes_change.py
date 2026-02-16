"""Tests for ChangeRecord/ChangeRecordResponse models and LLM error wrapping.

Covers:
- ChangeRecord validates confidence range (rejects > 1.0)
- ChangeRecord auto-sets requires_manual_review based on confidence
- ChangeRecord rejects empty plain_english_summary
- ChangeRecordResponse accepts valid data
- parse_extraction_response returns ChangeRecord (not dict)
- extract_regulatory_change wraps LLM errors in ValueError (mock generate_chat to raise)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from api.intelligence.change_extraction import (
    ChangeRecord,
    extract_regulatory_change,
    parse_extraction_response,
)
from api.intelligence.change_routes import (
    ChangeRecordResponse,
    PaginatedChanges,
    PaginationMeta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_change_record_kwargs(**overrides):
    """Return minimal valid kwargs for ChangeRecord."""
    base = {
        "change_type": "bylaw_amendment",
        "geographic_scope": "neighbourhood",
        "affected_areas": ["Downtown"],
        "entitlement_change": {"field": "max_fsr", "before_value": "3.0", "after_value": "5.0"},
        "plain_english_summary": "Downtown FSR increased from 3.0 to 5.0, enabling larger developments.",
        "nlp_confidence_score": 0.92,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ChangeRecord model tests
# ---------------------------------------------------------------------------

class TestChangeRecord:
    """Tests for the ChangeRecord Pydantic model."""

    def test_valid_record(self):
        """ChangeRecord accepts valid data and sets fields correctly."""
        rec = ChangeRecord(**_valid_change_record_kwargs())
        assert rec.change_type == "bylaw_amendment"
        assert rec.nlp_confidence_score == 0.92
        # confidence >= 0.85 => no manual review
        assert rec.requires_manual_review is False

    def test_rejects_confidence_above_1(self):
        """ChangeRecord rejects nlp_confidence_score > 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            ChangeRecord(**_valid_change_record_kwargs(nlp_confidence_score=1.5))
        assert "nlp_confidence_score" in str(exc_info.value)

    def test_rejects_confidence_below_0(self):
        """ChangeRecord rejects nlp_confidence_score < 0.0."""
        with pytest.raises(ValidationError) as exc_info:
            ChangeRecord(**_valid_change_record_kwargs(nlp_confidence_score=-0.1))
        assert "nlp_confidence_score" in str(exc_info.value)

    def test_auto_sets_requires_manual_review_true(self):
        """When confidence < 0.85, requires_manual_review is True."""
        rec = ChangeRecord(**_valid_change_record_kwargs(nlp_confidence_score=0.7))
        assert rec.requires_manual_review is True

    def test_auto_sets_requires_manual_review_false(self):
        """When confidence >= 0.85, requires_manual_review is False."""
        rec = ChangeRecord(**_valid_change_record_kwargs(nlp_confidence_score=0.85))
        assert rec.requires_manual_review is False

    def test_auto_sets_review_overrides_explicit_value(self):
        """Model validator overrides explicit requires_manual_review."""
        rec = ChangeRecord(**_valid_change_record_kwargs(
            nlp_confidence_score=0.5,
            requires_manual_review=False,  # should be overridden to True
        ))
        assert rec.requires_manual_review is True

    def test_rejects_empty_summary(self):
        """ChangeRecord rejects plain_english_summary shorter than 10 chars."""
        with pytest.raises(ValidationError) as exc_info:
            ChangeRecord(**_valid_change_record_kwargs(plain_english_summary="short"))
        assert "plain_english_summary" in str(exc_info.value)

    def test_rejects_blank_summary(self):
        """ChangeRecord rejects empty string summary."""
        with pytest.raises(ValidationError) as exc_info:
            ChangeRecord(**_valid_change_record_kwargs(plain_english_summary=""))
        assert "plain_english_summary" in str(exc_info.value)

    def test_truncates_summary_over_200_words(self):
        """ChangeRecord truncates plain_english_summary exceeding 200 words."""
        long_summary = " ".join(["word"] * 250)
        rec = ChangeRecord(**_valid_change_record_kwargs(plain_english_summary=long_summary))
        # Validator produces: " ".join(first 197 words) + "..."
        # The "..." is appended without a space, so the last token is "word..."
        words = rec.plain_english_summary.split()
        assert len(words) == 197
        assert rec.plain_english_summary.endswith("...")
        assert all(w == "word" for w in words[:196])

    def test_keeps_summary_at_200_words(self):
        """ChangeRecord keeps plain_english_summary at exactly 200 words unchanged."""
        summary_200 = " ".join(["word"] * 200)
        rec = ChangeRecord(**_valid_change_record_kwargs(plain_english_summary=summary_200))
        words = rec.plain_english_summary.split()
        assert len(words) == 200
        assert "..." not in rec.plain_english_summary

    def test_keeps_summary_under_200_words(self):
        """ChangeRecord keeps short plain_english_summary unchanged."""
        short_summary = "Downtown FSR increased from 3.0 to 5.0, enabling larger developments."
        rec = ChangeRecord(**_valid_change_record_kwargs(plain_english_summary=short_summary))
        assert rec.plain_english_summary == short_summary

    def test_rejects_summary_exceeding_max_length(self):
        """ChangeRecord rejects plain_english_summary exceeding 1200 characters."""
        # Create a summary that is under 200 words but over 1200 characters
        # Use long words to exceed char limit while staying under word limit
        long_word = "a" * 100
        # 13 words * 100 chars = 1300 chars + spaces > 1200
        over_chars_summary = " ".join([long_word] * 13)
        with pytest.raises(ValidationError) as exc_info:
            ChangeRecord(**_valid_change_record_kwargs(plain_english_summary=over_chars_summary))
        assert "plain_english_summary" in str(exc_info.value)

    def test_optional_metadata_fields(self):
        """Optional metadata fields default to None."""
        rec = ChangeRecord(**_valid_change_record_kwargs())
        assert rec.source_url is None
        assert rec.source_document_title is None
        assert rec.extraction_model is None
        assert rec.extraction_latency_ms is None

    def test_metadata_fields_set(self):
        """Metadata fields can be set."""
        rec = ChangeRecord(**_valid_change_record_kwargs(
            source_url="https://example.com/doc",
            source_document_title="Council Minutes",
            extraction_model="claude-3-sonnet",
            extraction_latency_ms=450,
        ))
        assert rec.source_url == "https://example.com/doc"
        assert rec.source_document_title == "Council Minutes"
        assert rec.extraction_model == "claude-3-sonnet"
        assert rec.extraction_latency_ms == 450


# ---------------------------------------------------------------------------
# ChangeRecordResponse model tests
# ---------------------------------------------------------------------------

class TestChangeRecordResponse:
    """Tests for the ChangeRecordResponse Pydantic model."""

    def test_accepts_valid_data(self):
        """ChangeRecordResponse accepts valid data with all fields."""
        resp = ChangeRecordResponse(
            change_id="550e8400-e29b-41d4-a716-446655440000",
            signal_id=42,
            change_type="bylaw_amendment",
            source_url="https://example.com",
            source_document_title="Council Minutes",
            publication_date="2026-01-15",
            effective_date="2026-03-01",
            geographic_scope="neighbourhood",
            affected_areas=["Downtown", "Kitsilano"],
            entitlement_change={"field": "max_fsr", "after_value": "5.0"},
            plain_english_summary="FSR increased to 5.0 in Downtown.",
            nlp_confidence_score=0.92,
            requires_manual_review=False,
            extraction_timestamp="2026-01-20T12:00:00",
            created_at="2026-01-20T12:00:00",
        )
        assert resp.change_id == "550e8400-e29b-41d4-a716-446655440000"
        assert resp.affected_areas == ["Downtown", "Kitsilano"]
        assert resp.nlp_confidence_score == 0.92

    def test_accepts_minimal_data(self):
        """ChangeRecordResponse works with only required fields + defaults."""
        resp = ChangeRecordResponse(
            change_id="550e8400-e29b-41d4-a716-446655440000",
            change_type="policy_update",
        )
        assert resp.signal_id is None
        assert resp.affected_areas == []
        assert resp.entitlement_change == {}
        assert resp.source_url is None


class TestPaginatedChanges:
    """Tests for the PaginatedChanges response model."""

    def test_valid_paginated_response(self):
        """PaginatedChanges constructs correctly."""
        result = PaginatedChanges(
            results=[
                ChangeRecordResponse(
                    change_id="abc-123",
                    change_type="bylaw_amendment",
                ),
            ],
            pagination=PaginationMeta(
                page=1, per_page=20, total=1, total_pages=1,
            ),
        )
        assert len(result.results) == 1
        assert result.pagination.total == 1


# ---------------------------------------------------------------------------
# parse_extraction_response tests
# ---------------------------------------------------------------------------

class TestParseExtractionResponse:
    """Tests for parse_extraction_response returning ChangeRecord."""

    def test_returns_change_record(self):
        """parse_extraction_response returns a ChangeRecord instance, not dict."""
        llm_json = json.dumps({
            "change_type": "bylaw_amendment",
            "geographic_scope": "neighbourhood",
            "affected_areas": ["Downtown"],
            "entitlement_change": {"field": "max_fsr"},
            "plain_english_summary": "Downtown FSR increased significantly for new developments.",
            "confidence": 0.9,
        })
        result = parse_extraction_response(llm_json)
        assert isinstance(result, ChangeRecord)
        assert result.nlp_confidence_score == 0.9
        assert result.requires_manual_review is False

    def test_maps_confidence_to_nlp_confidence_score(self):
        """The LLM 'confidence' key is mapped to 'nlp_confidence_score'."""
        llm_json = json.dumps({
            "change_type": "policy_update",
            "geographic_scope": "citywide",
            "affected_areas": [],
            "entitlement_change": {},
            "plain_english_summary": "City-wide parking requirements relaxed for new developments.",
            "confidence": 0.75,
        })
        result = parse_extraction_response(llm_json)
        assert result.nlp_confidence_score == 0.75
        assert result.requires_manual_review is True

    def test_invalid_json_raises_value_error(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_extraction_response("not json{{{")

    def test_missing_required_field_raises_value_error(self):
        """Missing required field raises ValueError."""
        llm_json = json.dumps({
            "change_type": "bylaw_amendment",
            # missing geographic_scope, affected_areas, etc.
        })
        with pytest.raises(ValueError, match="Validation failed"):
            parse_extraction_response(llm_json)


# ---------------------------------------------------------------------------
# extract_regulatory_change LLM error wrapping tests
# ---------------------------------------------------------------------------

class TestExtractRegulatoryChangeLLMErrorWrapping:
    """Tests that extract_regulatory_change wraps LLM errors in ValueError."""

    @pytest.mark.asyncio
    async def test_wraps_llm_runtime_error(self):
        """RuntimeError from generate_chat is wrapped in ValueError."""
        chunk = "The city council approved a bylaw amendment increasing the FSR limit in Downtown from 3.0 to 5.0."
        with patch(
            "api.intelligence.change_extraction.generate_chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API timeout"),
        ):
            with pytest.raises(ValueError, match="LLM extraction failed.*API timeout"):
                await extract_regulatory_change(
                    chunk_text=chunk,
                    source_url="https://example.com/doc",
                    source_title="Test Doc",
                )

    @pytest.mark.asyncio
    async def test_wraps_llm_connection_error(self):
        """ConnectionError from generate_chat is wrapped in ValueError."""
        chunk = "The city council approved a rezoning of Kitsilano to allow higher density residential."
        with patch(
            "api.intelligence.change_extraction.generate_chat",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Network unreachable"),
        ):
            with pytest.raises(ValueError, match="LLM extraction failed.*Network unreachable"):
                await extract_regulatory_change(
                    chunk_text=chunk,
                    source_url="https://example.com/doc",
                    source_title="Test Doc",
                )

    @pytest.mark.asyncio
    async def test_preserves_original_exception_as_cause(self):
        """The original exception is preserved as __cause__."""
        chunk = "A public hearing is scheduled to discuss potential zoning changes in Mount Pleasant neighbourhood."
        with patch(
            "api.intelligence.change_extraction.generate_chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("original error"),
        ):
            with pytest.raises(ValueError) as exc_info:
                await extract_regulatory_change(
                    chunk_text=chunk,
                    source_url="https://example.com/doc",
                    source_title="Test Doc",
                )
            assert exc_info.value.__cause__ is not None
            assert isinstance(exc_info.value.__cause__, RuntimeError)

    @pytest.mark.asyncio
    async def test_successful_extraction_returns_change_record(self):
        """Successful LLM call returns a ChangeRecord."""
        chunk = "City Council approved bylaw amendment 12345 increasing FSR from 3.0 to 5.0 in Downtown."
        llm_response = json.dumps({
            "change_type": "bylaw_amendment",
            "geographic_scope": "neighbourhood",
            "affected_areas": ["Downtown"],
            "entitlement_change": {"field": "max_fsr", "before_value": "3.0", "after_value": "5.0"},
            "plain_english_summary": "Downtown FSR increased from 3.0 to 5.0, enabling larger developments.",
            "confidence": 0.95,
        })
        with patch(
            "api.intelligence.change_extraction.generate_chat",
            new_callable=AsyncMock,
            return_value=(llm_response, "claude-3-sonnet", 0.45),
        ):
            result = await extract_regulatory_change(
                chunk_text=chunk,
                source_url="https://example.com/doc",
                source_title="Council Minutes",
            )
            assert isinstance(result, ChangeRecord)
            assert result.change_type == "bylaw_amendment"
            assert result.nlp_confidence_score == 0.95
            assert result.source_url == "https://example.com/doc"
            assert result.source_document_title == "Council Minutes"
            assert result.extraction_model == "claude-3-sonnet"
            assert result.extraction_latency_ms == 450
            assert result.requires_manual_review is False
