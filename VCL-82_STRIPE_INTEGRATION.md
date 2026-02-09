# VCL-82 [BIZ-003] Stripe Payment Integration — Implementation Summary

## Overview

Implemented complete Stripe payment integration for VanCity Lens subscription platform. This includes checkout session creation, webhook handling, subscription lifecycle management, and Stripe Customer Portal integration.

## Files Created

### 1. `/api/stripe_integration.py` — Stripe Service Layer

Core service class for all Stripe operations:

**StripeService Class Methods:**

- `create_checkout_session()` — Creates Stripe Checkout sessions for subscription tiers
  - Supports monthly and annual billing
  - Maps internal tier names to Stripe price IDs
  - Returns session_id and checkout_url for redirect
  - Handles tier validation and Stripe API errors

- `handle_webhook()` — Verifies and routes Stripe webhook events
  - Validates Stripe signature (HMAC-SHA256)
  - Routes events to appropriate handlers
  - Supports: subscription.created, invoice.paid, invoice.payment_failed, subscription.deleted
  - Returns event status and processing info

- `process_subscription_created()` — Handles subscription creation
  - Stores Stripe IDs in database
  - Creates user_subscriptions record
  - Implements idempotency (ON CONFLICT DO NOTHING)
  - Records events in payment_events audit log

- `process_invoice_paid()` — Handles successful payments
  - Sets subscription status to "active"
  - Clears grace period if previously set
  - Records payment event

- `process_invoice_payment_failed()` — Handles failed payments
  - Implements 7-day grace period
  - Subscription remains active during grace period
  - Allows user to retry payment without losing access
  - Records failure reason

- `process_subscription_deleted()` — Handles cancellations
  - Sets subscription status to "cancelled"
  - Clears grace period
  - Prevents re-activation

- `generate_portal_url()` — Creates Stripe Customer Portal session
  - Returns URL for user to manage subscription
  - Update payment method, change plan, cancel, etc.

- `cancel_subscription()` — Cancels active subscriptions
  - Calls Stripe API to delete subscription
  - Requires database subscription record

**Configuration:**
- `STRIPE_API_KEY` — From environment variable
- `STRIPE_WEBHOOK_SECRET` — From environment variable
- `GRACE_PERIOD_DAYS` — Set to 7 days (configurable constant)

### 2. `/api/stripe_routes.py` — FastAPI Endpoints

RESTful API endpoints for Stripe operations:

**Public Endpoints (Authenticated):**

- `POST /api/v1/stripe/create-checkout-session`
  - Request: `{tier_name, billing_period, success_url, cancel_url}`
  - Response: `{session_id, checkout_url}`
  - Redirects user to Stripe Checkout
  - Validates tier (must not be "free")

- `GET /api/v1/stripe/portal`
  - Response: `{portal_url}`
  - Returns Stripe Customer Portal URL
  - 404 if no Stripe customer ID

- `POST /api/v1/stripe/cancel`
  - Request: `{confirm: true}`
  - Response: `{status, stripe_subscription_id, cancelled_at}`
  - Requires explicit confirmation to prevent accidents
  - 404 if no active subscription

**Webhook Endpoint (Unauthenticated):**

- `POST /api/v1/stripe/webhook`
  - Validates Stripe signature header
  - Processes Stripe events
  - 401 if signature invalid or missing
  - Returns: `{event_id, event_type, status}`

**Error Handling:**
- 400: Invalid tier/billing period/payload
- 401: Missing/invalid signature
- 402: Payment processing error
- 404: No subscription found
- 500: Internal error

### 3. `/db/020_stripe_integration.sql` — Database Migration

Adds Stripe integration columns and tables:

**subscription_tiers modifications:**
- `stripe_price_id` — Unique Stripe price ID (TEXT)
- `stripe_product_id` — Stripe product ID (TEXT)
- `is_stripe_managed` — Flag for Stripe-managed tiers (BOOLEAN)

**user_subscriptions modifications:**
- `stripe_customer_id` — Stripe customer ID (TEXT)
- `stripe_subscription_id` — Stripe subscription ID (TEXT)
- `grace_period_ends_at` — Grace period expiration (TIMESTAMP)

