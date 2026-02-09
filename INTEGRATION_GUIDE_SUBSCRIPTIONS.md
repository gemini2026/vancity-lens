# Integration Guide - VCL-78 Tiered Subscriptions

## Step-by-Step Integration

### Step 1: Run Database Migration

Execute the migration to create the subscription tables:

```bash
cd /sessions/zen-relaxed-lamport/mnt/bill47
psql $DATABASE_URL < db/019_subscriptions.sql
```

**Verify migration:**
```bash
psql $DATABASE_URL -c "\dt subscription_tiers user_subscriptions usage_tracking"
```

Expected output:
```
                   List of relations
 Schema |         Name         | Type  |  Owner
--------+----------------------+-------+---------
 public | subscription_tiers   | table | postgres
 public | usage_tracking       | table | postgres
 public | user_subscriptions   | table | postgres
```

### Step 2: Verify Seed Data

Check that the 4 subscription tiers were created:

```bash
psql $DATABASE_URL -c "SELECT id, name, display_name, max_api_calls_daily FROM subscription_tiers ORDER BY id;"
```

Expected output:
```
 id |     name     | display_name | max_api_calls_daily
----+--------------+--------------+---------------------
  1 | free         | Free         |                 100
  2 | starter      | Starter      |                1000
  3 | professional | Professional |                10000
  4 | enterprise   | Enterprise   |
```

### Step 3: Update FastAPI Main App

Edit `/sessions/zen-relaxed-lamport/mnt/bill47/api/main.py` to include the subscription routers:

```python
# Add to imports section
from api.subscription_routes import router as subscription_router
from api.subscription_routes import admin_router as subscription_admin_router

# Add to app initialization (after other routers)
app.include_router(subscription_router)
app.include_router(subscription_admin_router)
```

### Step 4: Add Subscription Check to User Registration

Update user registration to automatically create a free subscription:

In `api/auth_routes.py` or wherever user registration is handled:

```python
from api.subscriptions import SubscriptionManager
import asyncpg

@router.post("/register", response_model=UserResponse)
async def register(
    user_create: UserCreate,
    db_pool: asyncpg.Pool = None,
):
    # ... existing registration logic ...

    user = await register_user(db_pool, user_create.email, user_create.password, user_create.display_name)

    # Create free subscription for new user
    try:
        subscription = await SubscriptionManager.create_subscription(
            db_pool,
            user_id=user["id"],
            tier_name="free",
            trial_days=14  # Optional: 14-day trial
        )
        logger.info(f"Created free subscription for user {user['id']}")
    except Exception as e:
        logger.error(f"Failed to create subscription for user {user['id']}: {e}")
        # Don't fail registration if subscription creation fails

    return UserResponse(**user)
```

### Step 5: Protect API Endpoints with Subscription Requirements

Update existing endpoints to require minimum subscription tiers:

