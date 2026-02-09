# VCL-42 [INTEL-007] Weekly Digest Generator Implementation

## Overview

The weekly digest generator for VanCity Lens provides users with personalized intelligence summaries based on selected neighborhoods and signal types. Users can subscribe to weekly or daily digests that compile the most important real estate and urban development signals relevant to their interests.

## Components

### 1. Database Migration (`db/016_weekly_digests.sql`)

Creates two main tables and supporting indexes:

#### `digest_subscriptions`
- User digest preferences and configurations
- Stores selected neighborhoods and signal types
- Tracks subscription frequency (daily/weekly)
- Supports enable/disable of subscriptions

**Indexes:**
- `idx_digest_subscriptions_user_id` - for user queries
- `idx_digest_subscriptions_is_active` - for active subscription filtering
- `idx_digest_subscriptions_user_active` - compound index for common queries
- `idx_digest_subscriptions_frequency` - for scheduled digest runs

#### `digest_deliveries`
- Records of generated and delivered digests
- Stores complete digest content as JSONB
- Tracks delivery status (pending/sent/failed)
- Timestamps for creation and sending

**Indexes:**
- `idx_digest_deliveries_subscription_id` - for subscription history
- `idx_digest_deliveries_digest_date` - for date-range queries
- `idx_digest_deliveries_status` - for failed/pending delivery tracking
- `idx_digest_deliveries_unique_subscription_date` - prevents duplicate digests

### 2. Digest Generator (`api/intelligence/digest.py`)

Core business logic for digest generation and scheduling.

#### `DigestGenerator` Class

**Main Methods:**

- `generate_weekly_digest(db_pool, user_id, neighborhoods=None, signal_types=None, date_from=None, date_to=None)`
  - Generates complete digest for specified period and filters
  - Returns `DigestContent` with all digest information
  - Default period: last 7 days

- `_fetch_signals_for_period(db_pool, date_from, date_to, neighborhoods=None, signal_types=None)`
  - Queries signals from `intelligence_signals` table
  - Supports optional filtering by neighborhood and signal type
  - Joins with documents table for source information
  - Returns list of signal dictionaries

- `_summarize_signals(signals)`
  - Groups signals by type, neighborhood, and severity
  - Returns summary counts for each category
  - Used to create statistical overview

- `_generate_highlights(signals)`
  - Selects top 5 most impactful signals
  - Prioritizes by severity, confidence, and recency
  - Returns `DigestHighlight` objects for display

- `_compute_statistics(signals, date_from, date_to)`
  - Calculates period statistics
  - Counts by type, neighborhood, severity
  - Returns `DigestStats` object with comprehensive metrics

- `_format_neighborhood_updates(signals)`
  - Groups signals by neighborhood
  - Extracts top signal and key events for each
  - Returns list of `NeighborhoodUpdate` objects

- `_create_summary_text(total_signals, stats, neighborhoods, highlights)`
  - Generates human-readable summary paragraph
  - Includes key statistics and highlights
  - Used in email/notification body

#### `DigestScheduler` Class

**Main Methods:**

- `get_active_subscriptions(db_pool, frequency=None)`
  - Retrieves all active subscriptions
  - Optional filtering by frequency (daily/weekly)
  - Returns list of `DigestSubscription` objects

- `process_subscription(db_pool, subscription)`
  - Generates digest for single subscription
  - Creates or updates delivery record
  - Handles duplicate prevention via unique constraint
  - Returns `DigestDelivery` object

- `run_digest_cycle(db_pool, frequency=WEEKLY)`
  - Processes all active subscriptions for given frequency
  - Runs in background (async)
  - Handles errors gracefully, continues on failures
  - Returns list of created/updated deliveries

- `mark_delivery_sent(db_pool, delivery_id)`
  - Updates delivery status to "sent"
  - Sets `sent_at` timestamp
  - Used after successful email delivery

- `mark_delivery_failed(db_pool, delivery_id, error_message=None)`
  - Updates delivery status to "failed"
  - Logs error for debugging
  - Can be retried later

### 3. Pydantic Models

All models support JSON serialization for API responses and database storage.

