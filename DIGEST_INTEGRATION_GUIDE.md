# VCL-42 Weekly Digest Integration Guide

## Quick Start

### 1. Database Setup

Apply the migration:
```bash
psql $DATABASE_URL < db/016_weekly_digests.sql
```

This creates:
- `digest_subscriptions` table
- `digest_deliveries` table
- All necessary indexes

### 2. Import Modules in Main App

Add to `api/main.py`:

```python
from api.intelligence.digest_routes import router as digest_router, admin_router as admin_digest_router

# In app creation section:
app.include_router(digest_router)
app.include_router(admin_digest_router)
```

### 3. Scheduler Setup (Optional but Recommended)

Create a background task to run digest cycles. Add to `api/main.py`:

```python
from api.intelligence.digest import DigestScheduler, DigestFrequency
import asyncio

@app.on_event("startup")
async def schedule_digests():
    """Schedule weekly digest generation."""
    async def run_weekly_digests():
        while True:
            try:
                # Run every Monday at 8 AM UTC
                now = datetime.utcnow()
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                seconds_until_8am = (8 * 3600) - (now.hour * 3600 + now.minute * 60 + now.second)
                if seconds_until_8am < 0:
                    days_until_monday += 1
                    seconds_until_8am += 86400

                wait_seconds = days_until_monday * 86400 + seconds_until_8am
                await asyncio.sleep(wait_seconds)

                await DigestScheduler.run_digest_cycle(db.pool, DigestFrequency.WEEKLY)
            except Exception as e:
                logger.error(f"Error in digest scheduler: {e}", exc_info=True)
                await asyncio.sleep(3600)  # Retry after 1 hour on error

    asyncio.create_task(run_weekly_digests())
```

Or use Celery for production:

```python
# celery_app.py
from celery import Celery
from api.intelligence.digest import DigestScheduler, DigestFrequency

celery = Celery(__name__)
celery.conf.beat_schedule = {
    'generate-weekly-digests': {
        'task': 'tasks.run_weekly_digests',
        'schedule': crontab(day_of_week=1, hour=8, minute=0),  # Monday 8 AM
    },
}

@celery.task
async def run_weekly_digests():
    deliveries = await DigestScheduler.run_digest_cycle(db.pool)
    logger.info(f"Generated {len(deliveries)} digests")
    return len(deliveries)
```

### 4. API Documentation

The following endpoints are now available:

#### Subscription Management
- `POST /api/v1/intel/digests/subscribe` - Create subscription
- `GET /api/v1/intel/digests/subscriptions` - List user subscriptions
- `PUT /api/v1/intel/digests/subscriptions/{id}` - Update subscription
- `DELETE /api/v1/intel/digests/subscriptions/{id}` - Delete subscription

#### Digest Operations
- `GET /api/v1/intel/digests/preview` - Preview digest
- `GET /api/v1/intel/digests/history` - View past digests

#### Admin Operations
- `POST /api/v1/admin/digests/trigger` - Trigger digest generation

### 5. Frontend Integration Example

```javascript
// Subscribe to digest
async function subscribeToDigest() {
  const response = await fetch('/api/v1/intel/digests/subscribe', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      neighborhoods: ['Downtown', 'Mount Pleasant'],
      signal_types: ['rezoning_decision', 'permit_approval'],
      frequency: 'weekly'
    })
  });
  return response.json();
}

// Preview digest
async function previewDigest(neighborhoods, signalTypes) {
  const params = new URLSearchParams({
    neighborhoods: neighborhoods.join(','),
    signal_types: signalTypes.join(',')
  });

  const response = await fetch(`/api/v1/intel/digests/preview?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
}

