"""
Prometheus metrics endpoint routes for VanCity Lens (VCL-49 / INFRA-007)

Provides:
- GET /metrics — Prometheus metrics endpoint
"""

from fastapi import APIRouter, Response
from .metrics import get_metrics
from prometheus_client import CONTENT_TYPE_LATEST

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    response_class=Response,
    summary="Prometheus metrics",
    description="Returns metrics in Prometheus text format for scraping by monitoring systems.",
    tags=["observability", "internal"],
)
async def metrics_endpoint():
    """
    Expose Prometheus metrics for monitoring systems.

    Returns metrics in Prometheus exposition format including:
    - request_duration_seconds: Request latency histogram
    - api_calls_total: Total API call counter
    - active_requests: Currently active request count
    - db_pool_size: Database connection pool metrics
    - cache_hit_ratio: Cache hit ratio
    - errors_total: Error count by endpoint

    This endpoint is typically excluded from rate limiting and normal metrics collection.
    """
    metrics = get_metrics()
    return Response(
        content=metrics.get_metrics(),
        media_type=CONTENT_TYPE_LATEST,
    )