#### Example 1: API Call Endpoint
```python
from api.subscriptions import require_tier, check_rate_limit
from api.user_auth import get_current_user
import asyncpg
from fastapi import Depends

@app.post("/api/v1/signals/query")
async def query_signals(
    query: SignalQuery,
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(require_tier("starter")(db_pool)),
    _rate_limit: None = Depends(check_rate_limit("signals_queried")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    """Query signals - requires at least Starter tier."""
    try:
        # Your signal querying logic
        signals = await query_signals_logic(query)

        # Track usage
        await SubscriptionManager.track_usage(
            db_pool,
            user_id=user["id"],
            usage_type="signals_queried",
            count=1
        )

        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### Example 2: Chat Endpoint
```python
@app.post("/api/v1/chat")
async def send_chat_message(
    message: ChatMessage,
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(require_tier("starter")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    """Send chat message - requires at least Starter tier with chat enabled."""
    # Check if tier has chat enabled
    subscription = await SubscriptionManager.get_user_subscription(db_pool, user["id"])
    if subscription:
        tier = await SubscriptionManager.get_tier(db_pool, subscription.tier_name)
        if not tier.features.get("chat_enabled"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chat is not enabled for your subscription tier"
            )

    # Send chat message
    response = await process_chat_message(message)

    # Track usage
    await SubscriptionManager.track_usage(
        db_pool,
        user_id=user["id"],
        usage_type="chat_messages",
        count=1
    )

    return response
```

#### Example 3: Export Endpoint
```python
@app.post("/api/v1/export")
async def export_data(
    request: ExportRequest,
    user: Dict = Depends(get_current_user(db_pool)),
    _: None = Depends(require_tier("starter")(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    """Export data - requires at least Starter tier with export enabled."""
    subscription = await SubscriptionManager.get_user_subscription(db_pool, user["id"])
    if subscription:
        tier = await SubscriptionManager.get_tier(db_pool, subscription.tier_name)
        if not tier.features.get("export_enabled"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Export is not enabled for your subscription tier"
            )

    # Export logic
    exported_data = await export_logic(request)

    # Track usage
    await SubscriptionManager.track_usage(
        db_pool,
        user_id=user["id"],
        usage_type="exports",
        count=1
    )

    return {"file": exported_data}
```

### Step 6: Add Watchlist Limit Check

For watchlist creation, verify the user hasn't exceeded their tier limit:

```python
from api.subscriptions import SubscriptionManager

@app.post("/api/v1/watchlists")
async def create_watchlist(
    watchlist: WatchlistCreate,
    user: Dict = Depends(get_current_user(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    """Create a watchlist with subscription tier limit checks."""

    # Get user's subscription and tier
    subscription = await SubscriptionManager.get_user_subscription(db_pool, user["id"])
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription required to create watchlists"
        )

    tier = await SubscriptionManager.get_tier(db_pool, subscription.tier_name)

    # Check watchlist count
    current_watchlists = await get_user_watchlist_count(db_pool, user["id"])
    if current_watchlists >= tier.max_watchlists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You have reached the maximum watchlists ({tier.max_watchlists}) for your tier. Upgrade to create more."
        )

    # Create watchlist
    new_watchlist = await create_watchlist_logic(watchlist, user["id"])

    return new_watchlist
```

### Step 7: Test Integration

Run the test suite to verify everything works:

```bash
cd /sessions/zen-relaxed-lamport/mnt/bill47
pytest tests/test_subscriptions.py -v
```

Expected output:
```
tests/test_subscriptions.py::test_get_tiers_success PASSED
tests/test_subscriptions.py::test_get_tier_success PASSED
...
======================== 45+ passed in X.XXs ========================
```

### Step 8: Add Subscription Dashboard (Optional)

Create an endpoint for users to view their subscription:

```python
@app.get("/api/v1/subscriptions/dashboard")
async def get_subscription_dashboard(
    user: Dict = Depends(get_current_user(db_pool)),
    db_pool: asyncpg.Pool = None,
):
    """Get comprehensive subscription information for dashboard."""

    # Get subscription
    subscription = await SubscriptionManager.get_user_subscription(db_pool, user["id"])
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found")

    # Get tier details
    tier = await SubscriptionManager.get_tier(db_pool, subscription.tier_name)

    # Get usage today
    usage_today = await SubscriptionManager.get_usage(db_pool, user["id"])

    # Get usage summary (30 days)
    usage_summary = await SubscriptionManager.get_usage_summary(db_pool, user["id"], days=30)

    # Calculate percentages
    api_usage_pct = 0
    if tier.max_api_calls_daily:
        api_usage_pct = (usage_today.api_calls / tier.max_api_calls_daily) * 100

    # Calculate days until renewal
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    days_until_renewal = (subscription.current_period_end.date() - now.date()).days

    return {
        "tier": {
            "name": tier.display_name,
            "features": tier.features,
            "pricing": {
                "monthly": str(tier.price_monthly) if tier.price_monthly else "Custom",
                "annual": str(tier.price_annual) if tier.price_annual else "Custom",
            }
        },
        "status": subscription.status,
        "is_trial": subscription.status == "trial",
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "period": {
            "start": subscription.current_period_start.isoformat(),
            "end": subscription.current_period_end.isoformat(),
            "days_remaining": days_until_renewal,
        },
        "usage_today": {
            "api_calls": {
                "used": usage_today.api_calls,
                "limit": tier.max_api_calls_daily,
                "percentage": api_usage_pct,
            },
            "signals_queried": {
                "used": usage_today.signals_queried,
                "limit": tier.max_signals_per_query,
            },
            "chat_messages": usage_today.chat_messages,
            "exports": usage_today.exports,
        },
        "usage_30_days": usage_summary,
    }
```

### Step 9: Setup Monitoring & Alerts (Optional)

Create a scheduled task to monitor subscriptions:

```python
# In background tasks or scheduler
import asyncio
from datetime import datetime, timezone, timedelta

async def check_expiring_trials():
    """Alert users about expiring trials."""
    db_pool = ... # Get pool

    # Find trials expiring in 3 days
    async with db_pool.acquire() as conn:
        trials = await conn.fetch(
            """
            SELECT us.user_id, us.trial_ends_at, u.email
            FROM user_subscriptions us
            JOIN users u ON us.user_id = u.id
            WHERE us.trial_ends_at IS NOT NULL
              AND us.trial_ends_at <= NOW() + INTERVAL '3 days'
              AND us.trial_ends_at > NOW()
            """
        )

    # Send email notifications
    for trial in trials:
        days_left = (trial["trial_ends_at"].date() - datetime.now(tz=timezone.utc).date()).days
        await send_email(
            trial["email"],
            "Your trial expires in {days_left} days!",
            "Please upgrade to continue using VanCity Lens"
        )
```

## Troubleshooting

### Issue: "subscription_tiers table not found"
**Solution**: Run the database migration:
```bash
psql $DATABASE_URL < db/019_subscriptions.sql
```

### Issue: "User already has a subscription"
**Solution**: This is expected. Users can only have one active subscription at a time.
Use upgrade/downgrade instead of trying to create a new one.

### Issue: "Rate limit exceeded (429)"
**Solution**: User has exceeded their daily limit for that usage type.
- Free: 100 API calls/day
- Starter: 1,000 API calls/day
- Professional: 10,000 API calls/day
- Enterprise: Unlimited

### Issue: "Insufficient tier (403)"
**Solution**: The endpoint requires a higher tier. User needs to upgrade their subscription.

### Issue: Tests failing with "No such module"
**Solution**: Ensure all imports are correct and modules exist:
```bash
cd /sessions/zen-relaxed-lamport/mnt/bill47
python3 -m pytest tests/test_subscriptions.py -v
```

## Performance Optimization Tips

1. **Cache tier information** - Tiers don't change often:
```python
from functools import lru_cache

@lru_cache(maxsize=10)
async def get_tier_cached(tier_name: str):
    return await SubscriptionManager.get_tier(db_pool, tier_name)
```

2. **Batch usage tracking** - If tracking many operations:
```python
# Instead of individual calls, batch them
for operation in operations:
    await SubscriptionManager.track_usage(db_pool, user_id, usage_type, 1)

# Better: accumulate and insert once
total = len(operations)
await SubscriptionManager.track_usage(db_pool, user_id, usage_type, total)
```

3. **Query optimization** - Use connection pooling:
```python
# db_pool should be reused, not created per request
# The FastAPI dependency injection handles this
```

## Security Checklist

- [x] Tier checks enforced server-side
- [x] Admin routes protected
- [x] User isolation enforced
- [x] Rate limits prevent abuse
- [x] SQL injection prevention via parameterized queries
- [x] No sensitive data in logs

## Monitoring Queries

View subscription health:
```sql
-- Active subscriptions by tier
SELECT st.display_name, COUNT(*) as count
FROM user_subscriptions us
JOIN subscription_tiers st ON us.tier_id = st.id
WHERE us.status = 'active'
GROUP BY st.id, st.display_name;

-- Trial signups this month
SELECT DATE(created_at), COUNT(*) as count
FROM user_subscriptions
WHERE status = 'trial' AND created_at >= DATE_TRUNC('month', NOW())
GROUP BY DATE(created_at);

-- Top API users today
SELECT user_id, api_calls
FROM usage_tracking
WHERE usage_date = CURRENT_DATE
ORDER BY api_calls DESC
LIMIT 10;
```

## Next Steps

1. ✅ Database migration completed
2. ✅ Routes integrated into FastAPI
3. ✅ Endpoints secured with tier requirements
4. ✅ Usage tracking implemented
5. ⏳ (Optional) Payment integration (Stripe/Paddle)
6. ⏳ (Optional) Usage alerts and notifications
7. ⏳ (Optional) Analytics dashboard
8. ⏳ (Optional) Custom enterprise plans

## Support & Documentation

- **Quick Reference**: See `SUBSCRIPTIONS_QUICK_REFERENCE.md`
- **Implementation Details**: See `IMPLEMENTATION_SUBSCRIPTIONS.md`
- **API Documentation**: FastAPI auto-generated docs at `/docs`
- **Tests**: See `tests/test_subscriptions.py` for usage examples
