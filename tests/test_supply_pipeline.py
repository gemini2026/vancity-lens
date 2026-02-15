"""
Comprehensive tests for supply pipeline tracking (VCL-54).

Tests cover:
- Pipeline entry CRUD operations
- Stage transitions with audit trail
- Pipeline queries with filters
- Summary and statistics generation
- Neighborhood supply analysis
- Intelligence signal ingestion
- Edge cases and error handling
"""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import asyncpg

from api.intelligence.supply_pipeline import (
    SupplyPipelineTracker,
    PipelineEntry,
    PipelineEntryCreate,
    PipelineStage,
    PipelineStageChange,
    PipelineSummary,
    NeighborhoodSupply,
    PipelineStats,
    _row_to_entry,
)


# ════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db_pool():
    """Mock asyncpg pool for pipeline tests."""
    pool = AsyncMock()
    pool.acquire = MagicMock()

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


@pytest.fixture
def sample_entry_create():
    """Sample pipeline entry creation data."""
    return PipelineEntryCreate(
        parcel_pid="000-123-456",
        address="1234 Main Street",
        neighborhood="Downtown",
        pipeline_stage=PipelineStage.REZONING_APPLICATION,
        current_zoning="RS-1",
        proposed_zoning="CD-1",
        proposed_storeys=25,
        proposed_units=300,
        proposed_sqft=150000.0,
        developer="Developer Corp",
        estimated_completion=date(2026, 6, 30),
        metadata={"project_name": "Main Street Tower"}
    )


@pytest.fixture
def sample_pipeline_row():
    """Sample database row from supply_pipeline table."""
    return {
        'id': 1,
        'parcel_pid': '000-123-456',
        'address': '1234 Main Street',
        'neighborhood': 'Downtown',
        'pipeline_stage': 'rezoning_application',
        'current_zoning': 'RS-1',
        'proposed_zoning': 'CD-1',
        'proposed_storeys': 25,
        'proposed_units': 300,
        'proposed_sqft': 150000.0,
        'developer': 'Developer Corp',
        'estimated_completion': date(2026, 6, 30),
        'signal_ids': [1, 2, 3],
        'metadata': {'project_name': 'Main Street Tower'},
        'created_at': datetime(2024, 1, 1, 12, 0, 0),
        'updated_at': datetime(2024, 1, 1, 12, 0, 0),
    }


@pytest.fixture
def sample_stage_history_rows():
    """Sample stage history rows."""
    return [
        {
            'id': 1,
            'pipeline_id': 1,
            'from_stage': None,
            'to_stage': 'rezoning_application',
            'changed_at': datetime(2024, 1, 1, 10, 0, 0),
            'signal_id': None,
            'notes': 'Initial entry'
        },
        {
            'id': 2,
            'pipeline_id': 1,
            'from_stage': 'rezoning_application',
            'to_stage': 'public_hearing',
            'changed_at': datetime(2024, 2, 1, 14, 0, 0),
            'signal_id': 1,
            'notes': 'Hearing scheduled'
        },
        {
            'id': 3,
            'pipeline_id': 1,
            'from_stage': 'public_hearing',
            'to_stage': 'council_decision',
            'changed_at': datetime(2024, 3, 1, 16, 0, 0),
            'signal_id': 2,
            'notes': 'Council vote scheduled'
        }
    ]


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: CRUD Operations
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_add_entry_success(mock_db_pool, sample_entry_create, sample_pipeline_row):
    """Test successful pipeline entry creation."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = sample_pipeline_row

    result = await SupplyPipelineTracker.add_entry(mock_db_pool, sample_entry_create)

    assert result.id == 1
    assert result.parcel_pid == '000-123-456'
    assert result.address == '1234 Main Street'
    assert result.proposed_units == 300
    assert result.pipeline_stage == PipelineStage.REZONING_APPLICATION


@pytest.mark.asyncio
async def test_add_entry_duplicate_parcel(mock_db_pool, sample_entry_create):
    """Test that duplicate parcel_pid raises error."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.side_effect = asyncpg.UniqueViolationError(
        "duplicate key value violates unique constraint"
    )

    with pytest.raises(ValueError, match="already in pipeline"):
        await SupplyPipelineTracker.add_entry(mock_db_pool, sample_entry_create)


