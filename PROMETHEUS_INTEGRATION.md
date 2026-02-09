# Prometheus Metrics Integration Guide (VCL-49 / INFRA-007)

This guide explains how to integrate the new Prometheus metrics and Grafana dashboard into the VanCity Lens application.

## Files Created

### 1. Core Metrics Implementation
- **`api/metrics.py`** (9.0 KB)
  - `PrometheusMetrics` class: Singleton managing all metrics
  - `PrometheusMiddleware` class: FastAPI middleware for request tracking
  - Metrics defined:
    - `request_duration_seconds`: Histogram with labels (method, endpoint, status)
    - `api_calls_total`: Counter with labels (method, endpoint, status)
    - `active_requests`: Gauge for concurrent request count
    - `db_pool_size`: Gauge with labels (pool_name, state)
    - `cache_hit_ratio`: Gauge (0.0-1.0)
    - `cache_hits_total`: Counter
    - `cache_misses_total`: Counter
    - `errors_total`: Counter with labels (endpoint, status)

- **`api/metrics_routes.py`** (1.2 KB)
  - FastAPI router with `GET /metrics` endpoint
  - Returns Prometheus text format for scraping

### 2. Configuration Files
- **`config/prometheus/prometheus.yml`** (851 bytes)
  - Prometheus scrape configuration
  - Configures VanCity Lens API as target at `localhost:8000/metrics`
  - Scrape interval: 15 seconds

- **`config/prometheus/alert_rules.yml`** (3.4 KB)
  - Alert rules with these critical thresholds:
    - **P95 Latency Alert**: > 5 seconds for 5 minutes (warning)
    - **P99 Latency Alert**: > 10 seconds for 3 minutes (critical)
    - **High Error Rate**: > 5% for 2 minutes (warning)
    - **Critical Error Rate**: > 10% for 1 minute (critical)
    - **DB Pool Exhaustion**: > 90% utilization for 2 minutes (critical)
    - **Low Cache Hit Ratio**: < 50% for 10 minutes (info)
    - **High Concurrent Requests**: > 100 active for 5 minutes (warning)

### 3. Grafana Dashboard
- **`config/grafana/dashboards/vancity-lens.json`** (9.2 KB)
  - Pre-configured dashboard with 10 panels:
    1. **Request Rate** (req/sec) - Graph
    2. **Active Requests** - Graph
    3. **Request Latency P50/P95/P99** - Graph with P95 alert threshold at 5s
    4. **Error Rate (%)** - Graph with alert threshold at 5%
    5. **DB Pool Utilization (%)** - Graph with alert threshold at 90%
    6. **Cache Hit Ratio** - Gauge with color thresholds
    7. **DB Pool Size Details** - Table showing active/idle/total
    8. **Request Distribution by Endpoint** - Pie chart
    9. **HTTP Status Code Distribution** - Pie chart
    10. **Errors by Endpoint** - Table

### 4. Comprehensive Tests
- **`tests/test_metrics.py`** (673 lines, 50 test cases)
  - Singleton pattern tests
  - Middleware request tracking tests
  - Histogram and counter recording tests
  - Gauge update tests
  - Endpoint exclusion tests
  - Label correctness tests
  - Prometheus format output tests
  - Error handling tests
  - Performance tests
  - Edge case tests

## Integration Steps

### Step 1: Add Imports to main.py

Add these imports to the top of `api/main.py`:

```python
from .metrics import PrometheusMiddleware, get_metrics
from .metrics_routes import router as metrics_router
```

### Step 2: Add Middleware (in main.py after other middleware)

Around line 289, after the `MaxPageSizeMiddleware` addition, add:

```python
# Prometheus metrics middleware for performance monitoring (VCL-49 / INFRA-007)
app.add_middleware(PrometheusMiddleware)
```

The complete middleware stack should look like:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
)

# Response compression for JSON/GeoJSON (VCL-71 / PERF-009)
app.add_middleware(CompressionMiddleware)

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting for general API endpoints (VCL-20 / SEC-008)
app.add_middleware(RateLimitMiddleware)

# Request ID middleware for request tracing (VCL-53 / INFRA-008)
app.add_middleware(RequestIdMiddleware)

# API versioning strategy (VCL-23 / SEC-009)
app.add_middleware(APIVersionMiddleware)

# Audit logging for admin operations (VCL-35 / SEC-012)
app.add_middleware(AuditMiddleware)

# Sentry error tracking (VCL-45 / INFRA-006)
sentry_middleware = get_sentry_middleware()
if sentry_middleware:
    app.add_middleware(sentry_middleware)

# Frontend pagination enforcement (VCL-83 / PERF-012)
app.add_middleware(MaxPageSizeMiddleware)

# Prometheus metrics middleware for performance monitoring (VCL-49 / INFRA-007)
app.add_middleware(PrometheusMiddleware)
```

### Step 3: Add Router (in main.py after other router inclusions)

Around line 293, after the other router inclusions, add:

```python
# Prometheus metrics endpoint (VCL-49 / INFRA-007)
app.include_router(metrics_router)
```

The router section should look like:

```python
app.include_router(admin_router)
app.include_router(intelligence_router)
app.include_router(auth_router)
# Prometheus metrics endpoint (VCL-49 / INFRA-007)
app.include_router(metrics_router)
```

### Step 4: Update Pool/Cache Metrics in Lifespan (Optional)

If you want to periodically update pool and cache metrics, add this to the lifespan function:

```python
# In the lifespan function, after app is fully initialized:
async def update_infrastructure_metrics():
    """Periodically update infrastructure metrics."""
    while True:
        try:
            # Update pool metrics if monitor available
            if db.monitor:
                health = db.monitor.get_health_status()
                metrics = get_metrics()
                metrics.update_pool_metrics(
                    pool_name="main",
                    active=int(health.get("active_connections", 0)),
                    idle=int(health.get("idle_connections", 0)),
                    total=int(health.get("total_size", 0)),
                )
            
            # Update cache metrics if cache available
            cache_manager = getattr(app.state, "cache", None)
            if cache_manager:
                cache_stats = await cache_manager.get_stats()
                metrics.update_cache_metrics(
                    hits=int(cache_stats.get("hits", 0)),
                    misses=int(cache_stats.get("misses", 0)),
                )
        except Exception as e:
            logger.warning(f"Error updating metrics: {e}")
        
        await asyncio.sleep(30)  # Update every 30 seconds
