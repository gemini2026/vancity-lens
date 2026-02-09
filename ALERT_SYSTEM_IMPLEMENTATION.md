# VCL-38 [INTEL-006] Alert System with Watchlist - Implementation Guide

## Overview

This document describes the implementation of the VanCity Lens alert system and watchlist functionality (VCL-38 / INTEL-006). The system allows users to create watchlists with customizable rules and automatically generates alerts when intelligence signals match those rules.

## Components

### 1. Database Migration (`db/015_alert_watchlist.sql`)

Three main tables support the alert system:

#### `watchlists` table
- `id` (PK): Unique identifier
- `user_id` (FK): Reference to users table
- `name`: User-friendly watchlist name
- `description`: Optional watchlist description
- `is_active`: Boolean flag for soft-deletes
- `created_at`, `updated_at`: Timestamps

**Indexes:**
- `idx_watchlists_user_id`: Fast lookup by user
- `idx_watchlists_is_active`: Filter active watchlists
- `idx_watchlists_user_active`: Compound index for common queries

#### `watchlist_rules` table
- `id` (PK): Unique identifier
- `watchlist_id` (FK): Reference to watchlists table
- `rule_type`: Type of rule (neighborhood, address, zoning, signal_type, keyword, severity)
- `rule_value`: The value to match
- `created_at`: Timestamp

**Indexes:**
- `idx_watchlist_rules_watchlist_id`: Retrieve rules for watchlist
- `idx_watchlist_rules_type`: Efficient rule type filtering
- `idx_watchlist_rules_watchlist_type`: Compound index for rule retrieval

#### `alerts` table
- `id` (PK): Unique identifier
- `watchlist_id` (FK): Reference to watchlists table
- `signal_id` (FK): Reference to intelligence_signals table
- `alert_type`: Type of alert (e.g., "signal_match")
- `headline`: Alert headline/title
- `summary`: Optional detailed summary
- `severity`: Severity level (info, low, medium, high, critical)
- `is_read`: Read status
- `created_at`: Alert creation timestamp
- `read_at`: When alert was marked as read

**Indexes:**
- `idx_alerts_watchlist_id`: Retrieve alerts for a watchlist
- `idx_alerts_signal_id`: Look up alerts by signal
- `idx_alerts_is_read`: Filter unread alerts
- `idx_alerts_created_at`: Chronological ordering
- `idx_alerts_watchlist_read`: Compound index for common queries
- `idx_alerts_unique_signal_watchlist`: Unique constraint to prevent duplicates

### 2. Alert Engine (`api/intelligence/alerts.py`)

#### Pydantic Models

**RuleType Enum**
- `NEIGHBORHOOD`: Match by neighborhood name
- `ADDRESS`: Match by address
- `ZONING`: Match by zoning code (from or to)
- `SIGNAL_TYPE`: Match by signal type
- `KEYWORD`: Match keywords in headline/summary
- `SEVERITY`: Match by severity level

**Key Models:**
- `WatchlistRule`: Single rule with type and value
- `WatchlistCreate`: Request model for creating watchlists
- `WatchlistUpdate`: Request model for updating watchlists
- `Watchlist`: Response model with full details and rules
- `Alert`: Response model for individual alerts
- `AlertCount`: Summary of alert counts (total and unread)

#### WatchlistManager Class

Handles all watchlist CRUD operations:

```python
# Create a new watchlist with rules
watchlist = await WatchlistManager.create_watchlist(
    db_pool=pool,
    user_id=user_id,
    name="Downtown Rezoning Monitor",
    description="Track rezoning in downtown Vancouver",
    rules=[
        WatchlistRule(rule_type=RuleType.NEIGHBORHOOD, rule_value="Downtown"),
        WatchlistRule(rule_type=RuleType.SIGNAL_TYPE, rule_value="rezoning_decision"),
    ]
)

# Retrieve all watchlists for a user
watchlists = await WatchlistManager.get_watchlists(db_pool, user_id, active_only=True)

# Get a specific watchlist
watchlist = await WatchlistManager.get_watchlist(db_pool, watchlist_id)

# Update watchlist metadata and/or rules
updated = await WatchlistManager.update_watchlist(
    db_pool, watchlist_id, name="New Name", rules=new_rules
)

# Delete a watchlist (cascades to rules and alerts)
deleted = await WatchlistManager.delete_watchlist(db_pool, watchlist_id)
```

#### AlertEngine Class

Evaluates signals against watchlist rules and manages alerts:

```python
# Evaluate a signal against all active watchlists
# Returns list of created alert IDs
alert_ids = await AlertEngine.evaluate_signal(db_pool, signal)

# Check if signal matches a set of rules (OR logic)
matches = AlertEngine.match_rules(signal, rules)

# Check if signal matches a single rule
matches = AlertEngine.match_rule(signal, rule)

# Create an alert manually
alert_id = await AlertEngine.create_alert(
    db_pool,
    watchlist_id=1,
    signal_id=1,
    alert_type="signal_match",
    headline="Downtown Tower Rezoning Approved",
    summary="City Council approved rezoning...",
    severity="high"
)

# Retrieve alerts for a user
alerts = await AlertEngine.get_alerts(
    db_pool, user_id, unread_only=False, limit=50, offset=0
)

# Mark an alert as read
updated = await AlertEngine.mark_read(db_pool, alert_id)

# Mark all alerts as read for a user
count = await AlertEngine.mark_all_read(db_pool, user_id)

# Get alert counts for a user
counts = await AlertEngine.get_alert_count(db_pool, user_id, unread_only=True)
```

#### Rule Matching Logic

Rules match signals using the following logic:

- **NEIGHBORHOOD**: Case-insensitive substring match in signal neighborhood field
- **ADDRESS**: Case-insensitive substring match in any address in signal addresses list
- **ZONING**: Case-insensitive substring match in zoning_from or zoning_to
- **SIGNAL_TYPE**: Exact match (case-insensitive) of signal type
- **KEYWORD**: Case-insensitive substring match in headline or summary
- **SEVERITY**: Exact match (case-insensitive) of severity level

Multiple rules use OR logic: a signal matches if it matches ANY rule in the watchlist.

### 3. API Endpoints (`api/intelligence/alert_routes.py`)

#### Watchlist Endpoints

**POST /api/v1/intel/watchlists** - Create watchlist
```json
Request:
{
  "name": "Downtown Rezoning Monitor",
  "description": "Track rezoning in downtown Vancouver",
  "rules": [
    {"rule_type": "neighborhood", "rule_value": "Downtown"},
    {"rule_type": "signal_type", "rule_value": "rezoning_decision"}
  ]
}

Response:
{
  "id": 1,
  "user_id": 100,
  "name": "Downtown Rezoning Monitor",
  "description": "Track rezoning in downtown Vancouver",
  "is_active": true,
  "rules": [...],
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

**GET /api/v1/intel/watchlists** - List user's watchlists
- Query params: `active_only=true` (default)
- Returns: Array of Watchlist objects

**GET /api/v1/intel/watchlists/{id}** - Get watchlist details
- Returns: Single Watchlist object with rules
- Validates ownership before returning

**PUT /api/v1/intel/watchlists/{id}** - Update watchlist
- Request: WatchlistUpdate (name, description, rules all optional)
- Returns: Updated Watchlist object
- Validates ownership before updating

**DELETE /api/v1/intel/watchlists/{id}** - Delete watchlist
- Validates ownership before deleting
- Cascades to all associated rules and alerts
- Returns: Success message

#### Alert Endpoints

**GET /api/v1/intel/alerts** - Get user's alerts
- Query params:
  - `unread_only=false` (default): Filter by read status
  - `limit=50` (max 100): Results per page
  - `offset=0`: Pagination offset
- Returns: Array of Alert objects, sorted by created_at DESC

**POST /api/v1/intel/alerts/{id}/read** - Mark alert as read
- Returns: Success message
- Validates ownership via watchlist

**POST /api/v1/intel/alerts/read-all** - Mark all user's alerts as read
- Returns: Success message and count of updated alerts

**GET /api/v1/intel/alerts/count** - Get alert counts
```json
Response:
{
  "total": 10,
  "unread": 3
}
```

### 4. Integration with Routes

The alert routes are integrated into the main intelligence router via:

```python
# In api/intelligence/routes.py
from . import alert_routes
router.include_router(alert_routes.router)
```

All alert endpoints are under `/api/v1/intel/` prefix and require JWT authentication via `get_current_user` dependency.

## Usage Examples

### Create a Watchlist

```python
# Create a watchlist to monitor high-severity rezoning decisions downtown
watchlist = await WatchlistManager.create_watchlist(
    db_pool=pool,
    user_id=user_id,
    name="High Priority Rezonings",
    description="Monitor rezoning decisions with high severity in downtown",
    rules=[
        WatchlistRule(rule_type=RuleType.SIGNAL_TYPE, rule_value="rezoning_decision"),
        WatchlistRule(rule_type=RuleType.SEVERITY, rule_value="high"),
        WatchlistRule(rule_type=RuleType.NEIGHBORHOOD, rule_value="Downtown"),
    ]
)
```

### Signal Evaluation

When a new signal is added to the intelligence layer:

```python
# Extract signal from documents
signal = {
    'id': signal_id,
    'signal_type': 'rezoning_decision',
    'headline': 'Downtown Tower Rezoning Approved',
    'summary': 'City Council approved rezoning...',
    'neighborhood': 'Downtown',
    'severity': 'high',
    'addresses': ['1234 Main Street'],
    'zoning_from': 'RS-1',
    'zoning_to': 'CD-1',
}