#### `DigestSubscription`
```python
{
  id: int,
  user_id: int,
  neighborhoods: List[str],
  signal_types: List[str],
  frequency: DigestFrequency,  # 'daily' | 'weekly'
  is_active: bool,
  created_at: datetime,
  updated_at: datetime
}
```

#### `DigestContent`
Complete digest with all components:
```python
{
  subscription_id: int,
  digest_date: date,
  date_from: date,
  date_to: date,
  highlights: List[DigestHighlight],
  statistics: DigestStats,
  neighborhood_updates: List[NeighborhoodUpdate],
  summary_text: str,
  generated_at: datetime
}
```

#### `DigestHighlight`
Individual high-impact signal:
```python
{
  signal_id: int,
  headline: str,
  summary: str,
  signal_type: str,
  neighborhood: Optional[str],
  severity: str,
  event_date: Optional[date],
  confidence: float
}
```

#### `DigestStats`
Statistical summary:
```python
{
  total_signals: int,
  by_type: Dict[str, int],
  by_neighborhood: Dict[str, int],
  by_severity: Dict[str, int],
  trend_change_pct: float,
  period_days: int
}
```

#### `NeighborhoodUpdate`
Per-neighborhood summary:
```python
{
  neighborhood: str,
  signal_count: int,
  signal_types: List[str],
  top_signal: Optional[DigestHighlight],
  key_events: List[str],
  severity_distribution: Dict[str, int]
}
```

#### `DigestDelivery`
Delivery record:
```python
{
  id: int,
  subscription_id: int,
  digest_date: date,
  content_json: Dict,
  signal_count: int,
  delivery_status: 'pending' | 'sent' | 'failed',
  created_at: datetime,
  sent_at: Optional[datetime]
}
```

### 4. API Routes (`api/intelligence/digest_routes.py`)

FastAPI routes for user and admin digest management.

#### User Routes (`/api/v1/intel/digests/`)

- **POST** `/subscribe`
  - Create new digest subscription
  - Query params: neighborhoods, signal_types, frequency, is_active
  - Returns: DigestSubscription (201 Created)

- **GET** `/subscriptions`
  - List user's subscriptions
  - Requires authentication
  - Returns: List[DigestSubscription]

- **PUT** `/subscriptions/{subscription_id}`
  - Update subscription (neighborhoods, signal_types, frequency, is_active)
  - Ownership verified before update
  - Returns: DigestSubscription

- **DELETE** `/subscriptions/{subscription_id}`
  - Delete subscription
  - Ownership verified before deletion
  - Returns: 204 No Content

- **GET** `/preview`
  - Preview digest for current period
  - Query params: neighborhoods, signal_types, date_from, date_to
  - Generates digest without saving
  - Returns: DigestContent

- **GET** `/history`
  - Retrieve past digest deliveries
  - Query params: subscription_id, limit, offset
  - Returns: List[DigestDelivery]

#### Admin Routes (`/api/v1/admin/digests/`)

- **POST** `/trigger`
  - Trigger digest generation for all subscriptions
  - Query params: frequency ('weekly'|'daily')
  - Returns: 202 Accepted (async operation)
  - Requires admin privileges

## Usage Examples

### Creating a Subscription

```bash
curl -X POST "http://localhost:8000/api/v1/intel/digests/subscribe" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "neighborhoods": ["Downtown", "Mount Pleasant"],
    "signal_types": ["rezoning_decision", "permit_approval"],
    "frequency": "weekly"
  }'
```

### Previewing a Digest

```bash
curl -X GET "http://localhost:8000/api/v1/intel/digests/preview" \
  -H "Authorization: Bearer <token>" \
  -d "neighborhoods=Downtown&signal_types=rezoning_decision"
```

### Running Digest Cycle (Admin)

```bash
curl -X POST "http://localhost:8000/api/v1/admin/digests/trigger" \
  -H "Authorization: Bearer <admin-token>" \
  -d "frequency=weekly"
```

### Programmatic Usage