```

## Running the Metrics

### Access the Metrics Endpoint

Once the application is running:

```bash
curl http://localhost:8000/metrics
```

This will output Prometheus exposition format with all collected metrics.

### Setting Up Prometheus

1. Copy the configuration file:
```bash
cp config/prometheus/prometheus.yml /etc/prometheus/prometheus.yml
cp config/prometheus/alert_rules.yml /etc/prometheus/alert_rules.yml
```

2. Update paths in prometheus.yml if needed

3. Restart Prometheus:
```bash
systemctl restart prometheus
# or if using Docker:
docker restart prometheus
```

### Importing Grafana Dashboard

1. Go to Grafana: `http://localhost:3000`
2. Click "+" → "Import"
3. Upload `config/grafana/dashboards/vancity-lens.json`
4. Select your Prometheus datasource
5. Click "Import"

## Metric Details

### request_duration_seconds
Histogram tracking HTTP request duration with buckets for latency analysis:
- Buckets: 0.005s, 0.01s, 0.025s, 0.05s, 0.075s, 0.1s, 0.25s, 0.5s, 0.75s, 1.0s, 2.5s, 5.0s
- Labels: method, endpoint, status
- Used for: Latency percentiles (p50, p95, p99)

### api_calls_total
Counter for total API requests:
- Labels: method, endpoint, status
- Used for: Request rate, status distribution

### active_requests
Gauge for concurrent requests:
- No labels
- Used for: Concurrency monitoring

### db_pool_size
Gauge for database connection pool:
- Labels: pool_name, state (active|idle|total)
- Used for: Pool health and capacity monitoring

### cache_hit_ratio
Gauge for cache performance (0.0-1.0):
- No labels
- Used for: Cache effectiveness monitoring

### errors_total
Counter for error responses:
- Labels: endpoint, status
- Used for: Error rate calculation and debugging

## Alert Rules

All alerts are configured with appropriate severity levels and durations:

| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| HighLatencyP95 | P95 > 5s | 5m | warning |
| HighLatencyP99 | P99 > 10s | 3m | critical |
| HighErrorRate | Error rate > 5% | 2m | warning |
| CriticalErrorRate | Error rate > 10% | 1m | critical |
| DBPoolExhaustion | Utilization > 90% | 2m | critical |
| LowCacheHitRatio | Ratio < 50% | 10m | info |
| HighConcurrentRequests | Active > 100 | 5m | warning |

## Performance Considerations

1. **Excluded Endpoints**: `/health`, `/ready`, `/metrics` are excluded from tracking to avoid circular dependencies and noise

2. **Metric Cardinality**: The middleware extracts full endpoint paths which can create high cardinality if not careful with dynamic IDs. Consider aggregating similar endpoints in dashboards.

3. **Histogram Buckets**: Custom buckets are optimized for typical API response times (5-100ms for p50, 100-500ms for p95, 500ms-5s for p99)

4. **Storage**: Prometheus default retention is 15 days. Adjust `--storage.tsdb.retention.time` flag if needed.

## Testing

Run the comprehensive test suite:

```bash
pytest tests/test_metrics.py -v
```

Expected output: 50 test cases covering:
- Singleton pattern and initialization
- Request tracking and middleware behavior
- Metric recording and updates
- Prometheus format output
- Label extraction
- Error handling
- Performance benchmarks
- Edge cases

## Troubleshooting

### Metrics endpoint returns 404
- Ensure `metrics_routes.py` is imported and router is included
- Check that middleware is added before routers

### No data in Prometheus
- Verify `/metrics` endpoint is accessible: `curl http://localhost:8000/metrics`
- Check Prometheus scrape config points to correct host/port
- Review Prometheus UI at `http://localhost:9090` → Status → Targets

### High cardinality warnings
- Monitor unique endpoint label values in Prometheus
- Consider grouping dynamic endpoints: `/users/{id}` → `/users/{id}` (grouped)

### Alert not firing
- Verify alert rules are loaded: Prometheus UI → Alerts
- Check alert conditions and durations match your environment
- Ensure Alertmanager is configured if using alerts

## Next Steps

1. Integrate middleware and router into main.py (Steps 1-3 above)
2. Deploy and verify `/metrics` endpoint is working
3. Configure Prometheus to scrape metrics
4. Import Grafana dashboard
5. Set up alerting integration with Alertmanager/PagerDuty/etc.
6. Monitor dashboard during development
7. Adjust alert thresholds based on observed patterns

## References

- Prometheus Documentation: https://prometheus.io/docs/
- prometheus_client Python library: https://github.com/prometheus/client_python
- Grafana Dashboarding: https://grafana.com/docs/grafana/latest/dashboards/
- FastAPI Middleware: https://fastapi.tiangolo.com/advanced/middleware/
