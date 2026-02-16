"""
Tests for report_generator.py silent failure hardening (Task 5).

Verifies that:
- Section build failures log at ERROR level with exc_info
- Entitlement fetch failure logs at ERROR
- Data currency inner loop logs instead of silently passing
- LLM fallback appends "(Auto-generated summary)"
- Due diligence evidence failure logs at ERROR with exc_info
"""

import logging
import pytest
import asyncpg
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from api.report_generator import ReportGenerator, ParcelReport


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def make_mock_pool(conn):
    """Create a mock asyncpg pool that properly supports `async with pool.acquire() as conn`."""
    pool = MagicMock()

    @asynccontextmanager
    async def mock_acquire():
        yield conn

    pool.acquire = mock_acquire
    return pool


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def generator():
    """Create a ReportGenerator instance."""
    return ReportGenerator()


@pytest.fixture
def minimal_parcel_data():
    """Minimal ParcelReport for testing section failures."""
    return ParcelReport(
        pid="999-999-999",
        civic_address="123 Test St, Vancouver",
        current_zoning="RS-1",
        proposed_zoning=None,
        lot_area_sqm=Decimal("400"),
        lot_area_sqft=Decimal("4305.56"),
        buildable_sqft=Decimal("8611.12"),
        estimated_land_value=1000000,
        assessed_value=900000,
        asking_price=None,
        value_delta=100000,
        generated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool with proper async context manager support."""
    conn = AsyncMock()
    pool = make_mock_pool(conn)
    return pool


# ────────────────────────────────────────────────────────────────────────────
# Issue 8: Section build failures log at ERROR with exc_info
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_environmental_section_failure_logs_error(
    generator, minimal_parcel_data, mock_db_pool, caplog
):
    """When _build_environmental_section raises, ERROR is logged with exc_info."""
    with patch.object(generator, "_fetch_parcel_data", return_value=minimal_parcel_data), \
         patch.object(generator, "_build_header_section"), \
         patch.object(generator, "_build_executive_summary", new_callable=AsyncMock), \
         patch.object(generator, "_build_title_ownership"), \
         patch.object(generator, "_build_entitlement_analysis"), \
         patch.object(generator, "_build_environmental_section", new_callable=AsyncMock, side_effect=RuntimeError("env db down")), \
         patch.object(generator, "_render_unavailable_section") as mock_render, \
         patch.object(generator, "_build_heritage_section"), \
         patch.object(generator, "_build_before_after_section"), \
         patch.object(generator, "_build_nearby_development", new_callable=AsyncMock), \
         patch.object(generator, "_build_market_context", new_callable=AsyncMock), \
         patch.object(generator, "_build_demographic_profile", new_callable=AsyncMock), \
         patch.object(generator, "_build_red_flags_summary"), \
         patch.object(generator, "_build_data_currency", new_callable=AsyncMock), \
         patch.object(generator, "_build_pro_forma"), \
         patch.object(generator, "_build_hbu_section"), \
         patch.object(generator, "_build_due_diligence"), \
         patch.object(generator, "_build_sources"), \
         patch.object(generator, "_build_footer"):

        with caplog.at_level(logging.ERROR, logger="api.report_generator"):
            await generator.generate_parcel_report(mock_db_pool, "999-999-999")

        # Verify ERROR log with exc_info
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "Environmental" in r.message]
        assert len(error_records) >= 1, "Expected ERROR log for Environmental section failure"
        assert error_records[0].exc_info is not None, "Expected exc_info to be set"
        assert "999-999-999" in error_records[0].message

        # Verify graceful degradation still works (render_unavailable_section was called)
        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert call_args[0][1] == "Environmental"
        assert call_args[0][2] == "Environmental data source"
        assert call_args[0][3] == "env db down"


@pytest.mark.asyncio
async def test_all_section_failures_log_error_with_exc_info(
    generator, minimal_parcel_data, mock_db_pool, caplog
):
    """All five section try/except blocks log at ERROR with exc_info when they fail."""
    section_errors = {
        "_build_environmental_section": "env error",
        "_build_nearby_development": "dev error",
        "_build_market_context": "market error",
        "_build_demographic_profile": "demo error",
        "_build_data_currency": "currency error",
    }

    patches = {}
    for method_name, error_msg in section_errors.items():
        patches[method_name] = patch.object(
            generator, method_name,
            new_callable=AsyncMock,
            side_effect=RuntimeError(error_msg),
        )

    safe_methods = [
        "_fetch_parcel_data", "_build_header_section", "_build_executive_summary",
        "_build_title_ownership", "_build_entitlement_analysis",
        "_build_heritage_section", "_build_before_after_section",
        "_build_red_flags_summary", "_build_pro_forma", "_build_hbu_section",
        "_build_due_diligence", "_build_sources", "_build_footer",
    ]
    safe_patches = {}
    for method_name in safe_methods:
        if method_name == "_fetch_parcel_data":
            safe_patches[method_name] = patch.object(
                generator, method_name, return_value=minimal_parcel_data
            )
        elif method_name == "_build_executive_summary":
            safe_patches[method_name] = patch.object(
                generator, method_name, new_callable=AsyncMock
            )
        else:
            safe_patches[method_name] = patch.object(generator, method_name)

    with patch.object(generator, "_render_unavailable_section"):
        entered = {}
        for name, p in {**patches, **safe_patches}.items():
            entered[name] = p.__enter__()

        try:
            with caplog.at_level(logging.ERROR, logger="api.report_generator"):
                await generator.generate_parcel_report(mock_db_pool, "999-999-999")

            error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
            section_names = ["Environmental", "Nearby Development", "Market Context", "Demographic Profile", "Data Currency"]
            for section_name in section_names:
                matching = [r for r in error_records if section_name in r.message]
                assert len(matching) >= 1, f"Expected ERROR log for {section_name} section failure"
                assert matching[0].exc_info is not None, f"Expected exc_info for {section_name}"
        finally:
            for name, p in {**patches, **safe_patches}.items():
                p.__exit__(None, None, None)


# ────────────────────────────────────────────────────────────────────────────
# Issue 9: Entitlement fetch failure logs at ERROR
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entitlement_fetch_failure_logs_error(generator, caplog):
    """When entitlement query raises, ERROR is logged with exc_info."""
    mock_conn = AsyncMock()

    parcel_row = {
        "pid": "111-222-333",
        "civic_address": "Test St",
        "current_zoning": "RS-1",
        "lot_area_sqm": Decimal("500"),
        "geo_local_area": "Downtown",
        "created_at": datetime.now(timezone.utc),
    }

    call_count = 0

    async def mock_fetchrow(query, *args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return parcel_row
        elif call_count == 2:
            # Entitlement fetch — simulate a Postgres error (caught at ERROR level)
            raise asyncpg.PostgresError("entitlement table error")
        else:
            return None

    mock_conn.fetchrow = mock_fetchrow
    mock_conn.fetch = AsyncMock(return_value=[])

    mock_pool = make_mock_pool(mock_conn)

    with caplog.at_level(logging.ERROR, logger="api.report_generator"):
        try:
            await generator._fetch_parcel_data(mock_pool, "111-222-333")
        except Exception:
            pass  # May fail on later queries, that's fine

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "entitlement" in r.message.lower()]
    assert len(error_records) >= 1, "Expected ERROR log for entitlement fetch failure"
    assert error_records[0].exc_info is not None, "Expected exc_info to be set"
    assert "111-222-333" in error_records[0].message


# ────────────────────────────────────────────────────────────────────────────
# Issue 10: Data currency inner loop logs instead of silently passing
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_currency_inner_loop_logs_on_failure(generator, caplog):
    """Data currency inner loop exception logs at DEBUG level instead of pass."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)

    mock_conn = AsyncMock()
    # Make every inner fetchrow raise
    mock_conn.fetchrow = AsyncMock(side_effect=RuntimeError("table does not exist"))

    mock_pool = make_mock_pool(mock_conn)

    with caplog.at_level(logging.DEBUG, logger="api.report_generator"):
        await generator._build_data_currency(pdf, mock_pool)

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG and "Data currency query failed for" in r.message]
    assert len(debug_records) >= 1, "Expected DEBUG log for data currency query failure"
    # Should contain the label of the data source
    all_messages = " ".join(r.message for r in debug_records)
    assert "BC Assessment" in all_messages or "StatsCan" in all_messages or "CMHC" in all_messages