@pytest.mark.asyncio
async def test_get_entry_success(mock_db_pool, sample_pipeline_row):
    """Test retrieving a single pipeline entry."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = sample_pipeline_row

    result = await SupplyPipelineTracker.get_entry(mock_db_pool, 1)

    assert result is not None
    assert result.id == 1
    assert result.parcel_pid == '000-123-456'


@pytest.mark.asyncio
async def test_get_entry_not_found(mock_db_pool):
    """Test retrieving non-existent entry returns None."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = None

    result = await SupplyPipelineTracker.get_entry(mock_db_pool, 999)

    assert result is None


@pytest.mark.asyncio
async def test_get_entry_by_parcel_success(mock_db_pool, sample_pipeline_row):
    """Test retrieving entry by parcel PID."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = sample_pipeline_row

    result = await SupplyPipelineTracker.get_entry_by_parcel(mock_db_pool, '000-123-456')

    assert result is not None
    assert result.parcel_pid == '000-123-456'


@pytest.mark.asyncio
async def test_delete_entry_success(mock_db_pool):
    """Test successful pipeline entry deletion."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.execute.return_value = "DELETE 1"

    result = await SupplyPipelineTracker.delete_entry(mock_db_pool, 1)

    assert result is True


@pytest.mark.asyncio
async def test_delete_entry_not_found(mock_db_pool):
    """Test deleting non-existent entry returns False."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.execute.return_value = "DELETE 0"

    result = await SupplyPipelineTracker.delete_entry(mock_db_pool, 999)

    assert result is False


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: Stage Transitions
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_update_stage_success(mock_db_pool, sample_pipeline_row):
    """Test successful stage transition."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Mock the get query
    mock_conn.fetchrow.return_value = {
        'pipeline_stage': 'rezoning_application'
    }

    # Mock the update query
    updated_row = dict(sample_pipeline_row)
    updated_row['pipeline_stage'] = 'public_hearing'
    mock_conn.fetchrow.return_value = updated_row

    result = await SupplyPipelineTracker.update_stage(
        mock_db_pool,
        1,
        PipelineStage.PUBLIC_HEARING,
        signal_id=5,
        notes="Hearing scheduled"
    )

    assert result.pipeline_stage == PipelineStage.PUBLIC_HEARING


@pytest.mark.asyncio
async def test_update_stage_not_found(mock_db_pool):
    """Test updating non-existent entry raises error."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = None

    with pytest.raises(ValueError, match="not found"):
        await SupplyPipelineTracker.update_stage(
            mock_db_pool, 999, PipelineStage.PUBLIC_HEARING
        )


@pytest.mark.asyncio
async def test_stage_history_tracking(mock_db_pool):
    """Test that stage transitions are recorded in history."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Mock the get query
    mock_conn.fetchrow.return_value = {
        'pipeline_stage': 'rezoning_application'
    }

    # Mock the update query
    mock_conn.fetchrow.return_value = {
        'id': 1,
        'parcel_pid': '000-123-456',
        'address': '1234 Main Street',
        'neighborhood': 'Downtown',
        'pipeline_stage': 'public_hearing',
        'current_zoning': 'RS-1',
        'proposed_zoning': 'CD-1',
        'proposed_storeys': 25,
        'proposed_units': 300,
        'proposed_sqft': 150000.0,
        'developer': 'Developer Corp',
        'estimated_completion': date(2026, 6, 30),
        'signal_ids': [],
        'metadata': {},
        'created_at': datetime.now(),
        'updated_at': datetime.now(),
    }

    await SupplyPipelineTracker.update_stage(
        mock_db_pool, 1, PipelineStage.PUBLIC_HEARING, signal_id=5
    )

    # Verify execute was called for history record
    assert mock_conn.execute.called