```python
from api.intelligence.digest import DigestGenerator, DigestScheduler
from api.db import db

# Generate digest for preview
digest = await DigestGenerator.generate_weekly_digest(
    db.pool,
    user_id=1,
    neighborhoods=["Downtown"],
    signal_types=["rezoning_decision"]
)

# Run scheduled digest cycle
deliveries = await DigestScheduler.run_digest_cycle(
    db.pool,
    frequency=DigestFrequency.WEEKLY
)

# Mark delivery as sent
await DigestScheduler.mark_delivery_sent(db.pool, delivery_id=1)
```

## Testing

Comprehensive test suite with 35 tests covering:

- Signal fetching with various filters
- Signal summarization and grouping
- Highlight generation and prioritization
- Statistics computation
- Neighborhood update formatting
- Complete digest generation
- Subscription management
- Scheduler cycle execution
- Delivery status tracking
- Edge cases (no signals, missing fields, etc.)
- Pydantic model validation

**Run tests:**
```bash
pytest tests/test_digest.py -v
```

## Performance Considerations

### Database Indexes
- Queries optimized with compound indexes for common patterns
- User-level queries include compound indexes (user_id + status)
- Date-range queries benefit from digest_date index
- Unique constraint prevents duplicate digests

### Caching Potential
- Digest content could be cached for public neighborhoods
- Statistics could be cached between runs
- Consider implementing TTL-based cache for preview requests

### Scaling
- Async implementation supports concurrent subscription processing
- Background task queue (Celery) recommended for production digest cycles
- Consider batching neighborhood updates for large result sets
- Delivery status tracking allows retry logic for failed digests

## Integration Points

### With Intelligence Layer
- Queries from `intelligence_signals` table
- Joins with `documents` table for source info
- Uses existing signal models and enums
- Compatible with existing geocoding and embeddings

### With User Authentication
- Authenticated routes use `get_current_user` dependency
- Ownership checks prevent cross-user access
- Admin routes can trigger batch operations

### With Database Pool
- Uses asyncpg connection pool from `api/db.py`
- All queries use parameterized statements (SQL injection protection)
- Proper resource management with async context managers

## Future Enhancements

1. **Email Delivery Integration**
   - Send digests via email service (SendGrid, etc.)
   - Update delivery_status after successful send
   - Track bounce rates and unsubscribes

2. **Smart Filtering**
   - Machine learning to rank highlights based on user behavior
   - Temporal patterns (prefer morning vs evening sending)
   - Personalized neighborhood weighting

3. **Advanced Statistics**
   - Trend analysis with historical comparisons
   - Anomaly detection for unusual signal clusters
   - Predictive signals for upcoming changes

4. **Customization**
   - Custom digest templates
   - Digest frequency flexibility (bi-weekly, monthly)
   - Keyword-based filtering within neighborhoods

5. **Analytics**
   - Digest engagement metrics
   - Read rates by signal type
   - Subscription conversion tracking

## Troubleshooting

### No Signals in Digest
- Check date range (default: last 7 days)
- Verify neighborhoods and signal types are valid
- Ensure intelligence signals have been extracted

### Duplicate Delivery Records
- Unique constraint on (subscription_id, digest_date) prevents true duplicates
- Safe to re-run digest cycle for same date/subscription

### Performance Issues
- Monitor query execution time with `EXPLAIN ANALYZE`
- Consider adding more indexes for specific use cases
- Check database connection pool exhaustion

## Code Quality

- **Type Safety**: Full Pydantic v2 validation and type hints
- **Async**: All I/O operations use async/await
- **Error Handling**: Comprehensive try/except with logging
- **Testing**: 35 tests with good coverage
- **Documentation**: Inline comments and docstrings throughout
- **Python 3.10**: Compatible with `asyncio.wait_for` (no timeout API)

## Files

- `/db/016_weekly_digests.sql` - Database migrations (450+ lines)
- `/api/intelligence/digest.py` - Core implementation (550+ lines)
- `/api/intelligence/digest_routes.py` - API endpoints (450+ lines)
- `/tests/test_digest.py` - Test suite (900+ lines, 35 tests)

## Maintenance

- Review signal extraction quality if digests seem inaccurate
- Monitor digest delivery success rate
- Archive old deliveries periodically (optional)
- Update signal_types and neighborhoods as they change