# ────────────────────────────────────────────────────────────────────────────
# Issue 20: LLM fallback appends "(Auto-generated summary)"
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_fallback_appends_auto_generated_note(generator, minimal_parcel_data, caplog):
    """When LLM enhancement fails, summary text includes '(Auto-generated summary)'."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)

    # Mock the LLM call to fail
    with patch("api.intelligence.llm_backend.generate_chat", new_callable=AsyncMock, side_effect=RuntimeError("LLM unavailable")):
        with caplog.at_level(logging.WARNING, logger="api.report_generator"):
            # Capture what gets passed to pdf.multi_cell
            original_multi_cell = pdf.multi_cell
            captured_texts = []

            def capturing_multi_cell(w, h, txt, *args, **kwargs):
                captured_texts.append(txt)
                return original_multi_cell(w, h, txt, *args, **kwargs)

            pdf.multi_cell = capturing_multi_cell
            await generator._build_executive_summary(pdf, minimal_parcel_data)

    # Check that the summary contains the auto-generated note
    assert len(captured_texts) >= 1, "Expected at least one multi_cell call"
    summary_text = captured_texts[0]
    assert "(Auto-generated summary)" in summary_text, \
        f"Expected '(Auto-generated summary)' in fallback summary, got: {summary_text[:200]}"


# ────────────────────────────────────────────────────────────────────────────
# Issue 21: due_diligence_evidence failure logs at ERROR with exc_info
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_due_diligence_evidence_failure_logs_error(generator, caplog):
    """Due diligence evidence failure logs at ERROR with exc_info (not WARNING)."""
    mock_conn = AsyncMock()

    parcel_row = {
        "pid": "444-555-666",
        "civic_address": "456 Test Ave",
        "current_zoning": "C-2",
        "lot_area_sqm": Decimal("600"),
        "geo_local_area": "Kitsilano",
        "created_at": datetime.now(timezone.utc),
    }

    entitlement_row = {
        "current_storeys": 4,
        "entitled_storeys": 8,
        "current_fsr": Decimal("2.0"),
        "entitled_fsr": Decimal("3.5"),
        "estimated_land_value": 1500000,
        "assessed_value": 1200000,
        "asking_price": 1800000,
        "value_delta": 300000,
    }

    call_count = 0

    async def mock_fetchrow(query, *args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return parcel_row
        elif call_count == 2:
            return entitlement_row
        return None

    mock_conn.fetchrow = mock_fetchrow
    mock_conn.fetch = AsyncMock(return_value=[])

    mock_pool = make_mock_pool(mock_conn)

    # Make build_due_diligence_evidence raise
    with patch("api.report_generator.build_due_diligence_evidence", new_callable=AsyncMock, side_effect=RuntimeError("evidence db timeout")):
        with caplog.at_level(logging.ERROR, logger="api.report_generator"):
            try:
                await generator._fetch_parcel_data(mock_pool, "444-555-666")
            except Exception:
                pass

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "due diligence evidence" in r.message.lower()]
    assert len(error_records) >= 1, "Expected ERROR log for due diligence evidence failure"
    assert error_records[0].exc_info is not None, "Expected exc_info to be set"
    assert "444-555-666" in error_records[0].message

    # Verify no WARNING-level log for this (it was upgraded to ERROR)
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and "due diligence" in r.message.lower()]
    assert len(warning_records) == 0, "Due diligence evidence failure should log at ERROR, not WARNING"