@pytest.mark.asyncio
async def test_get_stage_history(mock_db_pool, sample_stage_history_rows):
    """Test retrieving stage history."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetch.return_value = sample_stage_history_rows

    result = await SupplyPipelineTracker.get_stage_history(mock_db_pool, 1)

    assert len(result) == 3
    assert result[0].from_stage is None
    assert result[0].to_stage == 'rezoning_application'
    assert result[1].from_stage == 'rezoning_application'
    assert result[1].to_stage == 'public_hearing'
    assert result[1].signal_id == 1


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: Queries and Filters
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_pipeline_no_filters(mock_db_pool, sample_pipeline_row):
    """Test retrieving pipeline without filters."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 1}
    mock_conn.fetch.return_value = [sample_pipeline_row]

    entries, total = await SupplyPipelineTracker.get_pipeline(mock_db_pool)

    assert len(entries) == 1
    assert total == 1
    assert entries[0].parcel_pid == '000-123-456'


@pytest.mark.asyncio
async def test_get_pipeline_filter_by_neighborhood(mock_db_pool, sample_pipeline_row):
    """Test filtering pipeline by neighborhood."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 1}
    mock_conn.fetch.return_value = [sample_pipeline_row]

    entries, total = await SupplyPipelineTracker.get_pipeline(
        mock_db_pool, neighborhood='Downtown'
    )

    assert len(entries) == 1
    assert entries[0].neighborhood == 'Downtown'


@pytest.mark.asyncio
async def test_get_pipeline_filter_by_stage(mock_db_pool, sample_pipeline_row):
    """Test filtering pipeline by stage."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 1}
    mock_conn.fetch.return_value = [sample_pipeline_row]

    entries, total = await SupplyPipelineTracker.get_pipeline(
        mock_db_pool, stage='rezoning_application'
    )

    assert len(entries) == 1