# Evaluate against all active watchlists
alert_ids = await AlertEngine.evaluate_signal(db_pool, signal)

# This creates alerts for any matching watchlists
# In the example above, it would match the High Priority Rezonings watchlist
```

### Retrieve and Manage Alerts

```python
# Get unread alerts for user
unread_alerts = await AlertEngine.get_alerts(
    db_pool, user_id, unread_only=True
)

# Mark an alert as read
await AlertEngine.mark_read(db_pool, alert_id)

# Mark all alerts as read
count = await AlertEngine.mark_all_read(db_pool, user_id)

# Get alert summary
counts = await AlertEngine.get_alert_count(db_pool, user_id)
print(f"Total: {counts.total}, Unread: {counts.unread}")
```

## Testing

The implementation includes 53 comprehensive tests covering:

1. **Watchlist CRUD Operations** (11 tests)
   - Create with/without description
   - Create with/without rules
   - Retrieve single and multiple watchlists
   - Update name, description, rules
   - Delete watchlists

2. **Rule Matching** (21 tests)
   - Each rule type tested individually
   - Case-insensitive matching
   - No-match scenarios
   - OR logic with multiple rules

3. **Alert Management** (11 tests)
   - Create alerts
   - Retrieve with pagination and filtering
   - Mark as read/unread
   - Get alert counts

4. **Edge Cases and Error Handling** (7 tests)
   - Missing signal IDs
   - Empty watchlists
   - Database errors
   - Limit validation

5. **Model Validation** (5 tests)
   - Pydantic model creation and validation

6. **Integration Tests** (2 tests)
   - Full workflow: create-update-delete
   - Rule matching combinations

Run tests with:
```bash
python -m pytest tests/test_alerts.py -v
```

## Security Considerations

1. **Authentication**: All endpoints require JWT authentication via `get_current_user`
2. **Ownership Validation**: All watchlist/alert operations verify user ownership
3. **Input Validation**: Pydantic models validate all inputs
4. **SQL Injection**: All queries use parameterized statements via asyncpg
5. **Rate Limiting**: Can be applied via `rate_limit` decorator if needed
6. **Data Privacy**: Users only see their own watchlists and alerts

## Performance Optimization

1. **Indexes**: Strategic indexes on user_id, watchlist_id, is_read, created_at
2. **Unique Constraint**: Prevents duplicate alerts for same signal+watchlist pair
3. **Pagination**: All list endpoints support limit/offset for large datasets
4. **Query Efficiency**: Compound indexes for common filter combinations
5. **Connection Pooling**: Uses asyncpg connection pool (configured in db.py)

## Limitations and Future Enhancements

### Current Limitations
- Rule matching uses simple substring/exact matching (could add regex support)
- No alert scheduling or batching (could combine multiple alerts)
- No notification system (email, Slack, etc.)
- No rule priority or weighting

### Possible Future Enhancements
1. **Advanced Rule Types**
   - Regex pattern matching
   - Numeric thresholds (e.g., "unit_count > 100")
   - Date range rules

2. **Alert Notifications**
   - Email notifications for new alerts
   - Slack/webhook integration
   - Notification preferences per watchlist

3. **Rule Management**
   - Rule priority/weighting
   - Temporary disabling of rules
   - Rule templates for common patterns

4. **Analytics**
   - Alert trend analysis
   - Rule effectiveness metrics
   - User engagement tracking

## File Locations

- **Database**: `/sessions/zen-relaxed-lamport/mnt/bill47/db/015_alert_watchlist.sql`
- **Alert Engine**: `/sessions/zen-relaxed-lamport/mnt/bill47/api/intelligence/alerts.py`
- **API Routes**: `/sessions/zen-relaxed-lamport/mnt/bill47/api/intelligence/alert_routes.py`
- **Tests**: `/sessions/zen-relaxed-lamport/mnt/bill47/tests/test_alerts.py`
- **Integration**: `/sessions/zen-relaxed-lamport/mnt/bill47/api/intelligence/routes.py` (includes alert_routes)

## Deployment Notes

1. Run database migration before deploying:
   ```bash
   psql -U vancity -d vancity_lens -f db/015_alert_watchlist.sql
   ```

2. Ensure JWT authentication is configured in the main app

3. Add signal evaluation to the signal extraction pipeline:
   ```python
   # When creating signals in the extraction pipeline
   alert_ids = await AlertEngine.evaluate_signal(db_pool, signal)
   ```

4. Consider adding background tasks for:
   - Cleaning up old alerts
   - Batch processing signals
   - Alert notifications

## References

- **VCL-38 Specification**: Alert system with watchlist functionality
- **INTEL-006**: Intelligence layer alert integration
- **Pydantic v2**: Used for all model validation
- **AsyncPG**: PostgreSQL async driver for connection pooling
- **FastAPI**: Web framework for REST endpoints
