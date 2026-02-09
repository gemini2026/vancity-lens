# Tiered Subscriptions - Quick Reference Guide

## Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `db/019_subscriptions.sql` | Database schema & seed data | 180 |
| `api/subscriptions.py` | Core subscription logic | 680 |
| `api/subscription_routes.py` | FastAPI endpoints | 350 |
| `tests/test_subscriptions.py` | Comprehensive tests | 800+ |

## Subscription Tiers

| Tier | Watchlists | API Calls/Day | Signals/Query | Chat | Digest | Export | Priority Support |
|------|-----------|---------------|---------------|------|--------|--------|-----------------|
| Free | 1 | 100 | 10 | ❌ | ❌ | ❌ | ❌ |
| Starter | 5 | 1,000 | 50 | ✅ | ❌ | ✅ | ❌ |
| Professional | 20 | 10,000 | 200 | ✅ | ✅ | ✅ | ✅ |
| Enterprise | ∞ | ∞ | ∞ | ✅ | ✅ | ✅ | ✅ |

## API Endpoints

### Get Subscription Tiers
```bash
GET /api/v1/subscriptions/tiers
# Returns: List[TierInfo]
```

### Get Current User's Subscription
```bash
GET /api/v1/subscriptions/current
# Returns: SubscriptionStatusResponse {subscription, tier, usage_today, limits, days_until_renewal, is_trial}
```

### Subscribe to Tier
```bash
POST /api/v1/subscriptions/subscribe?tier_name=starter&trial_days=14
# Returns: UserSubscription
```

### Upgrade/Downgrade
```bash
POST /api/v1/subscriptions/upgrade?new_tier=professional
POST /api/v1/subscriptions/downgrade?new_tier=free
# Returns: UserSubscription
```

### Manage Subscription
```bash
POST /api/v1/subscriptions/cancel
POST /api/v1/subscriptions/reactivate
# Returns: UserSubscription
```

### Usage Tracking
```bash
GET /api/v1/subscriptions/usage?date=2024-02-08
GET /api/v1/subscriptions/usage/summary?days=30
# Returns: UsageStats / Dict
```

### Admin Stats
```bash
GET /api/v1/admin/subscriptions/stats
# Returns: {total_subscribers, active_subscriptions, trial_subscriptions, cancellations_pending, distribution_by_tier}
# Requires: Admin role
```

## Code Examples

### Create Subscription
```python
from api.subscriptions import SubscriptionManager

subscription = await SubscriptionManager.create_subscription(
    db_pool,
    user_id=100,
    tier_name="starter",
    trial_days=14
)
```

### Track Usage
```python
await SubscriptionManager.track_usage(
    db_pool,
    user_id=100,
    usage_type="api_calls",  # or "signals_queried", "chat_messages", "exports"
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

if not within_limit:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

### Require Tier in Route
```python
from api.subscriptions import require_tier
from api.user_auth import get_current_user

@app.post("/api/v1/signals/query")
async def query_signals(
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(require_tier("starter")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    await SubscriptionManager.track_usage(db_pool, user["id"], "signals_queried", 1)
    # ... signal logic
    return {...}
```

### Rate Limit Dependency
```python
from api.subscriptions import check_rate_limit

@app.post("/api/v1/api-call")
async def api_call(
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(check_rate_limit("api_calls")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    await SubscriptionManager.track_usage(db_pool, user["id"], "api_calls", 1)
    return {...}
```

## Usage Types
- `api_calls`: Count of API calls made
- `signals_queried`: Count of signals queried
- `chat_messages`: Count of chat messages sent
- `exports`: Count of data exports

## Subscription States
- `active`: Currently active subscription
- `trial`: In trial period
- `cancelled`: Cancelled (pending period end)
- `expired`: Subscription expired

## HTTP Status Codes
- `200 OK`: Success
- `400 Bad Request`: Invalid tier, already subscribed, no subscription
- `403 Forbidden`: Insufficient tier, admin-only, inactive account
- `404 Not Found`: Subscription not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Database error

## Database Queries

### Get User's Current Subscription with Tier
```sql
SELECT us.*, st.name as tier_name, st.display_name as tier_display_name
FROM user_subscriptions us
JOIN subscription_tiers st ON us.tier_id = st.id
WHERE us.user_id = $1;
```

### Get Daily Usage
```sql
SELECT * FROM usage_tracking
WHERE user_id = $1 AND usage_date = CURRENT_DATE;
```

### Get Usage Summary (30 days)
```sql
SELECT
    SUM(api_calls) as total_api_calls,
    SUM(signals_queried) as total_signals_queried,
    SUM(chat_messages) as total_chat_messages,
    SUM(exports) as total_exports
FROM usage_tracking
WHERE user_id = $1 AND usage_date >= CURRENT_DATE - INTERVAL '30 days';
```

### Get Subscription Distribution
```sql
SELECT st.display_name, COUNT(*) as user_count
FROM user_subscriptions us
JOIN subscription_tiers st ON us.tier_id = st.id
GROUP BY st.id, st.display_name;
```

## Testing

Run all tests:
```bash
pytest tests/test_subscriptions.py -v
```

Run specific test:
```bash
pytest tests/test_subscriptions.py::test_create_subscription_success -v
```

With coverage:
```bash
pytest tests/test_subscriptions.py --cov=api.subscriptions
```

## Common Workflows

### Onboarding Flow
1. User registers → create subscription to "free" tier
2. Option to upgrade → POST /upgrade with new tier
3. Trial ends → move to active or expired

### Usage Monitoring
1. Each API call → track_usage(..., "api_calls", 1)
2. Check limit before operation → check_limit(..., "api_calls")
3. Return 429 if over limit
4. Show usage stats on dashboard → GET /usage/summary

### Cancellation Flow
1. User cancels → POST /cancel (marks for end of period)
2. Period ends → system updates status to "cancelled"
3. User can reactivate → POST /reactivate before period ends

### Admin Monitoring
1. View subscription stats → GET /admin/subscriptions/stats
2. Track MRR (Monthly Recurring Revenue) from tier prices
3. Monitor churn rate and trial-to-paid conversion

## Performance Notes

- **Tier lookups**: O(1) with name index
- **User subscriptions**: O(1) with user_id unique index
- **Daily usage**: O(1) with (user_id, usage_date) composite index
- **Batch operations**: ON CONFLICT handles concurrent tracking

## Security Checklist

- ✅ Tier checks enforced server-side
- ✅ Admin routes require role validation
- ✅ User isolation (can't view others' subscriptions)
- ✅ Rate limits cannot be bypassed
- ✅ All queries use parameterized statements
- ✅ No sensitive data in URLs

## Integration Checklist

- [ ] Run database migration: `psql $DATABASE_URL < db/019_subscriptions.sql`
- [ ] Import routers in main.py: `from api.subscription_routes import router, admin_router`
- [ ] Include routers: `app.include_router(router); app.include_router(admin_router)`
- [ ] Update route handlers to use `require_tier()` and `check_rate_limit()` dependencies
- [ ] Add usage tracking calls after each operation
- [ ] Test with pytest: `pytest tests/test_subscriptions.py`
- [ ] Update API documentation with subscription endpoints
- [ ] Set up monitoring for subscription metrics