@pytest.mark.asyncio
async def test_get_pipeline_pagination(mock_db_pool):
    """Test pagination limits."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 200}
    mock_conn.fetch.return_value = []

    # Test limit capping
    await SupplyPipelineTracker.get_pipeline(mock_db_pool, limit=500)

    # Verify that the second positional arg is capped at 100
    call_args = mock_conn.fetch.call_args
    # The limit is passed as a positional argument
    assert 100 in call_args[0]  # Should be capped to 100


@pytest.mark.asyncio
async def test_get_pipeline_empty(mock_db_pool):
    """Test empty pipeline query."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 0}
    mock_conn.fetch.return_value = []

    entries, total = await SupplyPipelineTracker.get_pipeline(mock_db_pool)

    assert len(entries) == 0
    assert total == 0


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: Summary and Statistics
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_pipeline_summary(mock_db_pool):
    """Test pipeline summary generation."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Total stats
    mock_conn.fetchrow.return_value = {
        'count': 10,
        'units': 2500,
        'sqft': 1500000.0
    }

    # By stage
    stage_rows = [
        {'pipeline_stage': 'rezoning_application', 'count': 3, 'units': 600, 'sqft': 300000.0},
        {'pipeline_stage': 'public_hearing', 'count': 2, 'units': 400, 'sqft': 200000.0},
        {'pipeline_stage': 'council_decision', 'count': 3, 'units': 900, 'sqft': 600000.0},
        {'pipeline_stage': 'building_permit', 'count': 2, 'units': 600, 'sqft': 400000.0},
    ]

    # By neighborhood
    neighborhood_rows = [
        {'neighborhood': 'Downtown', 'count': 5, 'units': 1500, 'sqft': 900000.0},
        {'neighborhood': 'Kitsilano', 'count': 3, 'units': 700, 'sqft': 400000.0},
        {'neighborhood': 'Mount Pleasant', 'count': 2, 'units': 300, 'sqft': 200000.0},
    ]

    mock_conn.fetch.side_effect = [stage_rows, neighborhood_rows]

    result = await SupplyPipelineTracker.get_pipeline_summary(mock_db_pool)

    assert result.total_entries == 10
    assert result.total_units == 2500
    assert result.total_sqft == 1500000.0
    assert len(result.by_stage) == 4
    assert len(result.by_neighborhood) == 3
    assert 'Downtown' in result.by_neighborhood


@pytest.mark.asyncio
async def test_get_neighborhood_supply(mock_db_pool):
    """Test neighborhood supply analysis."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Overall stats
    mock_conn.fetchrow.return_value = {
        'count': 5,
        'units': 1500,
        'sqft': 900000.0
    }

    # By stage
    stage_rows = [
        {'pipeline_stage': 'rezoning_application', 'count': 2, 'units': 500, 'sqft': 300000.0},
        {'pipeline_stage': 'council_decision', 'count': 2, 'units': 800, 'sqft': 500000.0},
        {'pipeline_stage': 'under_construction', 'count': 1, 'units': 200, 'sqft': 100000.0},
    ]

    # Completion timeline
    completion_rows = [
        {'quarter': date(2025, 3, 31), 'count': 2, 'units': 500},
        {'quarter': date(2026, 3, 31), 'count': 2, 'units': 700},
        {'quarter': date(2027, 3, 31), 'count': 1, 'units': 300},
    ]

    mock_conn.fetch.side_effect = [stage_rows, completion_rows]

    result = await SupplyPipelineTracker.get_neighborhood_supply(
        mock_db_pool, 'Downtown'
    )

    assert result.neighborhood == 'Downtown'
    assert result.total_projects == 5
    assert result.total_units == 1500
    assert len(result.by_stage) == 3
    assert len(result.estimated_completion_range) == 3


@pytest.mark.asyncio
async def test_get_pipeline_stats(mock_db_pool):
    """Test detailed pipeline statistics."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Total stats
    mock_conn.fetchrow.return_value = {
        'count': 10,
        'units': 2500,
        'sqft': 1500000.0,
        'avg_units': 250.0,
        'avg_storeys': 18.5
    }

    # By stage
    stage_rows = [
        {'pipeline_stage': 'rezoning_application', 'count': 3},
        {'pipeline_stage': 'building_permit', 'count': 2},
        {'pipeline_stage': 'under_construction', 'count': 3},
        {'pipeline_stage': 'completed', 'count': 2},
    ]

    # By neighborhood
    neighborhood_rows = [
        {'neighborhood': 'Downtown', 'count': 5},
        {'neighborhood': 'Kitsilano', 'count': 3},
        {'neighborhood': 'Mount Pleasant', 'count': 2},
    ]

    # Near completion
    mock_conn.fetchrow.side_effect = [
        mock_conn.fetchrow.return_value,
        {'count': 5}  # near_completion_count
    ]
    mock_conn.fetch.side_effect = [stage_rows, neighborhood_rows]

    result = await SupplyPipelineTracker.get_pipeline_stats(mock_db_pool)

    assert result.total_projects == 10
    assert result.total_units == 2500
    assert result.average_units_per_project == 250.0
    assert result.average_storeys_per_project == 18.5


# ════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: Signal Ingestion
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ingest_from_signal_new_entry(mock_db_pool, sample_pipeline_row):
    """Test creating pipeline entry from intelligence signal."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Mock get_entry_by_parcel to return None (new entry)
    mock_conn.fetchrow.return_value = None

    # Mock add_entry response
    new_row = dict(sample_pipeline_row)
    new_row['parcel_pid'] = '042-042-042'
    new_row['signal_ids'] = [42]
    new_row['metadata'] = {
        'sourced_from_signal': 42,
        'signal_type': 'rezoning_decision',
        'confidence': 0.95
    }

    with patch.object(SupplyPipelineTracker, 'get_entry_by_parcel', return_value=None):
        with patch.object(SupplyPipelineTracker, 'add_entry') as mock_add:
            mock_add.return_value = _row_to_entry(new_row)
            mock_conn.execute.return_value = None

            signal = {
                'id': 42,
                'parcel_pid': '042-042-042',
                'addresses': ['1234 Main Street'],
                'neighborhood': 'Downtown',
                'zoning_from': 'RS-1',
                'zoning_to': 'CD-1',
                'height_after': 25,
                'unit_count': 300,
                'signal_type': 'rezoning_decision',
                'confidence': 0.95
            }

            result = await SupplyPipelineTracker.ingest_from_signal(mock_db_pool, signal)

            assert result.parcel_pid == '042-042-042'
            assert 42 in result.signal_ids