// Get digest history
async function getDigestHistory(subscriptionId) {
  const response = await fetch(
    `/api/v1/intel/digests/history?subscription_id=${subscriptionId}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  return response.json();
}
```

## Configuration Options

### Environment Variables

```bash
# Database credentials (already configured)
DATABASE_URL=postgresql://...

# Optional: Digest generation schedule
DIGEST_SCHEDULE_ENABLED=true
DIGEST_SCHEDULE_DAY=1  # 0=Sunday, 1=Monday, etc.
DIGEST_SCHEDULE_HOUR=8  # UTC hour
DIGEST_SCHEDULE_MINUTE=0

# Optional: Delivery settings
DIGEST_EMAIL_ENABLED=true
DIGEST_EMAIL_FROM=digests@vancitylens.com
DIGEST_MAX_HIGHLIGHTS=5
DIGEST_DEFAULT_PERIOD_DAYS=7
```

## Email Integration

To send digests via email, update `digest_routes.py` or add a separate delivery module:

```python
# api/intelligence/digest_delivery.py
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

async def send_digest_email(
    delivery: DigestDelivery,
    user_email: str,
    user_name: str,
):
    """Send digest via email."""
    content = delivery.content_json

    # Format digest content as HTML
    html_body = format_digest_html(content)

    message = Mail(
        from_email='digests@vancitylens.com',
        to_emails=user_email,
        subject=f"VanCity Lens Weekly Digest - {delivery.digest_date}",
        html_content=html_body
    )

    try:
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sg.send(message)

        # Mark as sent
        await DigestScheduler.mark_delivery_sent(db.pool, delivery.id)
        return True
    except Exception as e:
        logger.error(f"Failed to send digest {delivery.id}: {e}")
        await DigestScheduler.mark_delivery_failed(db.pool, delivery.id, str(e))
        return False

def format_digest_html(content: dict) -> str:
    """Format digest content as HTML email."""
    # Implementation details...
    pass
```

## Testing in Development

### Manual Testing

```bash
# Run tests
pytest tests/test_digest.py -v

# Test digest generation
python -c "
import asyncio
from api.intelligence.digest import DigestGenerator
from api.db import db

async def test():
    await db.connect()
    digest = await DigestGenerator.generate_weekly_digest(db.pool, user_id=1)
    print(f'Generated digest with {len(digest.highlights)} highlights')
    await db.disconnect()

asyncio.run(test())
"

# Test scheduler
python -c "
import asyncio
from api.intelligence.digest import DigestScheduler, DigestFrequency
from api.db import db

async def test():
    await db.connect()
    deliveries = await DigestScheduler.run_digest_cycle(db.pool, DigestFrequency.WEEKLY)
    print(f'Created {len(deliveries)} digest deliveries')
    await db.disconnect()

asyncio.run(test())
"
```

### API Testing with curl

```bash
# Get auth token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=testuser&password=password" | jq -r '.access_token')

# Subscribe to digest
curl -X POST http://localhost:8000/api/v1/intel/digests/subscribe \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "neighborhoods": ["Downtown"],
    "signal_types": ["rezoning_decision"],
    "frequency": "weekly",
    "is_active": true
  }'

# Preview digest
curl -X GET "http://localhost:8000/api/v1/intel/digests/preview?neighborhoods=Downtown" \
  -H "Authorization: Bearer $TOKEN"

# Get history
curl -X GET "http://localhost:8000/api/v1/intel/digests/history" \
  -H "Authorization: Bearer $TOKEN"
```

## Monitoring & Maintenance

### Health Checks

Monitor delivery success rates:

```sql
-- Check delivery status
SELECT
    delivery_status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM digest_deliveries), 2) as percentage
FROM digest_deliveries
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY delivery_status;

-- Find failed deliveries
SELECT id, subscription_id, created_at
FROM digest_deliveries
WHERE delivery_status = 'failed'
ORDER BY created_at DESC
LIMIT 10;

-- Check subscription activity
SELECT
    frequency,
    COUNT(*) as active_subs,
    COUNT(CASE WHEN updated_at > NOW() - INTERVAL '7 days' THEN 1 END) as updated_recently
FROM digest_subscriptions
WHERE is_active = true
GROUP BY frequency;
```

### Performance Optimization

Monitor query performance:

```sql
-- Index usage statistics
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename IN ('digest_subscriptions', 'digest_deliveries')
ORDER BY idx_scan DESC;

-- Query performance
EXPLAIN ANALYZE
SELECT * FROM digest_deliveries
WHERE subscription_id = 1
ORDER BY digest_date DESC
LIMIT 20;
```

## Troubleshooting

### Issue: No digests being generated

1. Check if scheduler is running: `systemctl status digest-scheduler`
2. Verify subscriptions exist: `SELECT COUNT(*) FROM digest_subscriptions WHERE is_active = true;`
3. Check signal availability: `SELECT COUNT(*) FROM intelligence_signals WHERE event_date >= CURRENT_DATE - 7;`
4. Review logs: `docker logs <container> | grep "digest"`

### Issue: Empty digest content

1. Verify signal extraction: `SELECT COUNT(*) FROM intelligence_signals;`
2. Check date range in subscription
3. Confirm neighborhood and signal type match actual data
4. Test with debug mode: Enable verbose logging in `digest.py`

### Issue: Database performance

1. Analyze table sizes: `SELECT pg_size_pretty(pg_total_relation_size('digest_deliveries'));`
2. Check index usage: See performance optimization section
3. Archive old deliveries: `DELETE FROM digest_deliveries WHERE digest_date < CURRENT_DATE - 365;`
4. Vacuum tables: `VACUUM ANALYZE digest_subscriptions, digest_deliveries;`

## Production Checklist

- [ ] Database migration applied
- [ ] Routes integrated into main FastAPI app
- [ ] Authentication middleware configured
- [ ] Scheduler/background task set up
- [ ] Email delivery service configured (if enabled)
- [ ] Monitoring/alerts configured for failed deliveries
- [ ] Test with real user subscriptions
- [ ] Performance tested under load
- [ ] Backup and recovery procedures documented
- [ ] Logging configured appropriately
