# VCL-78 [BIZ-002] Tiered Subscription Model Implementation

## Overview

Complete implementation of a tiered subscription model for VanCity Lens with support for multiple subscription tiers, usage tracking, and rate limiting.

## Files Created

### 1. Database Migration
**File**: `/sessions/zen-relaxed-lamport/mnt/bill47/db/019_subscriptions.sql`

Creates three main tables:

#### subscription_tiers
- **Purpose**: Define available subscription tiers with their features and limits
- **Key Columns**:
  - `name` (UNIQUE): Tier identifier (free, starter, professional, enterprise)
  - `display_name`: User-facing tier name
  - `price_monthly` / `price_annual`: Pricing for paid tiers (NULL for enterprise)
  - `max_watchlists`: Maximum watchlist count
  - `max_api_calls_daily`: Daily API call limit
  - `max_signals_per_query`: Signals per query limit
  - `features` (JSONB): Feature flags (chat_enabled, digest_enabled, export_enabled, priority_support, custom_branding)
  - `is_active`: Soft delete flag

#### user_subscriptions
- **Purpose**: Track each user's current subscription
- **Key Columns**:
  - `user_id` (UNIQUE FK): One subscription per user
  - `tier_id` (FK): Reference to subscription_tiers
  - `status`: Subscription state (active/cancelled/expired/trial)
  - `trial_ends_at`: Trial period end date
  - `current_period_start` / `current_period_end`: Billing period dates
  - `cancel_at_period_end`: Flag for cancellations effective next period
  - `created_at` / `updated_at`: Audit timestamps

#### usage_tracking
- **Purpose**: Track daily usage metrics per user
- **Key Columns**:
  - `user_id` / `usage_date` (UNIQUE composite): One record per user per day
  - `api_calls`: API call count
  - `signals_queried`: Signals query count
  - `chat_messages`: Chat message count
  - `exports`: Export count

**Indexes**: Optimized for:
- User subscription lookup (user_id)
- Tier distribution queries (tier_id)
- Status filtering (status)
- Period renewal checks (current_period_end)
- Trial expiry checks (trial_ends_at)
- Daily usage aggregation (user_id, usage_date)

**Seed Data**: Inserts 4 tiers:
1. **Free**: 1 watchlist, 100 API calls/day, 10 signals/query
2. **Starter**: 5 watchlists, 1,000 API calls/day, 50 signals/query, chat + export enabled
3. **Professional**: 20 watchlists, 10,000 API calls/day, 200 signals/query, all features enabled
4. **Enterprise**: Unlimited, custom features

### 2. Core Subscription Module
**File**: `/sessions/zen-relaxed-lamport/mnt/bill47/api/subscriptions.py`

**Line Count**: ~680 lines

**Components**:

#### Enums
- `SubscriptionTier`: Available tiers (FREE, STARTER, PROFESSIONAL, ENTERPRISE)
- `SubscriptionStatus`: Subscription states (ACTIVE, CANCELLED, EXPIRED, TRIAL)

#### Pydantic Models
- `TierInfo`: Tier information (id, name, display_name, pricing, limits, features)
- `UserSubscription`: User's subscription details
- `UsageStats`: Daily usage metrics
- `UsageLimits`: Tier limits
- `SubscriptionStatusResponse`: Complete subscription status response

#### SubscriptionManager Class
Static methods for all subscription operations:

**Tier Management**:
- `get_tiers()`: Fetch all active tiers
- `get_tier(tier_name)`: Fetch specific tier

**Subscription Operations**:
- `get_user_subscription(user_id)`: Get user's subscription
- `create_subscription(user_id, tier_name, trial_days=14)`: Create new subscription
- `upgrade_subscription(user_id, new_tier)`: Upgrade to higher tier
- `downgrade_subscription(user_id, new_tier)`: Downgrade to lower tier
- `cancel_subscription(user_id)`: Mark for cancellation at period end
- `reactivate_subscription(user_id)`: Reactivate cancelled subscription

**Usage Tracking**:
- `check_limit(user_id, limit_type)`: Check if user is within daily limit
- `track_usage(user_id, usage_type, count=1)`: Record usage (auto-creates daily record)
- `get_usage(user_id, date=None)`: Get usage for specific date (defaults to today)
- `get_usage_summary(user_id, days=30)`: Get aggregated usage over period

**Usage Types**: api_calls, signals_queried, chat_messages, exports

#### FastAPI Dependencies
- `require_tier(min_tier: str)`: Factory for tier requirement checks
  - Usage: `@app.get("/api/v1/signals", Depends(require_tier("starter")(db_pool)))`
  - Returns 403 if user lacks minimum tier

- `check_rate_limit(limit_type: str)`: Factory for rate limit checks
  - Usage: `@app.post("/api/v1/signals/query", Depends(check_rate_limit("signals_queried")(db_pool)))`
  - Returns 429 if limit exceeded
  - Works with enterprise (unlimited)

### 3. API Routes
**File**: `/sessions/zen-relaxed-lamport/mnt/bill47/api/subscription_routes.py`

**Line Count**: ~350 lines

#### Public Endpoints
Prefix: `/api/v1/subscriptions`