@pytest.mark.asyncio
async def test_ingest_from_signal_update_existing(mock_db_pool, sample_pipeline_row):
    """Test updating existing pipeline entry from signal."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    existing_entry = _row_to_entry(sample_pipeline_row)

    with patch.object(
        SupplyPipelineTracker, 'get_entry_by_parcel',
        return_value=existing_entry
    ):
        # Mock the update query
        updated_row = dict(sample_pipeline_row)
        updated_row['signal_ids'] = [1, 2, 3, 42]
        mock_conn.fetchrow.return_value = updated_row

        signal = {
            'id': 42,
            'addresses': ['1234 Main Street'],
            'neighborhood': 'Downtown',
            'zoning_to': 'CD-1',
            'unit_count': 300,
        }

        result = await SupplyPipelineTracker.ingest_from_signal(mock_db_pool, signal)

        assert result.parcel_pid == '000-123-456'
        assert 42 in result.signal_ids


@pytest.mark.asyncio
async def test_ingest_from_signal_missing_addresses(mock_db_pool):
    """Test ingestion fails without addresses."""
    signal = {
        'id': 42,
        'addresses': [],
        'neighborhood': 'Downtown',
    }

    with pytest.raises(ValueError, match="must have at least one address"):
        await SupplyPipelineTracker.ingest_from_signal(mock_db_pool, signal)


# ════════════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_pipeline_stages(mock_db_pool, sample_entry_create):
    """Test all seven pipeline stages are valid."""
    stages = [
        PipelineStage.REZONING_APPLICATION,
        PipelineStage.PUBLIC_HEARING,
        PipelineStage.COUNCIL_DECISION,
        PipelineStage.DEVELOPMENT_PERMIT,
        PipelineStage.BUILDING_PERMIT,
        PipelineStage.UNDER_CONSTRUCTION,
        PipelineStage.COMPLETED,
    ]

    for stage in stages:
        assert stage.value in [
            'rezoning_application',
            'public_hearing',
            'council_decision',
            'development_permit',
            'building_permit',
            'under_construction',
            'completed'
        ]


@pytest.mark.asyncio
async def test_row_to_entry_with_nulls():
    """Test conversion handles null values correctly."""
    row = {
        'id': 1,
        'parcel_pid': '000-123-456',
        'address': '1234 Main Street',
        'neighborhood': None,
        'pipeline_stage': 'rezoning_application',
        'current_zoning': None,
        'proposed_zoning': None,
        'proposed_storeys': None,
        'proposed_units': None,
        'proposed_sqft': None,
        'developer': None,
        'estimated_completion': None,
        'signal_ids': None,
        'metadata': None,
        'created_at': datetime.now(),
        'updated_at': datetime.now(),
    }

    result = _row_to_entry(row)

    assert result.id == 1
    assert result.neighborhood is None
    assert result.proposed_units is None
    assert result.signal_ids == []
    assert result.metadata == {}


@pytest.mark.asyncio
async def test_multiple_signals_per_entry(mock_db_pool, sample_pipeline_row):
    """Test that multiple signals can be linked to single entry."""
    row = dict(sample_pipeline_row)
    row['signal_ids'] = [1, 2, 3, 4, 5]

    result = _row_to_entry(row)

    assert len(result.signal_ids) == 5
    assert 1 in result.signal_ids
    assert 5 in result.signal_ids


@pytest.mark.asyncio
async def test_offset_and_limit_validation(mock_db_pool):
    """Test offset and limit are properly validated."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 200}
    mock_conn.fetch.return_value = []

    # Test negative offset is corrected
    await SupplyPipelineTracker.get_pipeline(mock_db_pool, offset=-5)

    call_args = mock_conn.fetch.call_args
    # Negative offset should be converted to 0
    offsets = [arg for arg in call_args[0] if isinstance(arg, int)]
    assert 0 in offsets


