"""Tests for undervalued_scoring.py error-handling hardening.

Verifies that DB/infrastructure errors propagate instead of being silently
swallowed, and that per-parcel errors are logged at the correct level.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from api.intelligence.undervalued_scoring import (
    compute_comp_averages,
    generate_undervalued_alerts,
    get_parcel_undervaluation,
    get_top_opportunities,
    score_parcels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(*, side_effect=None, fetch_return=None, fetchrow_return=None):
    """Build a mock asyncpg pool whose acquire() works with ``async with``."""
    pool = AsyncMock()
    conn = AsyncMock()

    if side_effect is not None:
        # Make the connection's methods raise
        conn.fetch = AsyncMock(side_effect=side_effect)
        conn.fetchrow = AsyncMock(side_effect=side_effect)
        conn.execute = AsyncMock(side_effect=side_effect)
    else:
        conn.fetch = AsyncMock(return_value=fetch_return or [])
        conn.fetchrow = AsyncMock(return_value=fetchrow_return)
        conn.execute = AsyncMock()

    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool, conn


def _make_pool_acquire_raises(error):
    """Build a mock pool where acquire().__aenter__ itself raises."""
    pool = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=error)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# Issue 1: compute_comp_averages propagates DB errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compute_comp_averages_propagates_interface_error():
    """asyncpg.InterfaceError must propagate (not be swallowed)."""
    pool, _ = _make_pool(side_effect=asyncpg.InterfaceError("connection lost"))
    with pytest.raises(asyncpg.InterfaceError, match="connection lost"):
        await compute_comp_averages(pool)


@pytest.mark.asyncio
async def test_compute_comp_averages_propagates_connection_error():
    """asyncpg.PostgresConnectionError must propagate."""
    pool = _make_pool_acquire_raises(
        asyncpg.PostgresConnectionError("cannot connect")
    )
    with pytest.raises(asyncpg.PostgresConnectionError):
        await compute_comp_averages(pool)


@pytest.mark.asyncio
async def test_compute_comp_averages_returns_empty_on_no_rows():
    """When the query succeeds but returns no rows, return empty dict."""
    pool, _ = _make_pool(fetch_return=[])
    result = await compute_comp_averages(pool)
    assert result == {}


# ---------------------------------------------------------------------------
# Issue 6: get_top_opportunities propagates DB errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_top_opportunities_propagates_db_error():
    """DB errors in get_top_opportunities must propagate."""
    pool, _ = _make_pool(side_effect=asyncpg.InterfaceError("pool closed"))
    with pytest.raises(asyncpg.InterfaceError, match="pool closed"):
        await get_top_opportunities(pool)


@pytest.mark.asyncio
async def test_get_top_opportunities_returns_empty_on_no_rows():
    """When the query succeeds but returns no rows, return []."""
    pool, _ = _make_pool(fetch_return=[])
    result = await get_top_opportunities(pool)
    assert result == []


# ---------------------------------------------------------------------------
# Issue 7: get_parcel_undervaluation propagates DB errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_parcel_undervaluation_propagates_db_error():
    """DB errors in get_parcel_undervaluation must propagate."""
    pool, _ = _make_pool(side_effect=asyncpg.InterfaceError("timeout"))
    with pytest.raises(asyncpg.InterfaceError, match="timeout"):
        await get_parcel_undervaluation(pool, "PID-001")


@pytest.mark.asyncio
async def test_get_parcel_undervaluation_returns_none_on_no_row():
    """When the query succeeds but the row is None, return None."""
    pool, _ = _make_pool(fetchrow_return=None)
    result = await get_parcel_undervaluation(pool, "PID-001")
    assert result is None


# ---------------------------------------------------------------------------
# Issue 12: generate_undervalued_alerts propagates outer errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_undervalued_alerts_propagates_db_error():
    """DB errors in generate_undervalued_alerts must propagate (no outer catch)."""
    pool, _ = _make_pool(side_effect=asyncpg.InterfaceError("conn reset"))
    with pytest.raises(asyncpg.InterfaceError, match="conn reset"):
        await generate_undervalued_alerts(pool, [])


# ---------------------------------------------------------------------------
# Issue 2: per-parcel errors logged at WARNING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_parcel_error_logged_at_warning(caplog):
    """Per-parcel scoring errors must be logged at WARNING (not DEBUG)."""
    pool, conn = _make_pool()

    # First call to conn.fetch (comp averages) returns data
    # Second call to conn.fetch (parcels) returns a parcel row
    parcel_row = {
        "pid": "TEST-PID",
        "neighborhood": "Downtown",
        "assessed_value": 1_000_000,
        "lot_area_sqm": 500,
        "entitled_fsr": 3.0,
        "buildable_sqft": 5000.0,
    }

    comp_row = {
        "neighborhood": "Downtown",
        "avg_price": 100.0,
        "comp_count": 5,
        "latest_date": "2025-01-01",
    }

    # We need to mock compute_comp_averages to return data so score_parcels
    # proceeds to the parcel loop. Then force an error inside the loop.
    call_count = 0

    async def mock_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # comp averages query
            return [comp_row]
        elif call_count == 2:
            # parcels query
            return [parcel_row]
        return []

    conn.fetch = AsyncMock(side_effect=mock_fetch)
    # Make fetchrow raise to trigger the per-parcel except block
    conn.fetchrow = AsyncMock(side_effect=ValueError("bad data in parcel"))

    with caplog.at_level(logging.WARNING, logger="api.intelligence.undervalued_scoring"):
        # score_parcels has its own outer try/except, so it won't raise for ValueError
        await score_parcels(pool, limit=10)

    # Check that the warning was logged with full error message and type
    warning_messages = [r for r in caplog.records if r.levelno == logging.WARNING]
    found = any(
        "Error scoring parcel TEST-PID" in r.message
        and "ValueError" in r.message
        and "bad data in parcel" in r.message
        for r in warning_messages
    )
    assert found, (
        f"Expected WARNING log with parcel PID, error type, and full message. "
        f"Got: {[r.message for r in warning_messages]}"
    )


# ---------------------------------------------------------------------------
# Issue 3: score_parcels re-raises infrastructure errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_parcels_reraises_interface_error():
    """score_parcels outer except must re-raise asyncpg.InterfaceError."""
    # We need compute_comp_averages to succeed, then the parcels query to fail
    comp_row = {
        "neighborhood": "Downtown",
        "avg_price": 100.0,
        "comp_count": 5,
        "latest_date": "2025-01-01",
    }

    # Build two separate pools: one for comp_averages (succeeds), one for score_parcels (fails)
    # Actually, score_parcels calls compute_comp_averages with the same pool, then acquires again.
    # We can patch compute_comp_averages to return data, then have the pool raise on next acquire.

    pool = AsyncMock()
    call_count = 0

    conn_good = AsyncMock()
    conn_good.fetch = AsyncMock(return_value=[comp_row])

    async def aenter_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First acquire is from compute_comp_averages
            return conn_good
        # Second acquire is from score_parcels main body
        raise asyncpg.InterfaceError("connection pool exhausted")

    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=aenter_side_effect)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(asyncpg.InterfaceError, match="connection pool exhausted"):
        await score_parcels(pool, limit=10)


@pytest.mark.asyncio
async def test_score_parcels_reraises_timeout_error():
    """score_parcels outer except must re-raise asyncio.TimeoutError."""
    comp_row = {
        "neighborhood": "Downtown",
        "avg_price": 100.0,
        "comp_count": 5,
        "latest_date": "2025-01-01",
    }

    pool = AsyncMock()
    call_count = 0

    conn_good = AsyncMock()
    conn_good.fetch = AsyncMock(return_value=[comp_row])

    async def aenter_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return conn_good
        raise asyncio.TimeoutError("query timeout")

    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=aenter_side_effect)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(asyncio.TimeoutError):
        await score_parcels(pool, limit=10)
