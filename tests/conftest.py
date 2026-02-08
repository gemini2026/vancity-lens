"""Pytest configuration and fixtures for VanCity Lens intelligence layer tests."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
import httpx
from fastapi.testclient import TestClient


# ────────────────────────────────────────────────────────────────────────────
# Cache Clearing (ensures no cross-test cache pollution from @cached decorator)
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def _clear_cache():
    """Clear the in-memory cache before each test to avoid cross-test pollution."""
    try:
        from api.cache import CacheManager
        manager = CacheManager()
        await manager.clear()
    except Exception:
        pass
    yield
    try:
        from api.cache import CacheManager
        manager = CacheManager()
        await manager.clear()
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
# Database Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool with preset data.

    pool.acquire() must return synchronously (not a coroutine) because
    asyncpg uses ``async with pool.acquire() as conn:`` where acquire()
    returns a PoolAcquireContext (an async-CM), **not** a coroutine.
    """
    pool = AsyncMock()
    pool.acquire = MagicMock()          # ← sync so async-with works

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


# ────────────────────────────────────────────────────────────────────────────
# Document & Content Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_document():
    """Realistic sample document (council meeting page)."""
    return {
        "id": 1,
        "source_type": "council_minutes",
        "source_url": "https://council.vancouver.ca/20240115/regulagenda20240115.htm",
        "title": "City Council Regular Meeting - January 15, 2024",
        "published_date": date(2024, 1, 15),
        "meeting_date": date(2024, 1, 15),
        "raw_text": """CITY OF VANCOUVER
CITY COUNCIL REGULAR MEETING
January 15, 2024

ITEM 1: APPROVAL OF MINUTES
Minutes of the previous meeting were approved.

ITEM 2: REZONING DECISION - 1234 MAIN STREET
Council voted to approve rezoning of 1234 Main Street from RS-1 to CD-1 (123).
Vote: 10-1 in favor.
The site permits a 25-storey mixed-use tower with approximately 300 residential units
and 15,000 square feet of retail space.
Conditions: Public plaza minimum 1500 square metres, 20% rental housing.
Project value estimated at $150 million.

ITEM 3: POLICY UPDATE
City Council approved updates to the Official Development Plan affecting multiple neighborhoods
including Kitsilano, Mount Pleasant, and East Vancouver.

ITEM 4: INFRASTRUCTURE ANNOUNCEMENT
New rapid transit infrastructure planned for Broadway corridor with completion by 2030.
""",
        "text_length": 1200,
        "page_count": 5,
        "file_format": "html",
        "metadata": {"meeting_type": "regular", "agenda_items_count": 4},
        "processed_at": None,
        "scraped_at": datetime(2024, 1, 16, 10, 30)
    }


@pytest.fixture
def sample_chunks():
    """Pre-chunked text samples."""
    return [
        {
            "chunk_text": "ITEM 2: REZONING DECISION - 1234 MAIN STREET\nCouncil voted to approve rezoning of 1234 Main Street from RS-1 to CD-1 (123).\nVote: 10-1 in favor.",
            "chunk_index": 0,
            "section_header": "ITEM 2: REZONING DECISION",
            "approx_token_count": 45
        },
        {
            "chunk_text": "The site permits a 25-storey mixed-use tower with approximately 300 residential units and 15,000 square feet of retail space. Conditions: Public plaza minimum 1500 square metres, 20% rental housing. Project value estimated at $150 million.",
            "chunk_index": 1,
            "section_header": "ITEM 2: REZONING DECISION",
            "approx_token_count": 52
        },
        {
            "chunk_text": "ITEM 3: POLICY UPDATE\nCity Council approved updates to the Official Development Plan affecting Kitsilano, Mount Pleasant, and East Vancouver.",
            "chunk_index": 2,
            "section_header": "ITEM 3: POLICY UPDATE",
            "approx_token_count": 28
        }
    ]


@pytest.fixture
def sample_signals():
    """Pre-extracted intelligence signals."""
    return [
        {
            "id": 1,
            "document_id": 1,
            "signal_type": "rezoning_decision",
            "summary": "City Council approved rezoning of 1234 Main Street from RS-1 to CD-1, permitting a 25-storey mixed-use tower with 300 units and 15,000 sq ft of retail.",
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
            "conditions": ["Public plaza minimum 1500 sq m", "Rental housing 20% of units"],
            "sentiment": "positive_for_development",
            "severity": "high",
            "confidence": 0.95,
            "event_date": date(2024, 1, 15),
            "source_title": "City Council Regular Meeting - January 15, 2024",
            "source_url": "https://council.vancouver.ca/20240115/regulagenda20240115.htm",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15)
        },
        {
            "id": 2,
            "document_id": 1,
            "signal_type": "policy_change",
            "summary": "Official Development Plan updated to affect zoning and density in Kitsilano, Mount Pleasant, and East Vancouver.",
            "headline": "ODP policy updates for multiple neighborhoods",
            "addresses": [],
            "neighborhood": None,
            "decision": None,
            "sentiment": "neutral",
            "severity": "medium",
            "confidence": 0.75,
            "event_date": date(2024, 1, 15),
            "source_title": "City Council Regular Meeting - January 15, 2024",
            "source_url": "https://council.vancouver.ca/20240115/regulagenda20240115.htm",
            "source_type": "council_minutes",
            "source_date": date(2024, 1, 15)
        }
    ]