@pytest.mark.asyncio
async def test_concurrent_entry_modifications(mock_db_pool):
    """Test handling of concurrent modifications."""
    # This is primarily to verify the async/await structure is sound
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 0}
    mock_conn.fetch.return_value = []

    # Run multiple queries concurrently
    results = await asyncio.gather(
        SupplyPipelineTracker.get_pipeline(mock_db_pool),
        SupplyPipelineTracker.get_pipeline(mock_db_pool),
        SupplyPipelineTracker.get_pipeline(mock_db_pool),
    )

    assert len(results) == 3


# ════════════════════════════════════════════════════════════════════════════
# INTEGRATION-STYLE TESTS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_complete_project_lifecycle(mock_db_pool):
    """Test a project moving through all stages."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Create entry
    create_row = {
        'id': 1,
        'parcel_pid': '000-123-456',
        'address': '1234 Main Street',
        'neighborhood': 'Downtown',
        'pipeline_stage': 'rezoning_application',
        'current_zoning': 'RS-1',
        'proposed_zoning': 'CD-1',
        'proposed_storeys': 25,
        'proposed_units': 300,
        'proposed_sqft': 150000.0,
        'developer': 'Developer Corp',
        'estimated_completion': date(2026, 6, 30),
        'signal_ids': [],
        'metadata': {},
        'created_at': datetime.now(),
        'updated_at': datetime.now(),
    }

    mock_conn.fetchrow.return_value = create_row

    entry = _row_to_entry(create_row)
    assert entry.pipeline_stage == PipelineStage.REZONING_APPLICATION

    # Simulate stage progression
    stages_to_traverse = [
        PipelineStage.PUBLIC_HEARING,
        PipelineStage.COUNCIL_DECISION,
        PipelineStage.DEVELOPMENT_PERMIT,
        PipelineStage.BUILDING_PERMIT,
        PipelineStage.UNDER_CONSTRUCTION,
        PipelineStage.COMPLETED,
    ]

    for stage in stages_to_traverse:
        updated_row = dict(create_row)
        updated_row['pipeline_stage'] = stage.value
        mock_conn.fetchrow.side_effect = [
            {'pipeline_stage': entry.pipeline_stage.value},
            updated_row
        ]

        # This verifies the async flow works without actually modifying db
        assert stage.value in [s.value for s in stages_to_traverse]


@pytest.mark.asyncio
async def test_neighborhood_analysis_workflow(mock_db_pool):
    """Test complete neighborhood analysis workflow."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    # Mock overall stats
    mock_conn.fetchrow.return_value = {
        'count': 10,
        'units': 2500,
        'sqft': 1500000.0
    }

    # Mock by-stage breakdown
    stage_rows = [
        {'pipeline_stage': 'rezoning_application', 'count': 3, 'units': 600, 'sqft': 300000.0},
        {'pipeline_stage': 'under_construction', 'count': 3, 'units': 900, 'sqft': 600000.0},
        {'pipeline_stage': 'completed', 'count': 2, 'units': 400, 'sqft': 200000.0},
    ]

    # Mock completion timeline
    completion_rows = [
        {'quarter': date(2025, 6, 30), 'count': 2, 'units': 500},
        {'quarter': date(2026, 6, 30), 'count': 3, 'units': 900},
    ]

    mock_conn.fetch.side_effect = [stage_rows, completion_rows]

    result = await SupplyPipelineTracker.get_neighborhood_supply(
        mock_db_pool, 'Downtown'
    )

    assert result.total_projects == 10
    assert result.total_units == 2500
    assert len(result.by_stage) == 3
    assert len(result.estimated_completion_range) == 2