- **GET /tiers**
  - List all active subscription tiers
  - Returns: `List[TierInfo]`

- **GET /current**
  - Get current user's subscription with usage and limits
  - Requires: User authentication
  - Returns: `SubscriptionStatusResponse`

- **POST /subscribe**
  - Subscribe user to a tier
  - Params: `tier_name` (str), `trial_days` (int, default 14)
  - Returns: `UserSubscription`
  - Errors: 400 (tier not found, already subscribed), 500

- **POST /upgrade**
  - Upgrade to higher tier
  - Params: `new_tier` (str)
  - Returns: `UserSubscription`
  - Errors: 400 (invalid tier, no subscription), 500

- **POST /downgrade**
  - Downgrade to lower tier
  - Params: `new_tier` (str)
  - Returns: `UserSubscription`
  - Errors: 400 (invalid tier, no subscription), 500

- **POST /cancel**
  - Cancel subscription (effective at period end)
  - Returns: `UserSubscription`
  - Errors: 400 (no subscription), 500

- **POST /reactivate**
  - Reactivate cancelled subscription
  - Returns: `UserSubscription`
  - Errors: 400 (no subscription), 500

- **GET /usage**
  - Get usage for specific date (defaults to today)
  - Params: `date` (str, optional, YYYY-MM-DD format)
  - Returns: `UsageStats`
  - Errors: 400 (invalid date), 500

- **GET /usage/summary**
  - Get aggregated usage summary
  - Params: `days` (int, default 30, max 365)
  - Returns: `Dict` with total_api_calls, total_signals_queried, total_chat_messages, total_exports, days_active, period_days
  - Errors: 400 (invalid days), 500

#### Admin Endpoints
Prefix: `/api/v1/admin`

- **GET /subscriptions/stats**
  - Get subscription distribution statistics (admin only)
  - Returns: `Dict` with:
    - `total_subscribers`: Total active subscribers
    - `active_subscriptions`: Active subscriptions
    - `trial_subscriptions`: Subscriptions in trial
    - `cancellations_pending`: Subscriptions pending cancellation
    - `distribution_by_tier`: List of tier distributions with user counts
  - Errors: 403 (not admin), 500

### 4. Comprehensive Tests
**File**: `/sessions/zen-relaxed-lamport/mnt/bill47/tests/test_subscriptions.py`

**Line Count**: ~800+ lines
**Test Count**: 45+ tests

#### Test Coverage

**Tier Listing** (3 tests):
- Successful tier retrieval
- Specific tier lookup
- Non-existent tier handling

**Subscription Creation** (4 tests):
- Success with trial
- Invalid tier rejection
- Duplicate subscription prevention
- No-trial creation

**Upgrade/Downgrade** (6 tests):
- Successful upgrades
- Invalid tier handling
- Not-found handling
- Successful downgrades

**Cancellation/Reactivation** (4 tests):
- Successful cancellation
- Not-found handling
- Successful reactivation
- Reactivation not-found

**Usage Tracking** (8 tests):
- API call tracking
- Invalid usage type handling
- No-subscription validation
- Successful usage retrieval
- No-record handling
- Usage summary retrieval
- Multi-type tracking

**Rate Limiting** (5 tests):
- Within limit checks
- At-limit detection
- Enterprise unlimited
- Invalid limit type
- No-subscription handling

**Dependencies** (4 tests):
- Tier requirement sufficient
- Tier requirement insufficient
- Tier requirement no-subscription
- Rate limit checks (within, exceeded)

**Edge Cases** (6 tests):
- User subscription retrieval
- Tier and status enums
- Pydantic model validation
- Multiple concurrent operations

**Models** (5 tests):
- TierInfo validation
- UserSubscription validation
- UsageStats validation
- UsageLimits validation
- SubscriptionStatusResponse validation

## Architecture Decisions

### Database Design
1. **Unique constraint on user_id in user_subscriptions**: Ensures one active subscription per user
2. **JSONB features column**: Allows flexible feature flags without schema changes
3. **Composite index on (user_id, usage_date)**: Fast daily usage lookups
4. **Status field in user_subscriptions**: Enables transition tracking
5. **Separate usage_tracking table**: Denormalized for analytics/reporting

### API Design
1. **Factory pattern for dependencies**: Reusable tier checks and rate limiting
2. **Explicit trial_days parameter**: Allows flexibility (0 = no trial)
3. **cancel_at_period_end flag**: Provides graceful cancellation
4. **Admin routes separate**: Clear authorization boundaries
5. **Comprehensive error codes**: Specific HTTP status codes (403, 429, 404)

### Error Handling
- **400 Bad Request**: Invalid input, tier not found, state conflicts
- **403 Forbidden**: Insufficient tier, admin-only endpoints, inactive accounts
- **404 Not Found**: Subscription not found
- **429 Too Many Requests**: Rate limits exceeded
- **500 Internal Server Error**: Database errors, unexpected failures

## Integration Guide

### 1. Register Routes with FastAPI App

In your main FastAPI application:

```python
from api.subscription_routes import router, admin_router

app.include_router(router)
app.include_router(admin_router)
```

