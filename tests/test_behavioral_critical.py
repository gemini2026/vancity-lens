"""
Critical behavioral tests for 5 key gaps:
  1. compute_entitlement ParcelNotFoundError
  2. store_change_record duplicate detection
  3. extract_regulatory_change full pipeline
  4. parse_extraction_response error paths
  5. generate_undervalued_alerts behavioral test
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Gap 1: compute_entitlement raises ParcelNotFoundError when parcel missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_entitlement_parcel_not_found():
    """compute_entitlement must raise ParcelNotFoundError when fetchrow returns None."""
    from api.entitlement import compute_entitlement, ParcelNotFoundError

    # The function signature is: compute_entitlement(conn, pid)
    # conn is an asyncpg.Connection, not a pool
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)  # parcel not found

    with pytest.raises(ParcelNotFoundError) as exc_info:
        await compute_entitlement(mock_conn, "999-999-999")

    assert "999-999-999" in str(exc_info.value)
    # Verify the correct SQL was called (the first fetchrow is for parcel info)
    mock_conn.fetchrow.assert_called_once()


# ---------------------------------------------------------------------------
# Gap 2: store_change_record duplicate detection
# ---------------------------------------------------------------------------


def _make_valid_change_record(**overrides):
    """Helper to create a valid ChangeRecord with sensible defaults."""
    from api.intelligence.change_extraction import ChangeRecord

    defaults = {
        "change_type": "bylaw_amendment",
        "geographic_scope": "citywide",
        "affected_areas": ["Downtown"],
        "entitlement_change": {"field": "max_fsr"},
        "plain_english_summary": "FSR increased citywide from 3.0 to 5.0",
        "nlp_confidence_score": 0.92,
        "source_url": "https://example.com/doc",
        "source_document_title": "Test Document",
    }
    defaults.update(overrides)
    return ChangeRecord(**defaults)


def _mock_pool_and_conn():
    """Create a mock asyncpg pool + connection for db_pool.acquire() context.

    asyncpg uses ``async with pool.acquire() as conn``, so ``acquire()``
    must return an async context manager (not a coroutine).  We build one
    with MagicMock so that __aenter__/__aexit__ work correctly.
    """
    mock_conn = AsyncMock()

    # Build an object that supports the async-context-manager protocol
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=mock_conn)
    acm.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acm
    return mock_pool, mock_conn


@pytest.mark.asyncio
async def test_store_change_record_new_record():
    """New record (no duplicate) should insert and return a new ID."""
    from api.intelligence.change_extraction import store_change_record

    mock_pool, mock_conn = _mock_pool_and_conn()
    new_id = uuid.uuid4().int % 10000  # arbitrary int ID

    # First fetchval = duplicate check → None (no duplicate)
    # Second fetchval = INSERT RETURNING → new_id
    mock_conn.fetchval = AsyncMock(side_effect=[None, new_id])

    record = _make_valid_change_record()
    result = await store_change_record(mock_pool, record)

    assert result == new_id
    assert mock_conn.fetchval.call_count == 2


@pytest.mark.asyncio
async def test_store_change_record_duplicate():
    """Duplicate record should return existing ID without inserting."""
    from api.intelligence.change_extraction import store_change_record

    mock_pool, mock_conn = _mock_pool_and_conn()
    existing_id = 42

    # fetchval returns existing ID on duplicate check
    mock_conn.fetchval = AsyncMock(return_value=existing_id)

    record = _make_valid_change_record()
    result = await store_change_record(mock_pool, record)

    assert result == existing_id
    # Only one fetchval call (duplicate check), no insert
    assert mock_conn.fetchval.call_count == 1


@pytest.mark.asyncio
async def test_store_change_record_invalid_record():
    """Passing invalid data (missing required fields) should raise ValidationError."""
    from pydantic import ValidationError
    from api.intelligence.change_extraction import ChangeRecord

    with pytest.raises(ValidationError):
        ChangeRecord(
            change_type="bylaw_amendment",
            # missing geographic_scope, affected_areas, entitlement_change,
            # plain_english_summary, nlp_confidence_score
        )


# ---------------------------------------------------------------------------
# Gap 3: extract_regulatory_change full pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_regulatory_change_non_candidate():
    """Non-candidate text (no regulatory keywords) should raise ValueError."""
    from api.intelligence.change_extraction import extract_regulatory_change

    short_text = "The weather in Vancouver is quite pleasant today."

    with pytest.raises(ValueError, match="does not appear to contain regulatory content"):
        await extract_regulatory_change(
            chunk_text=short_text,
            source_url="https://example.com/weather",
            source_title="Weather Report",
        )


@pytest.mark.asyncio
async def test_extract_regulatory_change_short_text():
    """Text shorter than 50 chars should raise ValueError (fails is_candidate_chunk)."""
    from api.intelligence.change_extraction import extract_regulatory_change

    with pytest.raises(ValueError, match="does not appear to contain regulatory content"):
        await extract_regulatory_change(
            chunk_text="Short zoning note.",
            source_url="https://example.com/short",
            source_title="Short Doc",
        )


@pytest.mark.asyncio
async def test_extract_regulatory_change_success():
    """Valid candidate text with mocked LLM should return a ChangeRecord with metadata."""
    from api.intelligence.change_extraction import extract_regulatory_change, ChangeRecord

    # Text that passes is_candidate_chunk (>50 chars, contains "bylaw" and "zoning")
    candidate_text = (
        "The City Council has approved a new bylaw amendment to the zoning "
        "regulations in Downtown Vancouver. The FSR has been increased from "
        "3.0 to 5.0 for all parcels within the designated area, effective "
        "immediately as per the official community plan update."
    )

    llm_json_response = json.dumps({
        "change_type": "bylaw_amendment",
        "geographic_scope": "neighbourhood",
        "affected_areas": ["Downtown"],
        "entitlement_change": {
            "field": "max_fsr",
            "before_value": "3.0",
            "after_value": "5.0",
        },
        "plain_english_summary": "Downtown FSR increased from 3.0 to 5.0, enabling larger developments.",
        "confidence": 0.92,
    })

    with patch("api.intelligence.change_extraction.generate_chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = (llm_json_response, "claude-3-sonnet", 0.5)

        result = await extract_regulatory_change(
            chunk_text=candidate_text,
            source_url="https://vancouver.ca/bylaw-12345",
            source_title="Bylaw 12345",
        )

    assert isinstance(result, ChangeRecord)
    assert result.change_type == "bylaw_amendment"
    assert result.geographic_scope == "neighbourhood"
    assert result.nlp_confidence_score == 0.92
    assert result.source_url == "https://vancouver.ca/bylaw-12345"
    assert result.source_document_title == "Bylaw 12345"
    assert result.extraction_model == "claude-3-sonnet"
    assert result.extraction_latency_ms == 500  # int(0.5 * 1000)
    # confidence >= 0.85 → requires_manual_review should be False
    assert result.requires_manual_review is False


@pytest.mark.asyncio
async def test_extract_regulatory_change_low_confidence_sets_review():
    """ChangeRecord with confidence < 0.85 should have requires_manual_review=True."""
    from api.intelligence.change_extraction import extract_regulatory_change

    candidate_text = (
        "There are rumors of a potential rezoning initiative in the Kitsilano "
        "neighbourhood that could affect current zoning designations. The public "
        "hearing has been scheduled but no decisions have been made yet."
    )

    llm_json_response = json.dumps({
        "change_type": "public_hearing",
        "geographic_scope": "neighbourhood",
        "affected_areas": ["Kitsilano"],
        "entitlement_change": {},
        "plain_english_summary": "Public hearing scheduled for potential Kitsilano zoning changes; specific changes TBD.",
        "confidence": 0.65,
    })

    with patch("api.intelligence.change_extraction.generate_chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = (llm_json_response, "claude-3-sonnet", 0.3)

        result = await extract_regulatory_change(
            chunk_text=candidate_text,
            source_url="https://example.com/hearing",
            source_title="Public Hearing Notice",
        )

    assert result.requires_manual_review is True
    assert result.nlp_confidence_score == 0.65


# ---------------------------------------------------------------------------
# Gap 4: parse_extraction_response error paths
# ---------------------------------------------------------------------------


def test_parse_extraction_response_malformed_json():
    """Malformed JSON string should raise ValueError with 'Invalid JSON'."""
    from api.intelligence.change_extraction import parse_extraction_response

    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_extraction_response("this is not json {{{")


def test_parse_extraction_response_missing_change_type():
    """Valid JSON missing 'change_type' should raise ValueError with 'Validation failed'."""
    from api.intelligence.change_extraction import parse_extraction_response

    incomplete = json.dumps({
        "geographic_scope": "citywide",
        "affected_areas": ["Downtown"],
        "entitlement_change": {},
        "plain_english_summary": "Some summary about zoning changes that is long enough",
        "confidence": 0.85,
    })

    with pytest.raises(ValueError, match="Validation failed"):
        parse_extraction_response(incomplete)


def test_parse_extraction_response_confidence_above_one():
    """Confidence > 1.0 should raise ValueError (Pydantic validation)."""
    from api.intelligence.change_extraction import parse_extraction_response

    invalid_confidence = json.dumps({
        "change_type": "bylaw_amendment",
        "geographic_scope": "citywide",
        "affected_areas": ["Downtown"],
        "entitlement_change": {"field": "max_fsr"},
        "plain_english_summary": "FSR increased citywide from 3.0 to 5.0 in the Downtown area",
        "confidence": 1.5,  # > 1.0 — should fail le=1.0 constraint
    })

    with pytest.raises(ValueError, match="Validation failed"):
        parse_extraction_response(invalid_confidence)


def test_parse_extraction_response_valid():
    """Valid JSON with all required fields should return a ChangeRecord."""
    from api.intelligence.change_extraction import parse_extraction_response, ChangeRecord

    valid = json.dumps({
        "change_type": "bylaw_amendment",
        "geographic_scope": "citywide",
        "affected_areas": ["Downtown"],
        "entitlement_change": {"field": "max_fsr"},
        "plain_english_summary": "FSR increased citywide from 3.0 to 5.0 in the Downtown area",
        "confidence": 0.90,
    })

    result = parse_extraction_response(valid)
    assert isinstance(result, ChangeRecord)
    assert result.nlp_confidence_score == 0.90
    assert result.change_type == "bylaw_amendment"


# ---------------------------------------------------------------------------
# Gap 5: generate_undervalued_alerts behavioral test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_undervalued_alerts_creates_alerts():
    """Undervalued parcels matching a watchlist rule should create alerts."""
    from api.intelligence.undervalued_scoring import generate_undervalued_alerts

    mock_pool, mock_conn = _mock_pool_and_conn()

    # Mock watchlist rules query result — one rule: undervalued_discount >= 30
    watchlist_rows = [
        {
            "id": 1,
            "user_id": 10,
            "rule_type": "undervalued_discount",
            "rule_value": "30",
        },
    ]
    mock_conn.fetch = AsyncMock(return_value=watchlist_rows)
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")

    scored_parcels = [
        {
            "pid": "012-345-678",
            "discount_pct": 45.0,  # above 30 threshold
            "lot_area_sqft": 5000,
            "tod_tier": 1,
            "is_undervalued": True,
            "neighborhood": "Downtown",
        },
    ]

    result = await generate_undervalued_alerts(mock_pool, scored_parcels)

    assert result == 1
    # execute should have been called to insert the alert
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_generate_undervalued_alerts_empty_watchlists():
    """Empty watchlists (no rules returned) should return 0 alerts."""
    from api.intelligence.undervalued_scoring import generate_undervalued_alerts

    mock_pool, mock_conn = _mock_pool_and_conn()

    # No watchlist rules
    mock_conn.fetch = AsyncMock(return_value=[])

    scored_parcels = [
        {
            "pid": "012-345-678",
            "discount_pct": 50.0,
            "lot_area_sqft": 5000,
            "tod_tier": 1,
            "is_undervalued": True,
            "neighborhood": "Downtown",
        },
    ]

    result = await generate_undervalued_alerts(mock_pool, scored_parcels)
    assert result == 0


@pytest.mark.asyncio
async def test_generate_undervalued_alerts_skips_non_undervalued():
    """Parcels with is_undervalued=False should be skipped — no alerts created."""
    from api.intelligence.undervalued_scoring import generate_undervalued_alerts

    mock_pool, mock_conn = _mock_pool_and_conn()

    watchlist_rows = [
        {
            "id": 1,
            "user_id": 10,
            "rule_type": "undervalued_discount",
            "rule_value": "30",
        },
    ]
    mock_conn.fetch = AsyncMock(return_value=watchlist_rows)
    mock_conn.execute = AsyncMock()

    scored_parcels = [
        {
            "pid": "111-222-333",
            "discount_pct": 10.0,
            "lot_area_sqft": 3000,
            "tod_tier": 2,
            "is_undervalued": False,  # not undervalued
            "neighborhood": "Kitsilano",
        },
        {
            "pid": "444-555-666",
            "discount_pct": 5.0,
            "lot_area_sqft": 2000,
            "tod_tier": 3,
            "is_undervalued": False,
            "neighborhood": "Marpole",
        },
    ]

    result = await generate_undervalued_alerts(mock_pool, scored_parcels)

    assert result == 0
    # execute should NOT have been called (no matching parcels)
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_generate_undervalued_alerts_rule_no_match():
    """Undervalued parcel that doesn't match the rule value should not create alert."""
    from api.intelligence.undervalued_scoring import generate_undervalued_alerts

    mock_pool, mock_conn = _mock_pool_and_conn()

    # Rule requires discount >= 50%
    watchlist_rows = [
        {
            "id": 1,
            "user_id": 10,
            "rule_type": "undervalued_discount",
            "rule_value": "50",
        },
    ]
    mock_conn.fetch = AsyncMock(return_value=watchlist_rows)
    mock_conn.execute = AsyncMock()

    scored_parcels = [
        {
            "pid": "012-345-678",
            "discount_pct": 35.0,  # below 50 threshold
            "lot_area_sqft": 5000,
            "tod_tier": 1,
            "is_undervalued": True,
            "neighborhood": "Downtown",
        },
    ]

    result = await generate_undervalued_alerts(mock_pool, scored_parcels)

    assert result == 0
    mock_conn.execute.assert_not_called()