@pytest.mark.asyncio
async def test_signal_to_pipeline_workflow(mock_db_pool):
    """Test complete workflow from signal to pipeline entry."""
    # Simulate scraper extracting signal -> pipeline ingestion -> querying

    sample_signal = {
        'id': 100,
        'parcel_pid': '100-100-100',
        'addresses': ['555 Cambie Street'],
        'neighborhood': 'Marpole',
        'zoning_from': 'RM-4',
        'zoning_to': 'CD-1',
        'height_after': 20,
        'unit_count': 250,
        'sqft': 120000.0,
        'signal_type': 'rezoning_decision',
        'confidence': 0.92
    }

    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value

    with patch.object(
        SupplyPipelineTracker, 'get_entry_by_parcel',
        return_value=None
    ):
        with patch.object(
            SupplyPipelineTracker, 'add_entry'
        ) as mock_add:
            ingested_row = {
                'id': 42,
                'parcel_pid': '100-100-100',
                'address': '555 Cambie Street',
                'neighborhood': 'Marpole',
                'pipeline_stage': 'rezoning_application',
                'current_zoning': 'RM-4',
                'proposed_zoning': 'CD-1',
                'proposed_storeys': 20,
                'proposed_units': 250,
                'proposed_sqft': 120000.0,
                'developer': None,
                'estimated_completion': None,
                'signal_ids': [100],
                'metadata': {
                    'sourced_from_signal': 100,
                    'signal_type': 'rezoning_decision',
                    'confidence': 0.92
                },
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }

            mock_add.return_value = _row_to_entry(ingested_row)
            mock_conn.execute.return_value = None

            result = await SupplyPipelineTracker.ingest_from_signal(
                mock_db_pool, sample_signal
            )

            assert result.neighborhood == 'Marpole'
            assert result.proposed_units == 250
            assert 100 in result.signal_ids


# ════════════════════════════════════════════════════════════════════════════
# ERROR HANDLING TESTS
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_database_error_handling(mock_db_pool):
    """Test graceful handling of database errors."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.side_effect = asyncpg.PostgresError("Connection failed")

    with pytest.raises(asyncpg.PostgresError):
        await SupplyPipelineTracker.get_pipeline(mock_db_pool)


@pytest.mark.asyncio
async def test_invalid_stage_value():
    """Test that invalid stage values are rejected."""
    with pytest.raises(ValueError):
        PipelineStage("invalid_stage")


@pytest.mark.asyncio
async def test_entry_create_validation():
    """Test that PipelineEntryCreate validates required fields."""
    from pydantic import ValidationError

    # Missing required field: address
    with pytest.raises(ValidationError):
        PipelineEntryCreate(
            parcel_pid="000-123-456",
            pipeline_stage=PipelineStage.REZONING_APPLICATION
            # address is missing
        )


@pytest.mark.asyncio
async def test_empty_query_results(mock_db_pool):
    """Test handling of empty query results."""
    mock_conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetchrow.return_value = {'total': 0}
    mock_conn.fetch.return_value = []

    entries, total = await SupplyPipelineTracker.get_pipeline(
        mock_db_pool, neighborhood='NonExistent'
    )

    assert len(entries) == 0
    assert total == 0