**payment_events table (new):**
- `id` — Primary key
- `user_id` — Foreign key to users
- `stripe_event_id` — Unique event identifier (for idempotency)
- `event_type` — Event type string
- `event_data` — Full event data (JSONB)
- `processed` — Processing status flag
- `error_message` — Error description if processing failed
- `created_at` — Event received time
- `processed_at` — Processing completion time

**Indexes:**
- Event ID lookup (webhook idempotency)
- User ID lookup (audit trails)
- Event type filtering (reporting)
- Processing status (queue management)
- Grace period checking (expiration detection)

### 4. `/tests/test_stripe_integration.py` — Comprehensive Test Suite

**29 passing tests** covering:

**Checkout Session Tests (6 tests):**
- ✓ Successful session creation (all tiers)
- ✓ Tier not found error handling
- ✓ User not found error handling
- ✓ Missing Stripe price ID handling
- ✓ Missing API key handling
- ✓ Stripe API error handling

**Webhook Signature Tests (3 tests):**
- ✓ Valid signature acceptance
- ✓ Invalid signature rejection
- ✓ Missing webhook secret handling

**Subscription Created Event (3 tests):**
- ✓ Successful processing
- ✓ Missing metadata validation
- ✓ Tier lookup validation

**Invoice Payment Events (4 tests):**
- ✓ Payment success updates subscription
- ✓ Payment success clears grace period
- ✓ Payment failure sets 7-day grace period
- ✓ Grace period duration verification

**Subscription Deletion Tests (1 test):**
- ✓ Cancellation updates database

**Portal URL Tests (3 tests):**
- ✓ Successful portal URL generation
- ✓ Missing Stripe customer error
- ✓ Missing API key error

**Subscription Cancellation Tests (3 tests):**
- ✓ Successful cancellation
- ✓ No active subscription error
- ✓ No Stripe ID error

**Webhook Routing Tests (2 tests):**
- ✓ Unhandled event routing
- ✓ Event routing to correct handlers

**Database & Error Tests (3 tests):**
- ✓ Database error handling
- ✓ Event idempotency (ON CONFLICT)
- ✓ Multiple tier support

**Billing Period Tests (1 test):**
- ✓ Annual billing period support

## Integration Points

### With Existing VCL-78 (BIZ-002) Subscription System

- Uses existing `SubscriptionTier` enum (free, starter, professional, enterprise)
- Updates `user_subscriptions` table with Stripe IDs
- Maintains `SubscriptionStatus` enum (active, cancelled, expired, trial)
- Leverages `SubscriptionManager` tier queries

### With Authentication (VCL-74 / BIZ-001)

- Uses `get_current_user_from_request` dependency
- Extracts user from JWT token
- Validates user_id in Stripe metadata

### With Database (asyncpg)

- Uses standard `get_db_pool` dependency
- Acquires connections from pool context manager
- Implements async/await patterns
- Uses parameterized queries for SQL injection prevention

## Key Design Decisions

### Grace Period Implementation

When a payment fails:
1. Set `grace_period_ends_at` to NOW() + 7 days
2. Subscription remains "active" during grace period
3. User retains full access to features
4. On successful retry payment, clear grace period
5. After 7 days, subscription expires (handled by separate service)

This allows recovery from temporary payment issues without disrupting user experience.

### Webhook Idempotency

All webhook handlers use SQL `ON CONFLICT (stripe_event_id) DO NOTHING` to prevent duplicate processing:

```sql
INSERT INTO payment_events (stripe_event_id, ...)
VALUES (...)
ON CONFLICT (stripe_event_id) DO NOTHING
```

This ensures Stripe's webhook retries don't create duplicate subscriptions or payments.

### Metadata for Tracking

Stripe checkout metadata stores:
- `user_id` — Internal user identifier
- `tier_name` — Subscription tier for validation
- `billing_period` — "monthly" or "annual"

Allows webhook handlers to look up user without Stripe API call.

### Error Recording

All webhook processing errors are logged to `payment_events`:
- `error_message` — Description of what failed
- `processed_at` — When failure occurred
- Allows debugging and manual reconciliation

## Environment Variables

**Required for Production:**

