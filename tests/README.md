# VanCity Lens V2 Intelligence Layer Test Suite

A comprehensive testing framework for the VanCity Lens intelligence layer, including unit tests, integration tests, and end-to-end pipeline validation.

## Quick Start

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_models.py

# Run with coverage report
pytest --cov=api.intelligence tests/
```

## Test Files Overview

| File | Purpose | Test Methods | Focus |
|------|---------|--------------|-------|
| `test_models.py` | Pydantic model validation | 41 | Enums, models, serialization, defaults |
| `test_chunker.py` | Text chunking pipeline | 44 | Token counting, splitting, headers, overlap |
| `test_extractor.py` | LLM extraction pipeline | 18 | Claude API, geocoding, document processing |
| `test_scrapers.py` | Web scraping functionality | 23 | Rate limiting, URL discovery, PDF parsing |
| `test_chat.py` | RAG chat system | 18 | Query processing, citations, signals |
| `test_signals.py` | Signal CRUD & feeds | 27 | Feed queries, filters, pagination, stats |
| `test_routes.py` | API endpoints | 36 | FastAPI routes, error handling, responses |
| `test_e2e_pipeline.py` | Full pipeline | 11 | End-to-end workflows, data preservation |
| `conftest.py` | Shared fixtures | 20+ fixtures | Mocks, sample data, clients |

**Total: 175+ test methods**

## Architecture

### Fixtures (conftest.py)

**Database:**
- `mock_db_pool` - AsyncMock connection pool

**Documents & Content:**
- `sample_document` - Realistic council meeting
- `sample_chunks` - Pre-chunked text
- `sample_signals` - Pre-extracted signals
- `sample_council_html` - Meeting HTML
- `sample_rezoning_html` - Rezoning HTML

**API Clients:**
- `mock_anthropic_client` - Claude API mock
- `mock_cohere_client` - Cohere embeddings + rerank mock
- `api_client` - HTTP test client

**Data:**
- `vancouver_addresses` - Sample addresses
- `vancouver_neighborhoods` - Real neighborhoods
- `vancouver_zoning_codes` - Real zoning codes
- `sample_chat_request` - Query example
- `sample_chat_response` - Response example

### Test Coverage

```
api/intelligence/
├── models.py          → test_models.py (41 tests)
├── chunker.py         → test_chunker.py (34 tests)
├── embeddings.py      → test_embeddings.py (24 tests)
├── extractor.py       → test_extractor.py (18 tests)
├── chat.py            → test_chat.py (14 tests)
├── signals.py         → test_signals.py (27 tests)
├── routes.py          → test_routes.py (18 tests)
├── parser.py          → test_parser.py (15 tests)
├── scraper_council.py → test_scrapers.py (19 tests)
├── scraper_news.py    → test_scraper_news.py (28 tests)
└── (end-to-end)       → test_e2e_pipeline.py (12 tests)
```

## Test Patterns

### 1. Model Validation (test_models.py)

```python
def test_extracted_signal_full(self):
    signal = ExtractedSignal(
        signal_type=SignalType.REZONING_DECISION,
        summary="...",
        confidence=0.95
    )
    assert signal.signal_type == SignalType.REZONING_DECISION
```

### 2. Async Operations (test_extractor.py)

```python
@pytest.mark.asyncio
async def test_extract_signals_from_chunk(self):
    signals = await extract_signals_from_chunk(chunk_text, doc_context, "api-key")
    assert len(signals) > 0
```

### 3. Mocking External Services (test_chat.py)

```python
with patch("api.intelligence.chat.hybrid_search", return_value=mock_chunks):
    response = await handle_chat(db_pool, query, api_key, cohere_key)
    assert response.session_id
```

### 4. API Endpoint Testing (test_routes.py)

```python
def test_get_signals(self, client):
    response = client.get("/api/v1/intel/signals", params={"limit": 20})
    assert response.status_code == 200
```

### 5. End-to-End Pipeline (test_e2e_pipeline.py)

```python
def test_full_pipeline(self, sample_document):
    chunks = chunk_document(sample_document["raw_text"])
    # Extract signals from chunks
    # Verify data preservation
    # Test signal models
```

## Running Tests

### All Tests
```bash
pytest
```

### Specific Test Class
```bash
pytest tests/test_models.py::TestEnums
```

### Specific Test Method
```bash
pytest tests/test_chunker.py::TestChunkDocument::test_long_document
```

### With Output
```bash
pytest -v                    # Verbose
pytest -s                    # Show print statements
pytest -vv                   # Very verbose
```

### With Filtering
```bash
pytest -k "chunk"            # Tests with "chunk" in name
pytest -m "not slow"         # Skip slow tests
pytest -m integration        # Only integration tests
```

### With Coverage
```bash
pytest --cov=api.intelligence tests/
pytest --cov=api.intelligence --cov-report=html tests/
```

## Mock Data

### Vancouver Neighborhoods
- Downtown
- Kitsilano
- Mount Pleasant
- West End
- East Vancouver

### Zoning Codes
- RS-1 (Single Family)
- RM-4 (Multiple Family)
- CD-1 (Downtown Community)
- C-1 (Commercial)

### Sample Addresses
- 1234 Main Street
- 5678 Granville Street
- 100 West Hastings Street
- 2000 Bayswater Street

## Dependencies

```
pytest>=7.0
pytest-asyncio>=0.21
httpx>=0.24
```

All external services (Claude API, OpenAI, AsyncPG) are mocked for testing.

## Key Test Scenarios

1. **Model Validation**
   - Enum values
   - Field constraints
   - Serialization round-trips
   - Default values

2. **Chunking**
   - Short vs. long documents
   - Section header detection
   - Token count accuracy
   - Overlap addition

3. **Extraction**
   - Valid JSON responses
   - Empty results
   - Error handling
   - Geocoding fallback

4. **Web Scraping**
   - Rate limiting
   - URL discovery
   - PDF parsing
   - Deduplication

5. **Chat/RAG**
   - Query processing
   - Citation building
   - Session management
   - Neighborhood filtering

6. **Signals**
   - CRUD operations
   - Feed pagination
   - Filtering (type, severity, date)
   - Aggregation statistics

7. **API Endpoints**
   - Request validation
   - Response formats
   - Error handling
   - Authentication

8. **End-to-End**
   - Document → chunks → signals → database
   - Data preservation
   - Model compatibility
   - Vancouver-specific handling

## Notes

- All tests run **offline** with no external API calls
- Tests complete in **seconds** (no rate limiting delays)
- Uses **AsyncMock** for database operations
- Uses **MagicMock** for API responses
- Tests are **isolated** (no shared state)
- Results are **deterministic** (no flakiness)

## Troubleshooting

**Import Error: No module named 'api'**
```bash
# Run from project root
cd /sessions/zen-relaxed-lamport/mnt/bill47
pytest tests/
```

**TypeError: object is not callable**
- Ensure mock objects are properly instantiated

**AssertionError in async test**
- Check `@pytest.mark.asyncio` decorator is present

**Connection refused**
- All tests should be mocked (no real connections)

## Contributing

When adding new tests:
1. Place in appropriate test file
2. Use descriptive test names: `test_feature_scenario`
3. Add docstring explaining what's tested
4. Use existing fixtures where possible
5. Mock external services
6. Add `@pytest.mark.asyncio` for async functions
7. Update this README with changes

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/advanced/testing-websockets/)