### 2. Use Tier Requirements in Routes

```python
from api.subscriptions import require_tier
from api.user_auth import get_current_user

@app.post("/api/v1/signals/query")
async def query_signals(
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(require_tier("starter")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    # Track usage
    await SubscriptionManager.track_usage(db_pool, user["id"], "signals_queried", 1)
    return {"signals": [...]}
```

### 3. Use Rate Limiting in Routes

```python
from api.subscriptions import check_rate_limit

@app.post("/api/v1/api-call")
async def make_api_call(
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(check_rate_limit("api_calls")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    # API call logic
    await SubscriptionManager.track_usage(db_pool, user["id"], "api_calls", 1)
    return {"result": "..."}
```

### 4. Initialize Database

Run the migration:

```bash
psql $DATABASE_URL < db/019_subscriptions.sql
```

## Usage Examples

### Subscribe User to Free Tier

```python
subscription = await SubscriptionManager.create_subscription(
    db_pool,
    user_id=100,
    tier_name="free",
    trial_days=14
)
```

### Upgrade to Professional

```python
subscription = await SubscriptionManager.upgrade_subscription(
    db_pool,
    user_id=100,
    new_tier="professional"
)
```

### Track API Call Usage

```python
await SubscriptionManager.track_usage(
    db_pool,
    user_id=100,
    usage_type="api_calls",
    count=1
)
```

### Check Rate Limit

```python
within_limit = await SubscriptionManager.check_limit(
    db_pool,
    user_id=100,
    limit_type="api_calls"
)
```

### Get User's Subscription

```python
subscription = await SubscriptionManager.get_user_subscription(db_pool, 100)
if subscription:
    print(f"User is on {subscription.tier_name} tier")
```

### Get Usage Summary

```python
summary = await SubscriptionManager.get_usage_summary(
    db_pool,
    user_id=100,
    days=30
)
print(f"Total API calls this month: {summary['total_api_calls']}")
```

## Performance Considerations

1. **Indexes**: All query patterns have supporting indexes
2. **Composite index on (user_id, usage_date)**: O(1) daily usage lookups
3. **UNIQUE constraints**: Enforce data integrity without additional queries
4. **Batch operations**: Usage tracking handles concurrent inserts via ON CONFLICT
5. **Connection pool**: Reuses database connections efficiently

## Security Considerations

1. **Admin routes**: Require explicit admin role check
2. **User isolation**: Each user can only view their own subscription
3. **Tier hierarchy**: Enforced on server-side, not client
4. **Rate limits**: Cannot be bypassed by tier claims
5. **SQL injection prevention**: All queries use parameterized statements

## Monitoring & Debugging

### View Subscription Distribution

```sql
SELECT
    st.display_name,
    COUNT(*) as user_count,
    COUNT(CASE WHEN us.status = 'trial' THEN 1 END) as trial_count
FROM user_subscriptions us
JOIN subscription_tiers st ON us.tier_id = st.id
GROUP BY st.id, st.display_name;
```

### Find Users Over Daily Limit

```sql
SELECT
    ut.user_id,
    us.tier_id,
    ut.api_calls,
    st.max_api_calls_daily
FROM usage_tracking ut
JOIN user_subscriptions us ON ut.user_id = us.user_id
JOIN subscription_tiers st ON us.tier_id = st.id
WHERE ut.usage_date = CURRENT_DATE
  AND st.max_api_calls_daily IS NOT NULL
  AND ut.api_calls >= st.max_api_calls_daily;
```

### Find Expiring Trials

```sql
SELECT us.user_id, us.trial_ends_at
FROM user_subscriptions us
WHERE us.trial_ends_at IS NOT NULL
  AND us.trial_ends_at <= NOW() + INTERVAL '3 days'
  AND us.status = 'trial';
```

## Future Enhancements

1. **Payment Integration**: Stripe/Paddle integration for paid tiers
2. **Usage Alerts**: Notify users when approaching limits
3. **Tiered Features**: More granular feature controls
4. **Custom Plans**: Enterprise custom pricing/limits
5. **Usage Overage**: Track and bill overages
6. **Analytics**: Dashboard for subscription metrics
7. **Churn Analysis**: Identify at-risk cancellations
8. **A/B Testing**: Experiment with pricing/features

## Python 3.10 Compatibility

- Uses `asyncio.wait_for()` (compatible with Python 3.10)
- Avoids `asyncio.timeout()` (requires Python 3.11+)
- Type hints use `Optional` instead of `| None`
- Async functions use `asyncio.sleep()` not `await asyncio.timeout()`

## Testing Command

Run all subscription tests:

```bash
pytest tests/test_subscriptions.py -v
```

Run specific test:

```bash
pytest tests/test_subscriptions.py::test_create_subscription_success -v
```

Run with coverage:

```bash
pytest tests/test_subscriptions.py --cov=api.subscriptions --cov-report=html
```

## Migration Notes

- **Production Safety**: Uses `ON CONFLICT DO NOTHING` for seed data
- **Idempotent**: Safe to run multiple times
- **Backward Compatible**: Only adds tables, doesn't modify existing schema
- **Atomic**: All table creations in single transaction (SQL file)