```bash
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

**For Testing:**

```bash
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_test_...
```

## Stripe Configuration Needed

### Products & Prices

Create in Stripe Dashboard:

| Tier | Monthly Price | Annual Price |
|------|---------------|--------------|
| Starter | $29.99 | $299.99 |
| Professional | $99.99 | $999.99 |
| Enterprise | Custom | Custom |

Capture price IDs (price_xxx) and update database:

```sql
UPDATE subscription_tiers
SET stripe_price_id = 'price_xxx'
WHERE name = 'starter';
```

### Webhook Endpoint

Configure in Stripe Dashboard:

- Endpoint: `https://api.vancitylens.com/api/v1/stripe/webhook`
- Events:
  - `customer.subscription.created`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`
  - `customer.subscription.deleted`

Copy webhook secret to `STRIPE_WEBHOOK_SECRET` env var.

## Running Tests

```bash
# Run all Stripe integration tests
pytest tests/test_stripe_integration.py -v

# Run specific test
pytest tests/test_stripe_integration.py::test_create_checkout_session_success -v

# Run with coverage
pytest tests/test_stripe_integration.py --cov=api.stripe_integration
```

**All 29 tests pass** with mocked Stripe API and database.

## Security Considerations

### Webhook Signature Verification

Every webhook is verified using HMAC-SHA256:
```python
stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
```

Missing or invalid signature immediately rejects webhook.

### API Key Management

- Never committed to version control
- Loaded from environment at startup
- Test uses different key than production
- All Stripe API calls use authenticated client

### Database Queries

All queries use parameterized placeholders ($1, $2, etc.):
```python
await conn.execute(
    "INSERT INTO table (col) VALUES ($1)",
    user_input,
)
```

Prevents SQL injection attacks.

### User Validation

Stripe customer IDs are verified to belong to authenticated user:
```python
# Only current user can access their subscription
subscription = await SubscriptionManager.get_user_subscription(
    db_pool, user["id"]
)
```

## Monitoring & Observability

### Logging

All operations logged:
- Checkout session creation
- Webhook receipt and processing
- Signature verification failures
- API errors
- Database errors

Logger: `api.stripe_integration`

### Audit Trail

`payment_events` table tracks:
- Every webhook received
- Event processing status
- Errors and failures
- Timestamps for debugging

Query example:
```sql
SELECT * FROM payment_events
WHERE user_id = 123
ORDER BY created_at DESC;
```

### Monitoring Queries

Failed payments in last 7 days:
```sql
SELECT user_id, event_data
FROM payment_events
WHERE event_type = 'invoice.payment_failed'
AND created_at > NOW() - INTERVAL '7 days';
```

Pending grace periods:
```sql
SELECT u.user_id, u.grace_period_ends_at
FROM user_subscriptions u
WHERE u.grace_period_ends_at IS NOT NULL
AND u.grace_period_ends_at > NOW();
```

## Future Enhancements

1. **Coupon/Discount Support**
   - Add discount codes to checkout
   - Track coupon usage in events

2. **Subscription Updates**
   - Allow tier upgrades/downgrades
   - Proration handling

3. **Automated Grace Period Expiry**
   - Background job to expire subscriptions after grace period
   - Send warning emails before expiry

4. **Payment Retry Logic**
   - Automatic retry on failed payments
   - Exponential backoff

5. **Usage-Based Billing**
   - Track metered usage
   - Report to Stripe for overage billing

6. **Invoice Management**
   - Store invoice PDFs
   - Email invoices to users
   - Tax handling (VATIN, GST/HST)

## Deployment Checklist

- [ ] Add `stripe>=5.0.0` to requirements.txt
- [ ] Run migration: `db/020_stripe_integration.sql`
- [ ] Create Stripe products and prices
- [ ] Set `STRIPE_API_KEY` env var (production)
- [ ] Set `STRIPE_WEBHOOK_SECRET` env var (production)
- [ ] Configure webhook endpoint in Stripe Dashboard
- [ ] Update subscription tier table with `stripe_price_id` values
- [ ] Run tests: `pytest tests/test_stripe_integration.py`
- [ ] Deploy `/api/stripe_integration.py`
- [ ] Deploy `/api/stripe_routes.py`
- [ ] Register routes in main FastAPI app
- [ ] Monitor logs for webhook errors

## Conclusion

VCL-82 implements a production-ready Stripe integration with:

- ✓ Secure checkout flow
- ✓ Robust webhook handling with idempotency
- ✓ Grace period support for payment failures
- ✓ Complete audit logging
- ✓ Comprehensive error handling
- ✓ 29 passing test cases
- ✓ Full integration with existing subscription system