@pytest.fixture
def sample_council_html():
    """Realistic HTML from a council meeting page."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Council Meeting January 15, 2024</title></head>
    <body>
        <h1>City Council Regular Meeting</h1>
        <p>Date: January 15, 2024</p>

        <h2>Agenda Items</h2>
        <ul>
            <li>ITEM 1: Approval of Minutes</li>
            <li>ITEM 2: Rezoning Decision - 1234 Main Street
                <ul>
                    <li>RS-1 to CD-1 (123)</li>
                    <li>25-storey tower</li>
                    <li>300 units</li>
                    <li>Vote: 10-1 approved</li>
                </ul>
            </li>
            <li>ITEM 3: Infrastructure Updates</li>
        </ul>

        <h2>Documents</h2>
        <a href="/2024/staff_report_2024_01_15.pdf">Staff Report PDF</a>
        <a href="/2024/decisions_2024_01_15.pdf">Decisions PDF</a>
    </body>
    </html>
    """


@pytest.fixture
def sample_rezoning_html():
    """Realistic HTML from a rezoning application page."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Rezoning Application - 5678 Granville Street</title></head>
    <body>
        <h1>Rezoning Application</h1>
        <h2>Application Details</h2>
        <p><strong>Address:</strong> 5678 Granville Street, Vancouver, BC</p>
        <p><strong>Current Zoning:</strong> RM-4</p>
        <p><strong>Proposed Zoning:</strong> CD-1 (456)</p>
        <p><strong>Neighborhood:</strong> Kitsilano</p>

        <h2>Project Summary</h2>
        <p>Proposed development: 12-storey mixed-use building with 180 residential units,
        8,000 sq ft of retail, and 150 parking spaces. Project value: $85 million.</p>

        <h2>Community Opposition</h2>
        <p>Significant community opposition regarding building height and traffic impacts.</p>

        <h2>Documents</h2>
        <a href="/rezoning/5678_granville_application.pdf">Application Details</a>
        <a href="/rezoning/5678_granville_transport_report.pdf">Transportation Report</a>
    </body>
    </html>
    """


# ────────────────────────────────────────────────────────────────────────────
# API Client Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_anthropic_client():
    """Mock for Claude API responses."""
    client = MagicMock()

    # Mock successful signal extraction response
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = """[{
        "signal_type": "rezoning_decision",
        "summary": "Council approved rezoning of 1234 Main Street from RS-1 to CD-1",
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
    }]"""

    client.messages.create = AsyncMock(return_value=mock_response)
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_cohere_client():
    """Mock for Cohere embedding + rerank responses."""
    client = MagicMock()

    # Mock embedding response (1024-dimensional vector for Cohere embed-english-v3.0)
    mock_embedding = [0.1] * 1024
    mock_response = MagicMock()
    mock_response.embeddings = [mock_embedding]

    client.embed = AsyncMock(return_value=mock_response)

    # Mock rerank response
    mock_rerank = MagicMock()
    mock_rerank.results = []
    client.rerank = AsyncMock(return_value=mock_rerank)

    return client


@pytest.fixture
async def api_client():
    """httpx AsyncClient for testing FastAPI endpoints."""
    async with httpx.AsyncClient() as client:
        yield client


# ────────────────────────────────────────────────────────────────────────────
# Data Fixtures for Tests
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def vancouver_addresses():
    """Sample Vancouver addresses for testing."""
    return [
        "1234 Main Street, Vancouver, BC",
        "5678 Granville Street, Vancouver, BC",
        "100 West Hastings Street, Vancouver, BC",
        "2000 Bayswater Street, Vancouver, BC",
        "3000 Commercial Drive, Vancouver, BC"
    ]


@pytest.fixture
def vancouver_neighborhoods():
    """Sample Vancouver neighborhoods."""
    return [
        "Downtown",
        "Kitsilano",
        "Mount Pleasant",
        "West End",
        "East Vancouver",
        "Burnaby",
        "Richmond"
    ]


@pytest.fixture
def vancouver_zoning_codes():
    """Sample Vancouver zoning codes."""
    return [
        "RS-1",
        "RM-4",
        "CD-1",
        "C-1",
        "I-1",
        "I-2",
        "B-1",
        "B-2"
    ]


@pytest.fixture
def sample_chat_request():
    """Sample chat request."""
    return {
        "query": "What rezoning decisions were made in Downtown Vancouver in 2024?",
        "session_id": "test-session-123",
        "neighborhood_filter": "Downtown",
        "date_from": date(2024, 1, 1),
        "date_to": date(2024, 12, 31)
    }


@pytest.fixture
def sample_chat_response():
    """Sample chat response."""
    return {
        "answer": "City Council approved rezoning of 1234 Main Street from RS-1 to CD-1 on January 15, 2024...",
        "citations": [
            {
                "document_title": "City Council Regular Meeting - January 15, 2024",
                "document_url": "https://council.vancouver.ca/20240115/regulagenda20240115.htm",
                "source_type": "council_minutes",
                "published_date": "2024-01-15",
                "relevance_score": 0.92,
                "excerpt": "Council voted to approve rezoning of 1234 Main Street..."
            }
        ],
        "related_signals": [],
        "session_id": "test-session-123"
    }
